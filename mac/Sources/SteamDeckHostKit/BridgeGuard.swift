import Foundation

public struct BridgePIDRecord: Equatable {
    public let bridgePID: Int32
    public let guardPID: Int32
    public let startTime: TimeInterval
    public init(bridgePID: Int32, guardPID: Int32, startTime: TimeInterval = Date().timeIntervalSince1970) {
        self.bridgePID = bridgePID; self.guardPID = guardPID; self.startTime = startTime
    }
    public func save(to url: URL) throws {
        try AtomicFile.write(JSONSerialization.data(withJSONObject: ["bridge_pid": bridgePID, "guard_pid": guardPID, "start_time": startTime]), to: url)
    }
    public static func load(from url: URL) throws -> BridgePIDRecord? {
        let data: Data
        do { data = try Data(contentsOf: url) }
        catch let error as CocoaError where error.code == .fileReadNoSuchFile { return nil }
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let bridge = object["bridge_pid"] as? Int32, bridge > 1,
              let guardPID = object["guard_pid"] as? Int32, guardPID > 1,
              let start = object["start_time"] as? Double else { throw HostError("Malformed pidfile \(url.path)") }
        return BridgePIDRecord(bridgePID: bridge, guardPID: guardPID, startTime: start)
    }
    public func removeIfMatching(at url: URL) throws {
        if try Self.load(from: url) == self { try FileManager.default.removeItem(at: url) }
    }
}

public enum OrphanResult: Equatable { case none, reaped(Int32), foreign(Int32, String) }
public protocol ProcessIdentifying {
    func commandLine(pid: Int32) throws -> String
    func birthSignature(pid: Int32) throws -> String
}
public struct SystemProcessIdentity: ProcessIdentifying {
    public init() {}
    public func commandLine(pid: Int32) throws -> String {
        try ProcessInspection.command("/bin/ps", ["-o", "command=", "-p", String(pid)])
    }
    public func birthSignature(pid: Int32) throws -> String {
        try ProcessInspection.command("/bin/ps", ["-o", "lstart=", "-p", String(pid)])
    }
}
@MainActor public protocol OrphanReconciling { func reconcile(pidFile: URL) async throws -> OrphanResult }
@MainActor public struct OrphanReaper: OrphanReconciling {
    private let clock: HostClock
    private let identity: ProcessIdentifying
    public init(clock: HostClock? = nil, identity: ProcessIdentifying = SystemProcessIdentity()) {
        self.clock = clock ?? SystemHostClock(); self.identity = identity
    }
    public func reconcile(pidFile: URL) async throws -> OrphanResult {
        guard let record = try BridgePIDRecord.load(from: pidFile) else { return .none }
        guard ProcessInspection.isAlive(record.bridgePID) else {
            try record.removeIfMatching(at: pidFile); return .none
        }
        let original = try identity.commandLine(pid: record.bridgePID)
        guard original.contains("windows.win_recv") else { return .foreign(record.bridgePID, original) }
        // Capture and recheck birth identity before the second signal, so a reused
        // PID cannot turn an old ownership record into authority over a new process.
        let birth = try identity.birthSignature(pid: record.bridgePID)
        guard kill(record.bridgePID, SIGTERM) == 0 || errno == ESRCH else { throw HostError("Cannot stop orphan pid \(record.bridgePID): \(String(cString: strerror(errno)))") }
        let deadline = clock.now + 8
        while ProcessInspection.isAlive(record.bridgePID), clock.now < deadline { try await clock.sleep(seconds: 0.05) }
        if ProcessInspection.isAlive(record.bridgePID) {
            let current = try identity.commandLine(pid: record.bridgePID)
            let currentBirth = try identity.birthSignature(pid: record.bridgePID)
            guard current == original, birth == currentBirth else { return .foreign(record.bridgePID, current) }
            guard kill(record.bridgePID, SIGKILL) == 0 || errno == ESRCH else { throw HostError("Cannot kill orphan pid \(record.bridgePID)") }
            let killDeadline = clock.now + 2
            while ProcessInspection.isAlive(record.bridgePID), clock.now < killDeadline { try await clock.sleep(seconds: 0.05) }
        }
        guard !ProcessInspection.isAlive(record.bridgePID) else { throw HostError("Orphan pid \(record.bridgePID) has not exited") }
        try record.removeIfMatching(at: pidFile)
        return .reaped(record.bridgePID)
    }
}

/// Runs in a separate copy of the host executable, before AppKit is initialized.
/// Register NOTE_EXIT before spawning Python: a host death during setup cannot
/// be missed. The guard inherits cwd, environment and output from its supervisor.
public enum BridgeGuard {
    public struct Invocation: Equatable {
        public let hostPID: Int32
        public let command: [String]
        public static func parse(_ arguments: [String]) throws -> Invocation {
            guard arguments.count >= 4, arguments[0] == "--bridge-guard",
                  let pid = Int32(arguments[1]), pid > 1, arguments[2] == "--",
                  arguments[3].hasPrefix("/") else { throw HostError("Expected --bridge-guard <host pid> -- <absolute executable> [arguments]") }
            return Invocation(hostPID: pid, command: Array(arguments.dropFirst(3)))
        }
    }
    public static func run(_ invocation: Invocation, pidFile: URL = HostPaths().pidFile,
                           stopTimeout: TimeInterval = 8) throws -> Int32 {
        let queue = kqueue()
        guard queue >= 0 else { throw HostError("kqueue: \(String(cString: strerror(errno)))") }
        defer { close(queue) }
        func register(_ ident: UInt, _ filter: Int16, _ flags: UInt32 = 0) throws {
            var event = kevent(ident: ident, filter: filter, flags: UInt16(EV_ADD | EV_ENABLE), fflags: flags, data: 0, udata: nil)
            guard kevent(queue, &event, 1, nil, 0, nil) == 0 else {
                throw HostError("kevent pid/signal \(ident): \(String(cString: strerror(errno))) (errno \(errno))")
            }
        }
        try register(UInt(invocation.hostPID), Int16(EVFILT_PROC), UInt32(NOTE_EXIT))
        // Caught handlers reset on exec; SIG_IGN would also silence Python's TERM.
        let oldTERM = signal(SIGTERM, { _ in }), oldINT = signal(SIGINT, { _ in })
        defer { signal(SIGTERM, oldTERM); signal(SIGINT, oldINT) }
        try register(UInt(SIGTERM), Int16(EVFILT_SIGNAL))
        try register(UInt(SIGINT), Int16(EVFILT_SIGNAL))
        guard ProcessInspection.isAlive(invocation.hostPID) else { return 0 }
        let child = Process()
        child.executableURL = URL(fileURLWithPath: invocation.command[0])
        child.arguments = Array(invocation.command.dropFirst())
        child.standardInput = FileHandle.nullDevice
        child.standardOutput = FileHandle.standardOutput; child.standardError = FileHandle.standardError
        try child.run()
        let record = BridgePIDRecord(bridgePID: child.processIdentifier, guardPID: getpid())
        do { try record.save(to: pidFile) }
        catch { child.terminate(); if child.isRunning { _ = kill(child.processIdentifier, SIGKILL) }; child.waitUntilExit(); throw error }
        var deadline: TimeInterval?
        while child.isRunning {
            var event = kevent()
            var timeout = timespec(tv_sec: 0, tv_nsec: 50_000_000)
            let count = kevent(queue, nil, 0, &event, 1, &timeout)
            if count < 0 && errno != EINTR {
                child.terminate(); deadline = ProcessInfo.processInfo.systemUptime + stopTimeout
            }
            let hostExited = count > 0 && event.filter == Int16(EVFILT_PROC)
            let requestedStop = count > 0 && event.filter == Int16(EVFILT_SIGNAL)
            if deadline == nil && (hostExited || requestedStop || !ProcessInspection.isAlive(invocation.hostPID)) {
                child.terminate() // SIGINT to the guard is deliberately translated to TERM.
                deadline = ProcessInfo.processInfo.systemUptime + stopTimeout
            }
            if let end = deadline, ProcessInfo.processInfo.systemUptime >= end, child.isRunning {
                _ = kill(child.processIdentifier, SIGKILL)
            }
        }
        child.waitUntilExit()
        try record.removeIfMatching(at: pidFile)
        return child.terminationReason == .uncaughtSignal ? 128 + child.terminationStatus : child.terminationStatus
    }
}
