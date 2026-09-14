import Foundation

public enum ControllerAction: String, CaseIterable, Sendable {
    case status, startBridge, stopBridge, restartBridge, logTail, loginItemStatus,
         setLoginItem, settings, updateSettings, openWindow, quit
}
public struct ControlRoute: Equatable, Sendable {
    public let method: String
    public let path: String
    public let action: ControllerAction
    public init(_ method: String, _ path: String, _ action: ControllerAction) {
        self.method = method; self.path = path; self.action = action
    }
}
public enum RouteTable {
    public static let routes: [ControlRoute] = [
        .init("GET", "/host/status", .status),
        .init("POST", "/host/bridge/start", .startBridge),
        .init("POST", "/host/bridge/stop", .stopBridge),
        .init("POST", "/host/bridge/restart", .restartBridge),
        .init("GET", "/host/log", .logTail),
        .init("GET", "/host/login-item", .loginItemStatus),
        .init("PUT", "/host/login-item", .setLoginItem),
        .init("GET", "/host/settings", .settings),
        .init("PUT", "/host/settings", .updateSettings),
        .init("POST", "/host/window/open", .openWindow),
        .init("POST", "/host/quit", .quit)
    ]
}
public struct HostMenuItem: Sendable {
    public let title: String
    public let route: ControlRoute
    public init(_ title: String, _ route: ControlRoute) { self.title = title; self.route = route }
}
public enum MenuModel {
    public static let items: [HostMenuItem] = [
        .init("Open Window", .init("POST", "/host/window/open", .openWindow)),
        .init("Start Bridge", .init("POST", "/host/bridge/start", .startBridge)),
        .init("Stop Bridge", .init("POST", "/host/bridge/stop", .stopBridge)),
        .init("Restart Bridge", .init("POST", "/host/bridge/restart", .restartBridge)),
        .init("Show Log", .init("GET", "/host/log", .logTail)),
        .init("Launch at Login", .init("PUT", "/host/login-item", .setLoginItem)),
        .init("Quit", .init("POST", "/host/quit", .quit))
    ]
}

@MainActor public final class HostController {
    public let supervisor: BridgeSupervisor
    public let paths: HostPaths
    private let loginItem: LoginItem
    private let windowHandler: () -> Void
    private let quitHandler: () -> Void
    private var configuration: HostSettings
    public var onSettingsChanged: ((HostSettings) -> Void)?
    public init(supervisor: BridgeSupervisor, loginItem: LoginItem,
                openWindow: @escaping () -> Void, quit: @escaping () -> Void) {
        self.supervisor = supervisor; self.paths = supervisor.paths
        self.configuration = supervisor.settings; self.loginItem = loginItem
        windowHandler = openWindow; quitHandler = quit
    }
    public func bootstrap() async throws {
        try await supervisor.reconcileOrphan()
        if configuration.autostartBridge { await supervisor.start() }
    }
    public func status() -> [String: Any] {
        var result = supervisor.state.json
        result["pid"] = supervisor.pid.map { $0 as Any } ?? NSNull()
        result["bridge_pid"] = supervisor.bridgePID.map { $0 as Any } ?? NSNull()
        result["healthy"] = supervisor.health == .healthy
        if case let .unhealthy(reason) = supervisor.health { result["health_error"] = reason }
        result["ui_url"] = supervisor.uiURL.absoluteString
        return result
    }
    public func startBridge() async -> [String: Any] { await supervisor.start(); return status() }
    public func stopBridge() async -> [String: Any] { await supervisor.stop(); return status() }
    public func restartBridge() async -> [String: Any] { await supervisor.restart(); return status() }
    public func logTail(lines: Int = 200) throws -> [String: Any] {
        guard (0...2000).contains(lines) else { throw HostError("lines must be an integer from 0 to 2000") }
        return ["lines": supervisor.log.tail(lines: lines), "path": paths.bridgeLog.path]
    }
    public func loginItemStatus() -> [String: Any] { ["status": loginItem.status().rawValue] }
    public func setLoginItem(enabled: Bool) throws -> [String: Any] { try loginItem.setEnabled(enabled); return loginItemStatus() }
    public func settings() -> [String: Any] { configuration.json }
    public func updateSettings(_ partial: [String: Any]) throws -> [String: Any] {
        let candidate = try configuration.updating(partial)
        _ = try BridgePort.required(by: candidate)
        try candidate.save(to: paths.settings)
        configuration = candidate
        supervisor.updateSettings(candidate)
        onSettingsChanged?(candidate)
        return settings()
    }
    public func openWindow() -> [String: Any] { windowHandler(); return ["ok": true] }
    public func quit() async { await supervisor.stop(); quitHandler() }
}
