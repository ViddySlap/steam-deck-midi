import Foundation
import Network

public struct HTTPFailure: Error {
    public let status: Int
    public let message: String
    public init(_ status: Int, _ message: String) { self.status = status; self.message = message }
}
public struct ControlRequest {
    public let method: String
    public let path: String
    public let query: [URLQueryItem]
    public let body: Data
    public init(method: String, target: String, body: Data = Data()) throws {
        guard target.hasPrefix("/"), !target.hasPrefix("//"), let components = URLComponents(string: target),
              components.fragment == nil else { throw HTTPFailure(400, "Invalid request target") }
        self.method = method; self.path = components.path; self.query = components.queryItems ?? []; self.body = body
    }
    public func object(required: Bool = false) throws -> [String: Any] {
        if body.isEmpty && !required { return [:] }
        guard let object = try? JSONSerialization.jsonObject(with: body) as? [String: Any] else {
            throw HTTPFailure(400, "Expected a JSON object")
        }
        return object
    }
}
public struct ControlResponse {
    public let status: Int
    public let json: [String: Any]
    /// Quit executes only after the response has been sent.
    public let afterSend: (@MainActor @Sendable () async -> Void)?
    public init(status: Int = 200, json: [String: Any], afterSend: (@MainActor @Sendable () async -> Void)? = nil) {
        self.status = status; self.json = json; self.afterSend = afterSend
    }
    public func wireData() throws -> Data {
        let body = try JSONSerialization.data(withJSONObject: json, options: .sortedKeys)
        let reason = [200: "OK", 202: "Accepted", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed",
                      408: "Request Timeout", 413: "Payload Too Large", 431: "Request Header Fields Too Large", 500: "Internal Server Error"][status] ?? "Error"
        let header = "HTTP/1.1 \(status) \(reason)\r\nContent-Type: application/json\r\nContent-Length: \(body.count)\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n"
        return Data(header.utf8) + body
    }
}

public enum HTTPRequestParser {
    public static let maximumBody = 64 * 1024
    public static let maximumHeader = 16 * 1024
    public static func parse(_ bytes: Data) throws -> ControlRequest? {
        guard let separator = bytes.range(of: Data("\r\n\r\n".utf8)) else {
            if bytes.count > maximumHeader { throw HTTPFailure(431, "Headers exceed 16 KB") }
            return nil
        }
        guard separator.lowerBound <= maximumHeader,
              let header = String(data: bytes[..<separator.lowerBound], encoding: .utf8) else { throw HTTPFailure(400, "Invalid headers") }
        let lines = header.components(separatedBy: "\r\n")
        let first = lines[0].split(separator: " ", omittingEmptySubsequences: false)
        guard first.count == 3, first[2] == "HTTP/1.1", !first[0].isEmpty else { throw HTTPFailure(400, "Expected HTTP/1.1 request") }
        var headers: [String: String] = [:]
        for line in lines.dropFirst() {
            guard let colon = line.firstIndex(of: ":"), !line.hasPrefix(" "), !line.hasPrefix("\t") else { throw HTTPFailure(400, "Invalid header") }
            let key = String(line[..<colon]).lowercased()
            guard !key.isEmpty, headers[key] == nil else { throw HTTPFailure(400, "Duplicate or empty header") }
            headers[key] = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
        }
        guard headers["transfer-encoding"] == nil else { throw HTTPFailure(400, "Only Content-Length bodies are supported") }
        var length = 0
        if let value = headers["content-length"] {
            guard !value.isEmpty, value.allSatisfy({ $0.isASCII && $0.isNumber }), let number = Int(value), number >= 0 else {
                throw HTTPFailure(400, "Invalid Content-Length")
            }
            length = number
        }
        guard length <= maximumBody else { throw HTTPFailure(413, "Body exceeds 64 KB") }
        let available = bytes.count - separator.upperBound
        guard available >= length else { return nil }
        guard available == length else { throw HTTPFailure(400, "Unexpected bytes after request body") }
        return try ControlRequest(method: String(first[0]), target: String(first[1]), body: bytes.subdata(in: separator.upperBound..<bytes.count))
    }
}

@MainActor public final class ControlRouter {
    public let controller: HostController
    public init(controller: HostController) { self.controller = controller }
    public func handle(_ request: ControlRequest) async -> ControlResponse {
        do {
            let paths = RouteTable.routes.filter { $0.path == request.path }
            guard !paths.isEmpty else { throw HTTPFailure(404, "Unknown path") }
            guard let route = paths.first(where: { $0.method == request.method }) else { throw HTTPFailure(405, "Method not allowed") }
            let body = try request.object(required: request.method == "PUT")
            let response: [String: Any]
            switch route.action {
            case .status: response = controller.status()
            case .startBridge: response = await controller.startBridge()
            case .stopBridge: response = await controller.stopBridge()
            case .restartBridge: response = await controller.restartBridge()
            case .logTail:
                let values = request.query.filter { $0.name == "lines" }
                guard values.count <= 1 else { throw HTTPFailure(400, "Duplicate lines parameter") }
                let count: Int
                if let item = values.first {
                    guard let value = item.value, let number = Int(value) else { throw HTTPFailure(400, "lines must be an integer") }
                    count = number
                } else { count = 200 }
                response = try controller.logTail(lines: count)
            case .loginItemStatus: response = controller.loginItemStatus()
            case .setLoginItem:
                guard body.count == 1, let enabled = body["enabled"], HostSettings.isBool(enabled) else {
                    throw HTTPFailure(400, "Expected {\"enabled\": boolean}")
                }
                response = try controller.setLoginItem(enabled: enabled as! Bool)
            case .settings: response = controller.settings()
            case .updateSettings: response = try controller.updateSettings(body)
            case .openWindow: response = controller.openWindow()
            case .quit:
                return ControlResponse(status: 202, json: ["quitting": true], afterSend: { [controller] in await controller.quit() })
            }
            return ControlResponse(json: response)
        } catch let error as HTTPFailure { return ControlResponse(status: error.status, json: ["error": error.message]) }
        catch let error as HostError { return ControlResponse(status: 400, json: ["error": error.message]) }
        catch { return ControlResponse(status: 500, json: ["error": error.localizedDescription]) }
    }
}

@MainActor public final class ControlServer {
    public private(set) var port: UInt16?
    public let bindAddress: String
    private let requestedPort: UInt16
    private let router: ControlRouter
    private var listener: NWListener?
    private var clients: [UUID: NWConnection] = [:]
    private var timeouts: [UUID: Task<Void, Never>] = [:]
    public init(controller: HostController, bindAddress: String = "127.0.0.1", port: UInt16 = 7724) throws {
        guard bindAddress == "127.0.0.1" else { throw HostError("Control API must bind to 127.0.0.1 only") }
        self.bindAddress = bindAddress; self.requestedPort = port; self.router = ControlRouter(controller: controller)
    }
    /// Port zero is for ephemeral test listeners; host.json requires a real port.
    public func start() async throws {
        guard listener == nil else { return }
        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = .hostPort(host: NWEndpoint.Host(bindAddress), port: NWEndpoint.Port(rawValue: requestedPort)!)
        let newListener = try NWListener(using: parameters)
        listener = newListener
        newListener.newConnectionHandler = { [weak self] connection in Task { @MainActor in self?.accept(connection) } }
        do {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                var finished = false
                newListener.stateUpdateHandler = { [weak self] state in
                    Task { @MainActor in
                        guard !finished else { return }
                        switch state {
                        case .ready:
                            finished = true; self?.port = newListener.port?.rawValue; continuation.resume()
                        case let .failed(error): finished = true; continuation.resume(throwing: HostError("Control listener: \(error)"))
                        case .cancelled: finished = true; continuation.resume(throwing: HostError("Control listener cancelled"))
                        default: break
                        }
                    }
                }
                newListener.start(queue: .main)
            }
        } catch { stop(); throw error }
    }
    public func stop() {
        listener?.cancel(); listener = nil; port = nil
        let active = Array(clients.keys)
        active.forEach { close($0) }
    }
    private func accept(_ connection: NWConnection) {
        let id = UUID(); clients[id] = connection
        connection.start(queue: .main)
        timeouts[id] = Task { [weak self] in
            do { try await Task.sleep(nanoseconds: 5_000_000_000) } catch { return }
            self?.reply(ControlResponse(status: 408, json: ["error": "Request timed out"]), id: id)
        }
        receive(id, bytes: Data())
    }
    private func receive(_ id: UUID, bytes: Data) {
        clients[id]?.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, done, error in
            Task { @MainActor in
                guard let self, self.clients[id] != nil else { return }
                if error != nil { self.close(id); return }
                var accumulated = bytes; if let data { accumulated.append(data) }
                do {
                    if let request = try HTTPRequestParser.parse(accumulated) {
                        self.timeouts[id]?.cancel(); self.timeouts[id] = nil
                        self.reply(await self.router.handle(request), id: id)
                    } else if done { self.reply(ControlResponse(status: 400, json: ["error": "Incomplete request"]), id: id) }
                    else { self.receive(id, bytes: accumulated) }
                } catch let error as HTTPFailure { self.reply(ControlResponse(status: error.status, json: ["error": error.message]), id: id) }
                catch { self.reply(ControlResponse(status: 400, json: ["error": error.localizedDescription]), id: id) }
            }
        }
    }
    private func reply(_ response: ControlResponse, id: UUID) {
        guard let connection = clients[id], let bytes = try? response.wireData() else { close(id); return }
        timeouts[id]?.cancel(); timeouts[id] = nil
        let afterSend = response.afterSend
        connection.send(content: bytes, completion: .contentProcessed { [weak self] _ in
            Task { @MainActor in
                self?.close(id)
                await afterSend?()
            }
        })
    }
    private func close(_ id: UUID) {
        timeouts.removeValue(forKey: id)?.cancel()
        clients.removeValue(forKey: id)?.cancel()
    }
}
