import Foundation
import Testing
@testable import SteamDeckHostKit

@MainActor private final class ControlFixture {
    let scratch: Scratch
    let launcher = FakeLauncher()
    let login = FakeLogin()
    let supervisor: BridgeSupervisor
    var windowCalls = 0
    var quitCalls = 0
    var stoppedWhenQuit = false
    lazy var controller = HostController(supervisor: supervisor, loginItem: login, openWindow: { [unowned self] in windowCalls += 1 }, quit: { [unowned self] in
        quitCalls += 1; stoppedWhenQuit = supervisor.state == .stopped && launcher.children.allSatisfy { !$0.isRunning }
    })
    init() throws {
        scratch = try Scratch()
        supervisor = BridgeSupervisor(settings: try HostSettings(values: ["future": ["keep": true]]), paths: scratch.paths,
            launcher: launcher, ports: FreePorts(), probe: FixedHealth(), reaper: NoOrphan())
    }
    func cleanup() async { await supervisor.stop(); scratch.cleanup() }
}

@Suite(.serialized) @MainActor struct ControlTests {
    private func request(_ port: UInt16, _ method: String, _ path: String, _ body: String? = nil) async throws -> (Int, [String: Any]) {
        var req = URLRequest(url: URL(string: "http://127.0.0.1:\(port)\(path)")!, timeoutInterval: 12)
        req.httpMethod = method; req.httpBody = body.map { Data($0.utf8) }
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let (data, response) = try await URLSession.shared.data(for: req)
        let http = try #require(response as? HTTPURLResponse)
        #expect(http.value(forHTTPHeaderField: "Content-Type") == "application/json")
        #expect(http.value(forHTTPHeaderField: "Content-Length") == String(data.count))
        let json = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        return (http.statusCode, json)
    }
    @Test func ephemeralHTTPServerEveryRouteHappyPathAndErrors() async throws {
        let f = try ControlFixture()
        let server = try ControlServer(controller: f.controller, port: 0)
        try await server.start()
        defer { server.stop(); f.scratch.cleanup() }
        let port = try #require(server.port)
        #expect(port > 0 && server.bindAddress == "127.0.0.1")
        var visited: Set<ControllerAction> = []
        for route in RouteTable.routes {
            let body: String?
            switch route.action {
            case .setLoginItem: body = "{\"enabled\":true}"
            case .updateSettings: body = "{\"control_port\":8877,\"autostart_bridge\":false}"
            default: body = nil
            }
            if route.action == .logTail { try f.supervisor.log.append(Data("one\ntwo\nthree\n".utf8)) }
            let (status, json) = try await request(port, route.method, route.path + (route.action == .logTail ? "?lines=2" : ""), body)
            #expect(status == (route.action == .quit ? 202 : 200), "\(route.method) \(route.path): \(json)")
            visited.insert(route.action)
            switch route.action {
            case .status: #expect(json["state"] as? String == "stopped" && json["healthy"] as? Bool == false)
            case .startBridge:
                #expect(f.launcher.children.count == 1 && f.launcher.children[0].isRunning)
                #expect(json["pid"] as? Int32 == f.launcher.children[0].pid)
            case .stopBridge:
                #expect(json["state"] as? String == "stopped")
                #expect(!f.launcher.children[0].isRunning && f.launcher.children[0].signals == [SIGTERM])
            case .restartBridge: #expect(f.launcher.children.count == 2 && f.launcher.children[1].isRunning)
            case .logTail: #expect(json["lines"] as? [String] == ["two", "three"])
            case .loginItemStatus: #expect(json["status"] as? String == "notRegistered")
            case .setLoginItem: #expect(json["status"] as? String == "enabled" && f.login.writes == [true])
            case .settings: #expect((json["future"] as? [String: Bool])?["keep"] == true)
            case .updateSettings:
                #expect(json["control_port"] as? Int == 8877 && json["autostart_bridge"] as? Bool == false)
                let saved = try HostSettings.load(from: f.scratch.paths.settings)
                #expect(saved.controlPort == 8877 && !saved.autostartBridge)
                #expect((saved.json["future"] as? [String: Bool])?["keep"] == true)
                #expect(f.supervisor.settings.controlPort == 8877)
            case .openWindow: #expect(json["ok"] as? Bool == true && f.windowCalls == 1)
            case .quit:
                #expect(json["quitting"] as? Bool == true)
                try await eventually { f.quitCalls == 1 }
                #expect(f.stoppedWhenQuit)
            }
        }
        #expect(visited == Set(ControllerAction.allCases))
        for (method, path, body, expected) in [
            ("PUT", "/host/settings", "{", 400), ("GET", "/missing", "", 404),
            ("DELETE", "/host/status", "", 405), ("PUT", "/host/login-item", "{\"enabled\":1}", 400),
            ("PUT", "/host/settings", "{\"control_port\":0}", 400), ("GET", "/host/log?lines=-1", "", 400),
            ("GET", "/host/log?lines=abc", "", 400), ("GET", "/host/log?lines=2&lines=3", "", 400)
        ] {
            let (status, json) = try await request(port, method, path, body.isEmpty ? nil : body)
            #expect(status == expected && json["error"] is String)
        }
        #expect(try HostSettings.load(from: f.scratch.paths.settings).controlPort == 8877)
        await f.supervisor.stop()
    }
    @Test func nonLoopbackBindIsRefusedBeforeOpeningSocket() throws {
        let f = try ControlFixture(); defer { f.scratch.cleanup() }
        for address in ["0.0.0.0", "::", "::1", "localhost", "192.168.1.2", "127.0.0.2"] {
            #expect(throws: HostError("Control API must bind to 127.0.0.1 only")) { try ControlServer(controller: f.controller, bindAddress: address, port: 0) }
        }
    }
    @Test func parserRetainsSplitBodyAndRefusesSmugglingAndOversizeBodies() throws {
        let prefix = "PUT /host/settings HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 2\r\n\r\n"
        #expect(try HTTPRequestParser.parse(Data((prefix + "{").utf8)) == nil)
        let complete = try #require(try HTTPRequestParser.parse(Data((prefix + "{}").utf8)))
        #expect(complete.method == "PUT" && complete.path == "/host/settings" && complete.body == Data("{}".utf8))
        let bad = [
            "POST /host/quit HTTP/1.1\r\nContent-Length: 65537\r\n\r\n",
            "POST /host/quit HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n",
            "POST /host/quit HTTP/1.1\r\nContent-Length: 0\r\nContent-Length: 2\r\n\r\n",
            "POST /host/quit HTTP/1.1\r\nContent-Length: -1\r\n\r\n",
            "POST /host/quit HTTP/1.1\r\nContent-Length: +2\r\n\r\n",
            "POST /host/quit HTTP/1.0\r\n\r\n", prefix + "{}extra",
            "GET / HTTP/1.1\r\n" + String(repeating: "x", count: 17000)
        ]
        for raw in bad { #expect(throws: HTTPFailure.self) { try HTTPRequestParser.parse(Data(raw.utf8)) } }
    }
    @Test func rawHTTPFramingErrorsAreJSONAndBodyCapIsEnforcedOnWire() async throws {
        let f = try ControlFixture(), server = try ControlServer(controller: f.controller, port: 0)
        try await server.start(); defer { server.stop(); f.scratch.cleanup() }
        let port = try #require(server.port)
        for (raw, code) in [
            ("PUT /host/settings HTTP/1.1\r\nHost: localhost\r\nContent-Length: 65537\r\n\r\n", 413),
            ("PUT /host/settings HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n", 400),
            ("GET /host/status HTTP/1.1\r\nContent-Length: -1\r\n\r\n", 400)
        ] {
            let bytes = try await rawExchange(port: port, text: raw)
            let text = String(decoding: bytes, as: UTF8.self)
            #expect(text.hasPrefix("HTTP/1.1 \(code) "))
            let body = try #require(text.components(separatedBy: "\r\n\r\n").last)
            #expect((try JSONSerialization.jsonObject(with: Data(body.utf8)) as? [String: String])?["error"] != nil)
        }
        do { _ = try await rawExchange(port: port, text: "GET /host/status HTTP/1.1\r\n\r\n", address: "127.0.0.2"); Issue.record("Listener accepted a different bind address") }
        catch { #expect(error.localizedDescription.contains("connect")) }
    }
    @Test func loginFakeAndControllerPropagateApprovalStatesAndErrors() throws {
        let f = try ControlFixture(); defer { f.scratch.cleanup() }
        for status in LoginItemStatus.allCases {
            f.login.value = status; #expect(f.controller.loginItemStatus()["status"] as? String == status.rawValue)
        }
        _ = try f.controller.setLoginItem(enabled: true)
        _ = try f.controller.setLoginItem(enabled: false)
        #expect(f.login.writes == [true, false] && f.login.value == .notRegistered)
        f.login.failure = HostError("registration refused")
        #expect(throws: HostError("registration refused")) { try f.controller.setLoginItem(enabled: true) }
    }
    @Test func routerEveryWrongMethodAndQuitDefersUntilResponseCompletion() async throws {
        let f = try ControlFixture(); defer { f.scratch.cleanup() }
        let router = ControlRouter(controller: f.controller)
        for route in RouteTable.routes {
            let response = await router.handle(try ControlRequest(method: "PATCH", target: route.path))
            #expect(response.status == 405 && response.json["error"] is String)
        }
        _ = await f.controller.startBridge()
        let reply = await router.handle(try ControlRequest(method: "POST", target: "/host/quit"))
        #expect(reply.status == 202 && f.quitCalls == 0 && f.launcher.children[0].isRunning)
        await reply.afterSend?()
        #expect(f.quitCalls == 1 && f.stoppedWhenQuit)
    }
}

private func rawExchange(port: UInt16, text: String, address: String = "127.0.0.1") async throws -> Data {
    try await Task.detached {
        let descriptor = socket(AF_INET, SOCK_STREAM, 0)
        guard descriptor >= 0 else { throw HostError("raw socket errno \(errno)") }
        defer { close(descriptor) }
        var timeout = timeval(tv_sec: 3, tv_usec: 0)
        _ = setsockopt(descriptor, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout.size(ofValue: timeout)))
        var addr = sockaddr_in(); addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET); addr.sin_port = port.bigEndian; addr.sin_addr.s_addr = inet_addr(address)
        _ = fcntl(descriptor, F_SETFL, O_NONBLOCK)
        let connected = withUnsafePointer(to: &addr) { p in
            p.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(descriptor, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) }
        }
        if connected != 0 {
            guard errno == EINPROGRESS else { throw HostError("raw connect \(address): errno \(errno)") }
            var pending = pollfd(fd: descriptor, events: Int16(POLLOUT), revents: 0)
            guard poll(&pending, 1, 1000) > 0 else { throw HostError("raw connect \(address): timed out") }
            var error: Int32 = 0, size = socklen_t(MemoryLayout<Int32>.size)
            _ = getsockopt(descriptor, SOL_SOCKET, SO_ERROR, &error, &size)
            guard error == 0 else { throw HostError("raw connect \(address): errno \(error)") }
        }
        _ = fcntl(descriptor, F_SETFL, 0)
        let bytes = Array(text.utf8)
        var offset = 0
        while offset < bytes.count {
            let count = bytes.withUnsafeBytes { send(descriptor, $0.baseAddress!.advanced(by: offset), bytes.count - offset, 0) }
            guard count > 0 else { throw HostError("raw send errno \(errno)") }; offset += count
        }
        var result = Data(), buffer = [UInt8](repeating: 0, count: 8192)
        while true {
            let count = recv(descriptor, &buffer, buffer.count, 0)
            if count == 0 { return result }
            guard count > 0 else { throw HostError("raw recv errno \(errno)") }
            result.append(contentsOf: buffer.prefix(count))
        }
    }.value
}
