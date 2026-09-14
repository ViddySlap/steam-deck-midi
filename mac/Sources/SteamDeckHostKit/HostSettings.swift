import Foundation

public enum HostKit { public static let version = "0.1.0" }

public struct HostError: Error, LocalizedError, Equatable {
    public let message: String
    public init(_ message: String) { self.message = message }
    public var errorDescription: String? { message }
}

public struct HostPaths: Sendable {
    public let appSupport: URL
    public let logs: URL
    public init(appSupport: URL = FileManager.default.homeDirectoryForCurrentUser
                    .appendingPathComponent("Library/Application Support/SteamDeckMIDI"),
                logs: URL = FileManager.default.homeDirectoryForCurrentUser
                    .appendingPathComponent("Library/Logs/SteamDeckMIDI")) {
        self.appSupport = appSupport
        self.logs = logs
    }
    public var settings: URL { appSupport.appendingPathComponent("host.json") }
    public var pidFile: URL { appSupport.appendingPathComponent("bridge.pid") }
    public var bridgeLog: URL { logs.appendingPathComponent("bridge.log") }
}

/// Same-directory temporary file and POSIX rename, including replacement.
public enum AtomicFile {
    public static func write(_ data: Data, to url: URL) throws {
        let directory = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let temporary = directory.appendingPathComponent(".\(url.lastPathComponent).\(UUID().uuidString).tmp")
        defer { try? FileManager.default.removeItem(at: temporary) }
        try data.write(to: temporary, options: .withoutOverwriting)
        guard rename(temporary.path, url.path) == 0 else {
            throw HostError("Cannot replace \(url.path): \(String(cString: strerror(errno)))")
        }
    }
}

public struct HostSettings {
    public static let defaultRoot = "/Users/viddyslap/Documents/project-workspaces/steam-deck-midi"
    public static let defaultArguments = ["-m", "windows.win_recv", "--listen", "0.0.0.0:45123",
        "--map", "config/windows_midi_map.json", "--midi-port", "IAC Driver DECK_IN",
        "--feedback-port", "IAC Driver DECK_OUT", "--pulse-port", "IAC Driver PULSE_OUT",
        "--timeout", "2.0", "--ui-port", "7723"]
    public static let defaultEnvironment = ["PYSTRAY_BACKEND": "dummy", "BROWSER": "/usr/bin/true"]
    private var raw: [String: Any]

    public init(values: [String: Any] = [:]) throws {
        raw = values
        try validate()
    }
    public var bridgeRoot: String { raw["bridge_root"] as? String ?? Self.defaultRoot }
    public var python: String { raw["python"] as? String ?? bridgeRoot + "/.venv/bin/python" }
    public var bridgeArguments: [String] { raw["bridge_args"] as? [String] ?? Self.defaultArguments }
    // A present object replaces the defaults: {} deliberately removes both overrides.
    public var bridgeEnvironment: [String: String] { raw["bridge_env"] as? [String: String] ?? Self.defaultEnvironment }
    public var uiURL: URL { URL(string: raw["ui_url"] as? String ?? "http://127.0.0.1:7723")! }
    public var controlPort: UInt16 { UInt16((raw["control_port"] as? NSNumber)?.intValue ?? 7724) }
    public var autostartBridge: Bool { raw["autostart_bridge"] as? Bool ?? true }
    public var json: [String: Any] {
        var result = raw
        let defaults: [String: Any] = ["bridge_root": bridgeRoot, "python": python,
            "bridge_args": bridgeArguments, "bridge_env": bridgeEnvironment,
            "ui_url": uiURL.absoluteString, "control_port": Int(controlPort), "autostart_bridge": autostartBridge]
        defaults.forEach { result[$0.key] = $0.value }
        return result
    }
    public func updating(_ partial: [String: Any]) throws -> HostSettings {
        try HostSettings(values: raw.merging(partial) { _, new in new })
    }
    public static func load(from url: URL) throws -> HostSettings {
        do {
            let data: Data
            do { data = try Data(contentsOf: url) }
            catch let error as CocoaError where error.code == .fileReadNoSuchFile { return try HostSettings() }
            guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                throw HostError("Expected a JSON object")
            }
            return try HostSettings(values: object)
        } catch { throw HostError("Cannot load \(url.path): \(error.localizedDescription)") }
    }
    public func save(to url: URL) throws {
        // Save the original object so defaults remain dependent on bridge_root.
        try AtomicFile.write(JSONSerialization.data(withJSONObject: raw, options: [.prettyPrinted, .sortedKeys]), to: url)
    }
    private func validate() throws {
        guard JSONSerialization.isValidJSONObject(raw) else { throw HostError("Settings must contain JSON values") }
        for key in ["bridge_root", "python", "ui_url"] where raw[key] != nil {
            guard let value = raw[key] as? String, !value.isEmpty else { throw HostError("\(key) must be a nonempty string") }
        }
        for key in ["bridge_root", "python"] where raw[key] != nil {
            guard (raw[key] as! String).hasPrefix("/") else { throw HostError("\(key) must be an absolute path") }
        }
        if let value = raw["bridge_args"], !(value is [String]) { throw HostError("bridge_args must be an array of strings") }
        if let value = raw["bridge_env"], !(value is [String: String]) { throw HostError("bridge_env must be an object of strings") }
        if let value = raw["autostart_bridge"], !Self.isBool(value) { throw HostError("autostart_bridge must be a boolean") }
        if let value = raw["control_port"] {
            guard let number = value as? NSNumber, !Self.isBool(value), number.doubleValue == Double(number.intValue),
                  (1...65535).contains(number.intValue) else { throw HostError("control_port must be an integer from 1 to 65535") }
        }
        if let value = raw["ui_url"] as? String {
            guard let url = URL(string: value), url.scheme == "http", url.host == "127.0.0.1",
                  url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
                  (1...65535).contains(url.port ?? 80) else { throw HostError("ui_url must be an HTTP URL on 127.0.0.1") }
        }
    }
    public static func isBool(_ value: Any) -> Bool {
        guard let number = value as? NSNumber else { return false }
        return String(cString: number.objCType) == "c"
    }
}
