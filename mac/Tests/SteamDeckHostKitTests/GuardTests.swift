import Foundation
import Testing
@testable import SteamDeckHostKit

@MainActor private enum GuardFixture {
    static var executable: URL?
    static func build() async throws -> URL {
        if let executable { return executable }
        let binary = try await Task.detached {
        let directory = URL(fileURLWithPath: "/tmp/sdhost-h1/guard-helper-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let main = directory.appendingPathComponent("main.swift")
        try Data(contentsOf: fixture("guard_main.swift.txt")).write(to: main)
        let package = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let build = package.appendingPathComponent(".build/debug")
        let objects = try FileManager.default.contentsOfDirectory(at: build.appendingPathComponent("SteamDeckHostKit.build"), includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "o" }.map(\.path)
        let binary = directory.appendingPathComponent("guard-fixture")
        _ = try ProcessInspection.command("/usr/bin/xcrun", ["swiftc", "-module-cache-path", directory.appendingPathComponent("cache").path,
            "-I", build.appendingPathComponent("Modules").path, main.path] + objects + ["-o", binary.path])
        return binary
        }.value
        executable = binary
        return binary
    }
}

@Suite(.serialized) @MainActor struct GuardTests {
    @Test func guardInvocationIsStrict() throws {
        let value = try BridgeGuard.Invocation.parse(["--bridge-guard", "123", "--", "/bin/sh", "bridge.sh"])
        #expect(value.hostPID == 123 && value.command == ["/bin/sh", "bridge.sh"])
        for args in [[String](), ["--bridge-guard", "0", "--", "/bin/sh"], ["--bridge-guard", "123", "/bin/sh"], ["--bridge-guard", "123", "--", "python"]] {
            #expect(throws: (any Error).self) { try BridgeGuard.Invocation.parse(args) }
        }
    }
    @Test(arguments: ["host-kill", "term", "int", "host-kill-stubborn"])
    func guardReapsBridgeOnHostDeathOrForwardedSignal(_ mode: String) async throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let helper = try await GuardFixture.build()
        let host = Process(); host.executableURL = URL(fileURLWithPath: "/bin/sleep"); host.arguments = ["30"]
        try host.run()
        defer { if host.isRunning { kill(host.processIdentifier, SIGKILL); host.waitUntilExit() } }
        let capture = scratch.file("guard.log")
        FileManager.default.createFile(atPath: capture.path, contents: nil)
        let log = try FileHandle(forWritingTo: capture); defer { try? log.close() }
        let guardProcess = Process(); guardProcess.executableURL = helper
        let stubborn = mode == "host-kill-stubborn"
        guardProcess.arguments = [scratch.paths.pidFile.path, "--bridge-guard", String(host.processIdentifier), "--", "/bin/sh", fixture(stubborn ? "stubborn_bridge.sh" : "fake_bridge.sh").path]
        guardProcess.standardOutput = log; guardProcess.standardError = log
        try guardProcess.run()
        defer {
            if let record = try? BridgePIDRecord.load(from: scratch.paths.pidFile), ProcessInspection.isAlive(record.bridgePID) { kill(record.bridgePID, SIGKILL) }
            if guardProcess.isRunning { kill(guardProcess.processIdentifier, SIGKILL); guardProcess.waitUntilExit() }
        }
        try await eventually { FileManager.default.fileExists(atPath: scratch.paths.pidFile.path) || !guardProcess.isRunning }
        let failure = (try? String(contentsOf: capture)) ?? "no guard output"
        let record = try #require(try BridgePIDRecord.load(from: scratch.paths.pidFile), "Guard did not start its bridge: \(failure)")
        #expect(record.guardPID == guardProcess.processIdentifier && record.bridgePID != record.guardPID)
        #expect(record.startTime > Date().timeIntervalSince1970 - 10)
        try await eventually { ((try? String(contentsOf: capture)) ?? "").contains("ready\n") }
        let start = ProcessInfo.processInfo.systemUptime
        if mode.hasPrefix("host-kill") { kill(host.processIdentifier, SIGKILL); host.waitUntilExit() }
        else { kill(guardProcess.processIdentifier, mode == "term" ? SIGTERM : SIGINT) }
        try await eventually(seconds: 10) { !ProcessInspection.isAlive(record.bridgePID) && !guardProcess.isRunning }
        #expect(ProcessInfo.processInfo.systemUptime - start < 10)
        #expect(kill(record.bridgePID, 0) == -1 && errno == ESRCH)
        #expect(!FileManager.default.fileExists(atPath: scratch.paths.pidFile.path))
        if stubborn {
            #expect(guardProcess.terminationStatus == 137)
            #expect(ProcessInfo.processInfo.systemUptime - start >= 8)
        } else {
            #expect(try String(contentsOf: capture).contains("stopping\n"), "Both guard signals and parent death must deliver TERM to the bridge")
            #expect(guardProcess.terminationStatus == 0)
        }
        if !mode.hasPrefix("host-kill") { #expect(host.isRunning) }
    }
    @Test(arguments: [true, false]) func leftoverPIDReapsOnlyMatchingCommand(_ matching: Bool) async throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let child = Process(); child.executableURL = URL(fileURLWithPath: "/bin/sh")
        child.arguments = [fixture("fake_bridge.sh").path, matching ? "windows.win_recv" : "unrelated-fixture"]
        child.standardInput = FileHandle.nullDevice
        let output = Pipe(); child.standardOutput = output; child.standardError = output
        try child.run()
        defer { if child.isRunning { kill(child.processIdentifier, SIGKILL); child.waitUntilExit() } }
        // Wait for the fixture's traps, not just successful posix_spawn.
        var bytes = Data()
        while !String(decoding: bytes, as: UTF8.self).contains("ready\n") { bytes.append(output.fileHandleForReading.availableData) }
        let record = BridgePIDRecord(bridgePID: child.processIdentifier, guardPID: getpid())
        try record.save(to: scratch.paths.pidFile)
        let before = try Data(contentsOf: scratch.paths.pidFile)
        let result = try await OrphanReaper().reconcile(pidFile: scratch.paths.pidFile)
        if matching {
            #expect(result == .reaped(child.processIdentifier))
            #expect(kill(child.processIdentifier, 0) == -1 && errno == ESRCH)
            #expect(!FileManager.default.fileExists(atPath: scratch.paths.pidFile.path))
        } else {
            guard case let .foreign(pid, command) = result else { Issue.record("Nonmatching live process was not reported"); return }
            #expect(pid == child.processIdentifier && command.contains("unrelated-fixture"))
            #expect(child.isRunning && kill(child.processIdentifier, 0) == 0)
            #expect(try Data(contentsOf: scratch.paths.pidFile) == before)
        }
    }
    @Test func pidfileReplacementCannotBeRemovedByOldGuard() throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let first = BridgePIDRecord(bridgePID: 123, guardPID: 124, startTime: 100)
        let second = BridgePIDRecord(bridgePID: 125, guardPID: 126, startTime: 101)
        try first.save(to: scratch.paths.pidFile)
        #expect(try BridgePIDRecord.load(from: scratch.paths.pidFile) == first)
        try second.save(to: scratch.paths.pidFile)
        try first.removeIfMatching(at: scratch.paths.pidFile)
        #expect(try BridgePIDRecord.load(from: scratch.paths.pidFile) == second)
        try second.removeIfMatching(at: scratch.paths.pidFile)
        #expect(try BridgePIDRecord.load(from: scratch.paths.pidFile) == nil)
    }

    // The real ps-backed test above remains mandatory on the gate. These
    // injected identity controls still signal and observe real fixture PIDs.
    @Test(arguments: [true, false]) func orphanDecisionWithInjectedIdentityStillAssertsRealProcess(_ matching: Bool) async throws {
        struct Identity: ProcessIdentifying {
            let matching: Bool
            func commandLine(pid: Int32) throws -> String { matching ? "python -m windows.win_recv" : "/bin/sleep 30" }
            func birthSignature(pid: Int32) throws -> String { "fixture-start" }
        }
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let child = Process(); child.executableURL = URL(fileURLWithPath: "/bin/sleep"); child.arguments = ["30"]
        try child.run()
        defer { if child.isRunning { kill(child.processIdentifier, SIGKILL); child.waitUntilExit() } }
        try BridgePIDRecord(bridgePID: child.processIdentifier, guardPID: getpid()).save(to: scratch.paths.pidFile)
        let bytes = try Data(contentsOf: scratch.paths.pidFile)
        let result = try await OrphanReaper(identity: Identity(matching: matching)).reconcile(pidFile: scratch.paths.pidFile)
        if matching {
            #expect(result == .reaped(child.processIdentifier))
            #expect(kill(child.processIdentifier, 0) == -1 && errno == ESRCH)
            #expect(!FileManager.default.fileExists(atPath: scratch.paths.pidFile.path))
        } else {
            #expect(result == .foreign(child.processIdentifier, "/bin/sleep 30"))
            #expect(kill(child.processIdentifier, 0) == 0)
            #expect(try Data(contentsOf: scratch.paths.pidFile) == bytes)
        }
    }
}
