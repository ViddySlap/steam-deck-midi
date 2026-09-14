import Foundation

public enum LaunchMode: String, Sendable { case window, background, cli }
public enum LaunchContext {
    /// arguments excludes argv[0]; bundlePath may be the bundle or executable path.
    public static func mode(arguments: [String], bundlePath: String) -> LaunchMode {
        if arguments == ["--background"] { return .background }
        if !arguments.isEmpty { return .cli }
        if bundlePath.hasSuffix(".app") { return .window }
        if let range = bundlePath.range(of: "/Contents/MacOS/"),
           bundlePath[..<range.lowerBound].hasSuffix(".app") { return .window }
        return .cli
    }
}

public enum BridgeState: Equatable, Sendable {
    case stopped, starting, running, stopping
    case crashed(exitCode: Int32, restarts: Int)
    case portBusy(port: UInt16, pid: Int32?)
    case failed(reason: String)
    public var json: [String: Any] {
        switch self {
        case .stopped: return ["state": "stopped"]
        case .starting: return ["state": "starting"]
        case .running: return ["state": "running"]
        case .stopping: return ["state": "stopping"]
        case let .crashed(code, restarts): return ["state": "crashed", "exit_code": code, "restarts": restarts]
        case let .portBusy(port, pid): return ["state": "port-busy", "port": Int(port), "pid": pid.map { $0 as Any } ?? NSNull()]
        case let .failed(reason): return ["state": "failed", "reason": reason]
        }
    }
}
public enum HealthResult: Equatable, Sendable { case healthy, unhealthy(String) }
public enum PageLoadResult: Equatable, Sendable { case loaded, failed(String) }
public enum ViewTone: String, Sendable { case neutral, progress, error }
public enum ViewState: Equatable, Sendable {
    case sentence(text: String, tone: ViewTone)
    case page(URL)
    public static func resolve(supervisorState: BridgeState, healthResult: HealthResult,
                               pageLoadResult: PageLoadResult? = nil, url: URL) -> ViewState {
        switch supervisorState {
        case .stopped: return .sentence(text: "Bridge is stopped.", tone: .neutral)
        case .starting: return .sentence(text: "Bridge is starting.", tone: .progress)
        case .stopping: return .sentence(text: "Bridge is stopping.", tone: .progress)
        case let .portBusy(port, pid):
            return .sentence(text: "Port \(port) is busy" + (pid.map { " (pid \($0))" } ?? " (owner unavailable)") + ".", tone: .error)
        case let .crashed(code, restarts):
            return .sentence(text: "Bridge crashed (exit \(code)); restart \(restarts) pending.", tone: .error)
        case let .failed(reason): return .sentence(text: "Bridge failed: \(reason).", tone: .error)
        case .running:
            if case let .unhealthy(reason) = healthResult { return .sentence(text: "Bridge health check failed: \(reason).", tone: .error) }
            if case let .failed(error) = pageLoadResult { return .sentence(text: "Bridge page could not load: \(error).", tone: .error) }
            return .page(url)
        }
    }
}

public enum LoginItemStatus: String, Sendable, CaseIterable { case enabled, requiresApproval, notRegistered, notFound }
@MainActor public protocol LoginItem: AnyObject {
    func status() -> LoginItemStatus
    func setEnabled(_ enabled: Bool) throws
}
