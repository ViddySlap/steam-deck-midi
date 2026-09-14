import Foundation

@MainActor public final class BridgeSupervisor {
    public private(set) var state: BridgeState = .stopped { didSet { onChange?() } }
    public private(set) var health: HealthResult = .unhealthy("Bridge is stopped") { didSet { onChange?() } }
    public private(set) var settings: HostSettings
    public private(set) var activeSettings: HostSettings?
    public var uiURL: URL { (activeSettings ?? settings).uiURL }
    public let paths: HostPaths
    public let log: BridgeLog
    public var onChange: (() -> Void)?
    public var pid: Int32? { child?.pid }
    public var bridgePID: Int32? {
        guard let child else { return nil }
        if !child.guardsBridge { return child.pid }
        guard let record = try? BridgePIDRecord.load(from: paths.pidFile), record.guardPID == child.pid else { return nil }
        return record.bridgePID
    }
    private let launcher: ProcessLaunching
    private let ports: PortChecking
    private let probe: HealthChecking
    private let clock: HostClock
    private let reaper: OrphanReconciling
    private var child: ChildProcess?
    private var requestedStop = false
    private var generation = 0
    private var crashes: [TimeInterval] = []
    private var restartCount = 0
    private var healthTask: Task<Void, Never>?
    private var restartTask: Task<Void, Never>?
    private var killTask: Task<Void, Never>?
    private var stopWaiters: [CheckedContinuation<Void, Never>] = []
    private var logFailure: String?

    public init(settings: HostSettings, paths: HostPaths = HostPaths(),
                launcher: ProcessLaunching? = nil,
                ports: PortChecking = BindPortChecker(), probe: HealthChecking = HealthProbe(),
                clock: HostClock? = nil, reaper: OrphanReconciling? = nil) {
        self.settings = settings; self.paths = paths; self.launcher = launcher ?? FoundationProcessLauncher()
        self.ports = ports; self.probe = probe; self.clock = clock ?? SystemHostClock(); self.reaper = reaper ?? OrphanReaper()
        log = BridgeLog(url: paths.bridgeLog)
    }
    public func updateSettings(_ value: HostSettings) { settings = value }
    /// Called on app launch even when bridge autostart is disabled.
    @discardableResult public func reconcileOrphan() async throws -> OrphanResult {
        let result = try await reaper.reconcile(pidFile: paths.pidFile)
        if case let .foreign(pid, command) = result {
            throw HostError("Leftover pid \(pid) is not this bridge; left alone: \(command)")
        }
        return result
    }
    public func start() async {
        guard child == nil, state != .starting, state != .stopping else { return }
        restartTask?.cancel(); restartTask = nil
        crashes.removeAll(); restartCount = 0; logFailure = nil
        generation += 1
        await launch(generation: generation, reconcile: true)
    }
    private func launch(generation token: Int, reconcile: Bool) async {
        guard token == generation, child == nil else { return }
        state = .starting; health = .unhealthy("Waiting for /api/settings")
        requestedStop = false
        let configuration = settings
        do {
            if reconcile { try await reconcileOrphan() }
            guard token == generation else { return }
            if let (port, pid) = try ports.busyPort(in: BridgePort.required(by: configuration)) {
                state = .portBusy(port: port, pid: pid); return
            }
            try log.open()
            activeSettings = configuration
            let environment = ProcessInfo.processInfo.environment.merging(configuration.bridgeEnvironment) { _, override in override }
            child = try launcher.launch(ProcessSpecification(executable: configuration.python,
                arguments: configuration.bridgeArguments, directory: configuration.bridgeRoot, environment: environment),
                output: { [weak self] data in
                    guard let self, token == self.generation else { return }
                    do { try self.log.append(data) }
                    catch {
                        self.logFailure = "Cannot capture bridge log: \(error.localizedDescription)"
                        Task { await self.stop() }
                    }
                }, exited: { [weak self] code in self?.exited(code, generation: token) })
            healthTask = Task { [weak self] in
                guard let self else { return }
                while !Task.isCancelled && token == self.generation && self.child != nil && !self.requestedStop {
                    let result = await self.probe.check(uiURL: configuration.uiURL)
                    guard !Task.isCancelled, token == self.generation, self.child != nil, !self.requestedStop else { break }
                    self.health = result
                    if result == .healthy { self.state = .running }
                    do { try await self.clock.sleep(seconds: 0.5) } catch { break }
                }
            }
        } catch {
            if token == generation { state = .failed(reason: error.localizedDescription) }
        }
    }
    public func stop() async {
        restartTask?.cancel(); restartTask = nil
        healthTask?.cancel(); healthTask = nil
        guard let child else {
            generation += 1 // Invalidate a launch waiting on orphan reconciliation.
            state = logFailure.map { .failed(reason: $0) } ?? .stopped
            health = .unhealthy("Bridge is stopped")
            return
        }
        if !requestedStop {
            requestedStop = true
            state = .stopping
            child.terminate()
            if !child.guardsBridge {
                let token = generation
                killTask = Task { [weak self] in
                    guard let self else { return }
                    do { try await self.clock.sleep(seconds: 8) } catch { return }
                    guard token == self.generation, self.requestedStop else { return }
                    self.child?.forceKill()
                }
            }
        }
        // A timer never changes stopping to stopped. Only the exit callback can.
        await withCheckedContinuation { stopWaiters.append($0) }
    }
    public func restart() async { await stop(); await start() }
    private func exited(_ code: Int32, generation token: Int) {
        guard token == generation else { return }
        child = nil
        healthTask?.cancel(); healthTask = nil
        killTask?.cancel(); killTask = nil
        log.finish(); health = .unhealthy("Bridge exited with code \(code)")
        if requestedStop {
            state = logFailure.map { .failed(reason: $0) } ?? .stopped
            let waiters = stopWaiters; stopWaiters.removeAll()
            waiters.forEach { $0.resume() }
            return
        }
        crashes = crashes.filter { clock.now - $0 < 60 }
        crashes.append(clock.now)
        if crashes.count >= 5 { state = .failed(reason: "crashed repeatedly"); return }
        restartCount += 1
        state = .crashed(exitCode: code, restarts: restartCount)
        let delays: [TimeInterval] = [1, 2, 4, 8, 16, 30]
        let delay = delays[min(restartCount - 1, delays.count - 1)]
        restartTask = Task { [weak self] in
            guard let self else { return }
            do { try await self.clock.sleep(seconds: delay) } catch { return }
            guard !Task.isCancelled, token == self.generation else { return }
            // A guard crash may leave its child alive. Reconcile its pidfile
            // before probing ports or spawning the next guard as well.
            await self.launch(generation: token, reconcile: true)
        }
    }
}
