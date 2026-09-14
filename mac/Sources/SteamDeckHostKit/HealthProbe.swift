import Foundation

public protocol HealthTransport {
    func get(_ request: URLRequest) async throws -> (Data, Int)
}
public struct URLSessionHealthTransport: HealthTransport {
    private let session: URLSession
    public init(session: URLSession = .shared) { self.session = session }
    public func get(_ request: URLRequest) async throws -> (Data, Int) {
        let (data, response) = try await session.data(for: request)
        return (data, (response as? HTTPURLResponse)?.statusCode ?? 0)
    }
}
public protocol HealthChecking { func check(uiURL: URL) async -> HealthResult }
public struct HealthProbe: HealthChecking {
    private let transport: HealthTransport
    public init(transport: HealthTransport = URLSessionHealthTransport()) { self.transport = transport }
    public func check(uiURL: URL) async -> HealthResult {
        var request = URLRequest(url: uiURL.appendingPathComponent("api/settings"), timeoutInterval: 1)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        do {
            let (data, status) = try await transport.get(request)
            guard status == 200 else { return .unhealthy("HTTP \(status)") }
            guard (try? JSONSerialization.jsonObject(with: data)) is [String: Any] else {
                return .unhealthy("Expected a JSON object from /api/settings")
            }
            return .healthy
        } catch { return .unhealthy(error.localizedDescription) }
    }
}
