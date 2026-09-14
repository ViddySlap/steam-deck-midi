import Foundation
import Testing
@testable import SteamDeckHostKit

@Suite(.serialized) @MainActor struct SupervisorTests {
    @Test func realProcessLogsEnvironmentCwdAndStopWaitsForESRCH() async throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let settings = try HostSettings(values: ["bridge_root": scratch.root.path, "python": "/bin/sh",
            "bridge_args": [fixture("fake_bridge.sh").path]])
        let supervisor = BridgeSupervisor(settings: settings, paths: scratch.paths, launcher: FoundationProcessLauncher(mode: .direct),
            ports: FreePorts(), probe: FixedHealth(), reaper: NoOrphan())
        await supervisor.start()
        let pid = try #require(supervisor.pid)
        defer { if ProcessInspection.isAlive(pid) { kill(pid, SIGKILL) } }
        try await eventually { supervisor.log.tail(lines: 200).contains("ready") && supervisor.state == .running }
        let expected = ["PYSTRAY_BACKEND=dummy", "BROWSER=/usr/bin/true", "cwd=\(scratch.root.path.replacingOccurrences(of: "/tmp/", with: "/private/tmp/"))",
                        "stdin-null", "line-1", "line-5", "stderr-line", "ready"]
        let output = supervisor.log.tail(lines: 200)
        for line in expected where !line.hasPrefix("cwd=") { #expect(output.contains(line)) }
        #expect(output.contains("cwd=\(scratch.root.path)") || output.contains(expected[2]))
        #expect(kill(pid, 0) == 0)
        // The fixture ignores INT like the real bridge. stop() must use TERM.
        #expect(kill(pid, SIGINT) == 0)
        try await Task.sleep(nanoseconds: 50_000_000)
        #expect(kill(pid, 0) == 0)
        await supervisor.stop()
        #expect(supervisor.state == .stopped)
        #expect(supervisor.pid == nil)
        #expect(kill(pid, 0) == -1 && errno == ESRCH)
        #expect(supervisor.log.tail(lines: 1) == ["stopping"])
        let file = try String(contentsOf: scratch.paths.bridgeLog)
        for line in ["line-1", "line-5", "stderr-line", "stopping", "BROWSER=/usr/bin/true", "PYSTRAY_BACKEND=dummy"] { #expect(file.contains(line + "\n")) }
        // Next launch appends instead of truncating the previous process's output.
        await supervisor.start()
        try await eventually { supervisor.state == .running }
        await supervisor.stop()
        #expect(try String(contentsOf: scratch.paths.bridgeLog).hasPrefix(file))
    }
    @Test func ringRetainsLast2000LinesAndFileRetainsAllBytes() throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let log = BridgeLog(url: scratch.paths.bridgeLog)
        let text = (0..<2005).map { "line-\($0)\n" }.joined() + "partial"
        let bytes = Data(text.utf8)
        try log.append(bytes.prefix(73)); try log.append(bytes.dropFirst(73)); log.finish()
        #expect(log.tail(lines: 3000).count == 2000)
        #expect(log.tail(lines: 3000).first == "line-6")
        #expect(log.tail(lines: 2) == ["line-2004", "partial"])
        #expect(try Data(contentsOf: scratch.paths.bridgeLog) == bytes)
        #expect(log.tail(lines: -1).isEmpty)
    }
    @Test func exactlyTwoEnvironmentOverridesAndOneOwnedChild() async throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let launcher = FakeLauncher()
        let settings = try HostSettings()
        let supervisor = BridgeSupervisor(settings: settings, paths: scratch.paths, launcher: launcher,
            ports: FreePorts(), probe: FixedHealth(), reaper: NoOrphan())
        await supervisor.start(); await supervisor.start()
        #expect(launcher.children.count == 1)
        let spec = try #require(launcher.specifications.first)
        #expect(spec.executable == settings.python && spec.arguments == settings.bridgeArguments && spec.directory == settings.bridgeRoot)
        #expect(spec.environment == ProcessInfo.processInfo.environment.merging(["PYSTRAY_BACKEND": "dummy", "BROWSER": "/usr/bin/true"]) { _, new in new })
        #expect(spec.environment.keys.sorted() == Set(ProcessInfo.processInfo.environment.keys).union(["PYSTRAY_BACKEND", "BROWSER"]).sorted())
        await supervisor.restart()
        #expect(launcher.children.count == 2)
        #expect(!launcher.children[0].isRunning)
        #expect(launcher.children[0].signals == [SIGTERM])
        await supervisor.stop()
        supervisor.updateSettings(try settings.updating(["bridge_env": [:]]))
        await supervisor.start()
        #expect(launcher.specifications.last?.environment == ProcessInfo.processInfo.environment)
        await supervisor.stop()
    }
    @Test func stoppingPersistsUntilExitAndEscalatesAtEightSeconds() async throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let launcher = FakeLauncher(), clock = ManualClock()
        let supervisor = BridgeSupervisor(settings: try HostSettings(), paths: scratch.paths, launcher: launcher,
            ports: FreePorts(), probe: FixedHealth(), clock: clock, reaper: NoOrphan())
        await supervisor.start()
        let child = try #require(launcher.children.first); child.autoExit = false
        let stopping = Task { await supervisor.stop() }
        try await eventually { supervisor.state == .stopping && clock.requested.contains(8) }
        #expect(child.isRunning && child.signals == [SIGTERM])
        await clock.advance(7.9)
        #expect(supervisor.state == .stopping && child.isRunning && child.signals == [SIGTERM])
        await clock.advance(0.1)
        await stopping.value
        #expect(child.signals == [SIGTERM, SIGKILL])
        #expect(!child.isRunning && supervisor.state == .stopped)
    }
    @Test func realStubbornProcessIsKilledAndReapedAfterTermDeadline() async throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let clock = ManualClock()
        let supervisor = BridgeSupervisor(settings: try HostSettings(values: ["bridge_root": scratch.root.path, "python": "/bin/sh",
            "bridge_args": [fixture("stubborn_bridge.sh").path]]), paths: scratch.paths,
            launcher: FoundationProcessLauncher(mode: .direct), ports: FreePorts(), probe: FixedHealth(), clock: clock, reaper: NoOrphan())
        await supervisor.start()
        let pid = try #require(supervisor.pid); defer { if ProcessInspection.isAlive(pid) { kill(pid, SIGKILL) } }
        try await eventually { supervisor.log.tail(lines: 20).contains("ready") }
        let stopping = Task { await supervisor.stop() }
        try await eventually { supervisor.state == .stopping && clock.requested.contains(8) }
        #expect(kill(pid, 0) == 0)
        await clock.advance(8)
        await stopping.value
        #expect(supervisor.state == .stopped)
        #expect(kill(pid, 0) == -1 && errno == ESRCH)
    }
    @Test func guardIsNeverKilledBySupervisor() async throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let launcher = FakeLauncher(), clock = ManualClock()
        let supervisor = BridgeSupervisor(settings: try HostSettings(), paths: scratch.paths, launcher: launcher,
            ports: FreePorts(), probe: FixedHealth(), clock: clock, reaper: NoOrphan())
        await supervisor.start()
        let child = try #require(launcher.children.first); child.guardsBridge = true; child.autoExit = false
        let stopping = Task { await supervisor.stop() }
        try await eventually { supervisor.state == .stopping }
        await clock.advance(10)
        #expect(child.signals == [SIGTERM] && child.isRunning)
        #expect(supervisor.state == .stopping)
        child.finish(0); await stopping.value
        #expect(supervisor.state == .stopped)
    }
    @Test func realExitThreeRestartsAtBackoffAndFiveCrashesLatchFailed() async throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let clock = ManualClock()
        let supervisor = BridgeSupervisor(settings: try HostSettings(values: ["bridge_root": scratch.root.path, "python": "/bin/sh",
            "bridge_args": [fixture("crash_bridge.sh").path]]), paths: scratch.paths,
            launcher: FoundationProcessLauncher(mode: .direct), ports: FreePorts(), probe: FixedHealth(), clock: clock, reaper: NoOrphan())
        await supervisor.start()
        for (index, delay) in [1.0, 2.0, 4.0, 8.0].enumerated() {
            try await eventually { supervisor.state == .crashed(exitCode: 3, restarts: index + 1) && clock.requested.contains(delay) }
            #expect(supervisor.pid == nil)
            await clock.advance(delay - 0.01)
            #expect(supervisor.state == .crashed(exitCode: 3, restarts: index + 1))
            await clock.advance(0.01)
        }
        try await eventually { supervisor.state == .failed(reason: "crashed repeatedly") }
        let bytes = try String(contentsOf: scratch.paths.bridgeLog)
        #expect(bytes.components(separatedBy: "crashing\n").count - 1 == 5)
        await clock.advance(100)
        #expect(supervisor.state == .failed(reason: "crashed repeatedly") && supervisor.pid == nil)
        #expect(try String(contentsOf: scratch.paths.bridgeLog) == bytes)
        await supervisor.start()
        try await eventually { supervisor.state == .crashed(exitCode: 3, restarts: 1) }
        await supervisor.stop()
        await clock.advance(100)
        #expect(supervisor.state == .stopped && supervisor.pid == nil)
    }
    @Test func backoffCapsAtThirtyAndCrashWindowExpires() async throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let launcher = FakeLauncher(), clock = ManualClock()
        let supervisor = BridgeSupervisor(settings: try HostSettings(), paths: scratch.paths, launcher: launcher,
            ports: FreePorts(), probe: FixedHealth(), clock: clock, reaper: NoOrphan())
        await supervisor.start()
        for delay in [1.0, 2, 4, 8, 16, 30, 30] {
            await clock.advance(61)
            let count = launcher.children.count
            launcher.children.last?.finish(3)
            try await eventually { clock.requested.last == delay }
            await clock.advance(delay)
            try await eventually { launcher.children.count == count + 1 }
        }
        await supervisor.stop()
    }
    @Test(arguments: [PortTransport.tcp, .udp]) func heldPortStaysHeldAndHolderIsNeverSignalled(_ transport: PortTransport) async throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let held = try HeldSocket(transport), launcher = FakeLauncher()
        let args = transport == .udp ? ["--listen", "127.0.0.1:\(held.port)"] : []
        let freeTCPPort = try HeldSocket(.tcp).port
        let settings = try HostSettings(values: ["ui_url": "http://127.0.0.1:\(transport == .tcp ? held.port : freeTCPPort)", "bridge_args": args])
        let supervisor = BridgeSupervisor(settings: settings, paths: scratch.paths, launcher: launcher,
            probe: FixedHealth(), reaper: NoOrphan())
        await supervisor.start()
        guard case let .portBusy(port, pid) = supervisor.state else { Issue.record("Expected busy port, got \(supervisor.state)"); return }
        #expect(port == held.port)
        if let pid { #expect(pid == getpid()) }
        #expect(launcher.specifications.isEmpty)
        await supervisor.stop()
        #expect(kill(getpid(), 0) == 0)
        #expect(try BindPortChecker().busyPort(in: [BridgePort(held.port, transport)])?.0 == held.port)
    }
    @Test func unhealthyChildNeverBecomesRunningAndSpawnFailureNamesReason() async throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let launcher = FakeLauncher()
        let supervisor = BridgeSupervisor(settings: try HostSettings(), paths: scratch.paths, launcher: launcher,
            ports: FreePorts(), probe: FixedHealth(result: .unhealthy("HTML")), reaper: NoOrphan())
        await supervisor.start()
        try await eventually { supervisor.health == .unhealthy("HTML") }
        #expect(supervisor.state == .starting)
        await supervisor.stop()
        launcher.failure = HostError("executable missing")
        await supervisor.start()
        #expect(supervisor.state == .failed(reason: "executable missing"))
        #expect(supervisor.pid == nil)
    }
    @Test func guardedLauncherUsesHostExecutableWithExactGuardArgv() async throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let executable = scratch.file("host-fixture.sh")
        try "#!/bin/sh\nprintf '%s\\n' \"$@\"\n".write(to: executable, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable.path)
        let launcher = FoundationProcessLauncher(mode: .guarded(hostExecutable: executable.path, hostPID: getpid()))
        let arguments = ["-m", "windows.win_recv", "--midi-port", "IAC Driver DECK_IN"]
        var captured = Data(), code: Int32?
        let child = try launcher.launch(ProcessSpecification(executable: "/python fixture", arguments: arguments,
            directory: scratch.root.path, environment: ProcessInfo.processInfo.environment), output: { captured.append($0) }, exited: { code = $0 })
        try await eventually { code != nil }
        #expect(code == 0 && !child.isRunning && child.guardsBridge)
        #expect(String(decoding: captured, as: UTF8.self).components(separatedBy: "\n") ==
            ["--bridge-guard", String(getpid()), "--", "/python fixture"] + arguments + [""])
        #expect(kill(child.pid, 0) == -1 && errno == ESRCH)
    }
    @Test func settingsChangesWaitForRestartAndForeignOrphanPreventsSpawn() async throws {
        struct Foreign: OrphanReconciling {
            func reconcile(pidFile: URL) async throws -> OrphanResult { .foreign(567, "unrelated") }
        }
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let launcher = FakeLauncher()
        let refused = BridgeSupervisor(settings: try HostSettings(), paths: scratch.paths, launcher: launcher,
            ports: FreePorts(), probe: FixedHealth(), reaper: Foreign())
        await refused.start()
        #expect(refused.state == .failed(reason: "Leftover pid 567 is not this bridge; left alone: unrelated"))
        #expect(launcher.children.isEmpty)
        let supervisor = BridgeSupervisor(settings: try HostSettings(), paths: scratch.paths, launcher: launcher,
            ports: FreePorts(), probe: FixedHealth(), reaper: NoOrphan())
        await supervisor.start()
        supervisor.updateSettings(try supervisor.settings.updating(["ui_url": "http://127.0.0.1:8800", "python": "/new/python"]))
        #expect(supervisor.uiURL.absoluteString == "http://127.0.0.1:7723")
        #expect(launcher.specifications.count == 1)
        await supervisor.restart()
        #expect(supervisor.uiURL.absoluteString == "http://127.0.0.1:8800")
        #expect(launcher.specifications.last?.executable == "/new/python")
        await supervisor.stop()
    }
}
