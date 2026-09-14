import Foundation
import Testing
@testable import SteamDeckHostKit

struct Scratch {
    let root: URL
    init() throws {
        root = URL(fileURLWithPath: "/tmp/sdhost-h1/tests/\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }
    var paths: HostPaths { HostPaths(appSupport: root.appendingPathComponent("support"), logs: root.appendingPathComponent("logs")) }
    func file(_ name: String) -> URL { root.appendingPathComponent(name) }
    func cleanup() { try? FileManager.default.removeItem(at: root) }
}
func fixture(_ name: String) -> URL { Bundle.module.url(forResource: name, withExtension: nil, subdirectory: "Fixtures")! }
@MainActor func eventually(seconds: Double = 3, _ condition: () -> Bool) async throws {
    let end = ProcessInfo.processInfo.systemUptime + seconds
    while !condition() && ProcessInfo.processInfo.systemUptime < end { try await Task.sleep(nanoseconds: 10_000_000) }
    try #require(condition(), "Condition did not become true within \(seconds) seconds")
}
@MainActor final class ManualClock: HostClock {
    var now: TimeInterval = 0
    var requested: [TimeInterval] = []
    private var sleepers: [UUID: (TimeInterval, CheckedContinuation<Void, Error>)] = [:]
    func sleep(seconds: TimeInterval) async throws {
        let id = UUID()
        try await withTaskCancellationHandler {
            try Task.checkCancellation()
            try await withCheckedThrowingContinuation { continuation in
                requested.append(seconds)
                sleepers[id] = (now + seconds, continuation)
            }
        } onCancel: { Task { @MainActor in self.sleepers.removeValue(forKey: id)?.1.resume(throwing: CancellationError()) } }
    }
    func advance(_ seconds: TimeInterval) async {
        now += seconds
        let ready = sleepers.filter { $0.value.0 <= now }.map(\.key)
        ready.forEach { sleepers.removeValue(forKey: $0)?.1.resume() }
        for _ in 0..<20 { await Task.yield() }
    }
}
@MainActor final class FakeChild: ChildProcess {
    let pid: Int32
    var isRunning = true
    var guardsBridge = false
    var signals: [Int32] = []
    var autoExit = true
    let output: @MainActor (Data) -> Void
    let exited: @MainActor (Int32) -> Void
    init(pid: Int32, output: @escaping @MainActor (Data) -> Void, exited: @escaping @MainActor (Int32) -> Void) {
        self.pid = pid; self.output = output; self.exited = exited
    }
    func terminate() {
        signals.append(SIGTERM)
        if autoExit { Task { await Task.yield(); finish(0) } }
    }
    func forceKill() { signals.append(SIGKILL); Task { await Task.yield(); finish(-9) } }
    func finish(_ code: Int32) { guard isRunning else { return }; isRunning = false; exited(code) }
}
@MainActor final class FakeLauncher: ProcessLaunching {
    var specifications: [ProcessSpecification] = []
    var children: [FakeChild] = []
    var failure: Error?
    func launch(_ spec: ProcessSpecification, output: @escaping @MainActor (Data) -> Void,
                exited: @escaping @MainActor (Int32) -> Void) throws -> ChildProcess {
        if let failure { throw failure }
        specifications.append(spec)
        let child = FakeChild(pid: Int32(900_000 + children.count), output: output, exited: exited)
        children.append(child)
        return child
    }
}
struct FreePorts: PortChecking { func busyPort(in ports: [BridgePort]) throws -> (UInt16, Int32?)? { nil } }
struct FixedHealth: HealthChecking {
    var result: HealthResult = .healthy
    func check(uiURL: URL) async -> HealthResult { result }
}
@MainActor struct NoOrphan: OrphanReconciling {
    func reconcile(pidFile: URL) async throws -> OrphanResult { .none }
}
@MainActor final class FakeLogin: LoginItem {
    var value: LoginItemStatus = .notRegistered
    var writes: [Bool] = []
    var failure: Error?
    func status() -> LoginItemStatus { value }
    func setEnabled(_ enabled: Bool) throws {
        if let failure { throw failure }
        writes.append(enabled); value = enabled ? .enabled : .notRegistered
    }
}
final class HeldSocket {
    let descriptor: Int32
    let port: UInt16
    init(_ transport: PortTransport) throws {
        let descriptor = socket(AF_INET, transport == .tcp ? SOCK_STREAM : SOCK_DGRAM, 0)
        self.descriptor = descriptor
        guard descriptor >= 0 else { throw HostError("fixture socket errno \(errno)") }
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size); addr.sin_family = sa_family_t(AF_INET)
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")
        let result = withUnsafePointer(to: &addr) { p in
            p.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(descriptor, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) }
        }
        guard result == 0 else { let code = errno; close(descriptor); throw HostError("fixture bind 127.0.0.1:0: \(String(cString: strerror(code))) (errno \(code))") }
        if transport == .tcp, listen(descriptor, 4) != 0 { close(descriptor); throw HostError("fixture listen errno \(errno)") }
        var size = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &addr) { p in p.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(descriptor, $0, &size) } }
        port = UInt16(bigEndian: addr.sin_port)
    }
    deinit { close(descriptor) }
}
