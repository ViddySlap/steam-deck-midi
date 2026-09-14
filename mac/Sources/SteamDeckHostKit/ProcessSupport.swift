import Foundation

public struct ProcessSpecification {
    public let executable: String
    public let arguments: [String]
    public let directory: String
    public let environment: [String: String]
    public init(executable: String, arguments: [String], directory: String, environment: [String: String]) {
        self.executable = executable; self.arguments = arguments
        self.directory = directory; self.environment = environment
    }
}
@MainActor public protocol ChildProcess: AnyObject {
    var pid: Int32 { get }
    var isRunning: Bool { get }
    /// A guard performs its own TERM/KILL ladder. Never SIGKILL that guard.
    var guardsBridge: Bool { get }
    func terminate()
    func forceKill()
}
@MainActor public protocol ProcessLaunching {
    func launch(_ specification: ProcessSpecification,
                output: @escaping @MainActor (Data) -> Void,
                exited: @escaping @MainActor (Int32) -> Void) throws -> ChildProcess
}

@MainActor private final class FoundationChild: ChildProcess {
    let process: Process
    let guardsBridge: Bool
    init(_ process: Process, guarded: Bool) { self.process = process; guardsBridge = guarded }
    var pid: Int32 { process.processIdentifier }
    var isRunning: Bool { process.isRunning }
    func terminate() { if process.isRunning { process.terminate() } }
    func forceKill() {
        // The guard owns Python and must stay alive to reap it.
        if process.isRunning && !guardsBridge { _ = kill(pid, SIGKILL) }
    }
}

@MainActor public struct FoundationProcessLauncher: ProcessLaunching {
    public enum Mode { case guarded(hostExecutable: String, hostPID: Int32), direct }
    private let mode: Mode
    public init(mode: Mode = .guarded(hostExecutable: CommandLine.arguments[0], hostPID: ProcessInfo.processInfo.processIdentifier)) {
        self.mode = mode
    }
    public func launch(_ spec: ProcessSpecification, output: @escaping @MainActor (Data) -> Void,
                       exited: @escaping @MainActor (Int32) -> Void) throws -> ChildProcess {
        let process = Process()
        let guarded: Bool
        switch mode {
        case let .guarded(executable, hostPID):
            process.executableURL = URL(fileURLWithPath: executable)
            process.arguments = ["--bridge-guard", String(hostPID), "--", spec.executable] + spec.arguments
            guarded = true
        case .direct:
            process.executableURL = URL(fileURLWithPath: spec.executable)
            process.arguments = spec.arguments
            guarded = false
        }
        process.currentDirectoryURL = URL(fileURLWithPath: spec.directory)
        process.environment = spec.environment
        process.standardInput = FileHandle.nullDevice
        let pipe = Pipe()
        process.standardOutput = pipe; process.standardError = pipe
        try process.run()
        // Close our writer: EOF must mean all child output has been collected.
        try? pipe.fileHandleForWriting.close()
        Task.detached {
            while true {
                let data = pipe.fileHandleForReading.availableData
                if data.isEmpty { break }
                await output(data)
            }
            process.waitUntilExit()
            try? pipe.fileHandleForReading.close()
            let code = process.terminationReason == .uncaughtSignal ? -process.terminationStatus : process.terminationStatus
            await exited(code)
        }
        return FoundationChild(process, guarded: guarded)
    }
}

@MainActor public protocol HostClock {
    var now: TimeInterval { get }
    func sleep(seconds: TimeInterval) async throws
}
@MainActor public struct SystemHostClock: HostClock {
    public init() {}
    public var now: TimeInterval { ProcessInfo.processInfo.systemUptime }
    public func sleep(seconds: TimeInterval) async throws {
        try await Task.sleep(nanoseconds: UInt64(max(0, seconds) * 1_000_000_000))
    }
}

@MainActor public final class BridgeLog {
    public let url: URL
    public let capacity: Int
    private var lines: [String] = []
    private var pending = Data()
    private var handle: FileHandle?
    public init(url: URL, capacity: Int = 2000) { self.url = url; self.capacity = max(1, capacity) }
    public func open() throws {
        guard handle == nil else { return }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: url.path) {
            guard FileManager.default.createFile(atPath: url.path, contents: nil) else { throw HostError("Cannot create \(url.path)") }
        }
        handle = try FileHandle(forWritingTo: url)
        try handle?.seekToEnd()
    }
    public func append(_ data: Data) throws {
        try open()
        try handle?.write(contentsOf: data)
        pending.append(data)
        while let newline = pending.firstIndex(of: 10) {
            add(String(decoding: pending[..<newline], as: UTF8.self).trimmingCharacters(in: CharacterSet(charactersIn: "\r")))
            pending.removeSubrange(...newline)
        }
    }
    public func finish() {
        if !pending.isEmpty { add(String(decoding: pending, as: UTF8.self)); pending.removeAll() }
        try? handle?.synchronize()
    }
    public func tail(lines count: Int) -> [String] { Array(lines.suffix(max(0, min(capacity, count)))) }
    private func add(_ line: String) {
        lines.append(line)
        if lines.count > capacity { lines.removeFirst(lines.count - capacity) }
    }
    deinit { try? handle?.close() }
}

public enum PortTransport: String, Equatable { case tcp, udp }
public struct BridgePort: Equatable {
    public let port: UInt16
    public let transport: PortTransport
    public init(_ port: UInt16, _ transport: PortTransport) { self.port = port; self.transport = transport }
    public static func required(by settings: HostSettings) throws -> [BridgePort] {
        var ports = [BridgePort(UInt16(settings.uiURL.port ?? 80), .tcp)]
        let args = settings.bridgeArguments
        func value(_ name: String) throws -> String? {
            var found: String?
            for (index, arg) in args.enumerated() {
                if arg.hasPrefix(name + "=") { found = String(arg.dropFirst(name.count + 1)) }
                if arg == name {
                    guard index + 1 < args.count else { throw HostError("Missing value for \(name)") }
                    found = args[index + 1]
                }
            }
            return found
        }
        if let listen = try value("--listen") {
            guard let tail = listen.split(separator: ":").last, let port = UInt16(tail), port > 0 else {
                throw HostError("Invalid --listen port")
            }
            ports.append(BridgePort(port, .udp))
        }
        if let ui = try value("--ui-port") {
            guard let port = UInt16(ui), port > 0 else { throw HostError("Invalid --ui-port") }
            let endpoint = BridgePort(port, .tcp)
            if !ports.contains(endpoint) { ports.append(endpoint) }
        }
        return ports
    }
}
public protocol PortChecking { func busyPort(in ports: [BridgePort]) throws -> (UInt16, Int32?)? }
public struct BindPortChecker: PortChecking {
    public init() {}
    public func busyPort(in ports: [BridgePort]) throws -> (UInt16, Int32?)? {
        for endpoint in ports {
            let fd = socket(AF_INET, endpoint.transport == .tcp ? SOCK_STREAM : SOCK_DGRAM, 0)
            guard fd >= 0 else { throw HostError("socket: \(String(cString: strerror(errno)))") }
            defer { close(fd) }
            // TCP TIME_WAIT is not a listener. No SO_REUSEPORT, including UDP.
            if endpoint.transport == .tcp {
                var reuse: Int32 = 1
                _ = setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse, socklen_t(MemoryLayout.size(ofValue: reuse)))
            }
            var address = sockaddr_in()
            address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
            address.sin_family = sa_family_t(AF_INET)
            address.sin_port = endpoint.port.bigEndian
            address.sin_addr.s_addr = inet_addr("127.0.0.1")
            let result = withUnsafePointer(to: &address) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) }
            }
            if result != 0 {
                let code = errno
                if code == EADDRINUSE { return (endpoint.port, owner(endpoint)) }
                throw HostError("bind 127.0.0.1:\(endpoint.port): \(String(cString: strerror(code))) (errno \(code))")
            }
        }
        return nil
    }
    private func owner(_ port: BridgePort) -> Int32? {
        let args = port.transport == .tcp ? ["-nP", "-iTCP:\(port.port)", "-sTCP:LISTEN", "-t"] : ["-nP", "-iUDP:\(port.port)", "-t"]
        return (try? ProcessInspection.command("/usr/sbin/lsof", args))?.split(whereSeparator: { $0.isWhitespace }).compactMap { Int32($0) }.first
    }
}

public enum ProcessInspection {
    public static func isAlive(_ pid: Int32) -> Bool { pid > 1 && (kill(pid, 0) == 0 || errno == EPERM) }
    public static func command(_ executable: String, _ arguments: [String]) throws -> String {
        let task = Process(); let output = Pipe(); let errors = Pipe()
        task.executableURL = URL(fileURLWithPath: executable); task.arguments = arguments
        task.standardInput = FileHandle.nullDevice; task.standardOutput = output; task.standardError = errors
        do { try task.run() }
        catch { throw HostError("Cannot run \(executable): \(error.localizedDescription)") }
        let data = output.fileHandleForReading.readDataToEndOfFile()
        let error = errors.fileHandleForReading.readDataToEndOfFile()
        task.waitUntilExit()
        guard task.terminationStatus == 0 else {
            throw HostError("\(executable): \(String(decoding: error, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)) (exit \(task.terminationStatus))")
        }
        return String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
