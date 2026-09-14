import Foundation
import Testing
@testable import SteamDeckHostKit

@Suite struct SettingsAndPresentationTests {
    @Test func defaultsMatchLauncherWithoutSectionOverride() throws {
        let value = try HostSettings()
        #expect(value.bridgeRoot == "/Users/viddyslap/Documents/project-workspaces/steam-deck-midi")
        #expect(value.python == value.bridgeRoot + "/.venv/bin/python")
        #expect(value.bridgeArguments == ["-m", "windows.win_recv", "--listen", "0.0.0.0:45123",
            "--map", "config/windows_midi_map.json", "--midi-port", "IAC Driver DECK_IN",
            "--feedback-port", "IAC Driver DECK_OUT", "--pulse-port", "IAC Driver PULSE_OUT",
            "--timeout", "2.0", "--ui-port", "7723"])
        #expect(!value.bridgeArguments.contains("--preset-section"))
        #expect(value.bridgeEnvironment == ["PYSTRAY_BACKEND": "dummy", "BROWSER": "/usr/bin/true"])
        #expect(value.uiURL.absoluteString == "http://127.0.0.1:7723")
        #expect(value.controlPort == 7724 && value.autostartBridge)
        let moved = try HostSettings(values: ["bridge_root": "/tmp/another"])
        #expect(moved.python == "/tmp/another/.venv/bin/python")
        #expect(try moved.updating(["bridge_env": [:]]).bridgeEnvironment.isEmpty)
        #expect(try moved.updating(["bridge_env": ["BROWSER": "/usr/bin/true"]]).bridgeEnvironment == ["BROWSER": "/usr/bin/true"])
    }
    @Test func settingsRoundTripAndAtomicReplacementPreserveUnknownKeys() throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let url = scratch.paths.settings
        #expect(try HostSettings.load(from: url).controlPort == 7724)
        #expect(!FileManager.default.fileExists(atPath: url.path))
        let original = try HostSettings(values: ["future": ["nested": [1, 2, 3]], "bridge_root": "/tmp/bridge"])
        try original.save(to: url)
        let openOldInode = try FileHandle(forReadingFrom: url); defer { try? openOldInode.close() }
        let modified = try HostSettings.load(from: url).updating(["control_port": 8811, "autostart_bridge": false])
        try modified.save(to: url)
        let disk = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        #expect((disk["future"] as? [String: [Int]])?["nested"] == [1, 2, 3])
        #expect(disk["control_port"] as? Int == 8811)
        #expect(try HostSettings.load(from: url).autostartBridge == false)
        let old = try #require(JSONSerialization.jsonObject(with: openOldInode.readToEnd()!) as? [String: Any])
        #expect(old["control_port"] == nil, "Existing inode stays unchanged; save must rename a new inode")
        #expect(try FileManager.default.contentsOfDirectory(atPath: scratch.paths.appSupport.path) == ["host.json"])
        #expect(!FileManager.default.fileExists(atPath: scratch.file("bridge").path))
    }
    @Test(arguments: ["{", "[]", "{\"control_port\":true}", "{\"bridge_env\":42}", "{\"ui_url\":\"http://evil.invalid\"}"])
    func malformedSettingsNameFileAndRemainByteIdentical(_ content: String) throws {
        let scratch = try Scratch(); defer { scratch.cleanup() }
        let url = scratch.file("host.json"), bytes = Data(content.utf8)
        try bytes.write(to: url)
        do { _ = try HostSettings.load(from: url); Issue.record("Malformed settings accepted") }
        catch { #expect(error.localizedDescription.contains(url.path)) }
        #expect(try Data(contentsOf: url) == bytes)
    }
    @Test func invalidTypedSettingsAreRefused() throws {
        let bad: [[String: Any]] = [["control_port": 0], ["control_port": 65536], ["control_port": 1.5],
            ["autostart_bridge": 1], ["bridge_args": [1]], ["bridge_root": "relative"], ["python": "python"], ["ui_url": "oops"]]
        for value in bad { #expect(throws: (any Error).self) { try HostSettings(values: value) } }
    }
    @Test func portsComeFromSettingsAndArguments() throws {
        let settings = try HostSettings(values: ["ui_url": "http://127.0.0.1:12345", "bridge_args": ["--listen=0.0.0.0:23456", "--ui-port", "34567"]])
        #expect(try BridgePort.required(by: settings) == [BridgePort(12345, .tcp), BridgePort(23456, .udp), BridgePort(34567, .tcp)])
        for args in [["--listen"], ["--listen", "bad"], ["--ui-port", "0"]] {
            #expect(throws: (any Error).self) { try BridgePort.required(by: HostSettings(values: ["bridge_args": args])) }
        }
    }
    @Test func launchContextBothDirections() {
        let bundled = "/Applications/DoesNotExist.app/Contents/MacOS/SteamDeckMIDI"
        let built = "/tmp/sdhost-h1/.build/debug/SteamDeckMIDI"
        #expect(LaunchContext.mode(arguments: [], bundlePath: bundled) == .window)
        #expect(LaunchContext.mode(arguments: [], bundlePath: "/Applications/DoesNotExist.app") == .window)
        #expect(LaunchContext.mode(arguments: [], bundlePath: built) == .cli)
        for path in [bundled, built] {
            #expect(LaunchContext.mode(arguments: ["--background"], bundlePath: path) == .background)
            for args in [["--help"], ["--window"], ["--bridge-guard", "123"], ["--background", "--help"], ["anything"]] {
                #expect(LaunchContext.mode(arguments: args, bundlePath: path) == .cli)
            }
        }
        for path in ["/tmp/a.app/foo", "/tmp/a.framework/Contents/MacOS/a", "/tmp/a.app.backup/Contents/MacOS/a"] {
            #expect(LaunchContext.mode(arguments: [], bundlePath: path) == .cli)
        }
    }
    @Test func everyViewStateRowIsDistinctFromAHealthyPage() {
        let url = URL(string: "http://127.0.0.1:7723")!
        let rows: [(BridgeState, String)] = [(.stopped, "stopped"), (.starting, "starting"), (.stopping, "stopping"),
            (.portBusy(port: 8811, pid: 555), "pid 555"), (.portBusy(port: 8812, pid: nil), "owner unavailable"),
            (.crashed(exitCode: 3, restarts: 2), "exit 3"), (.failed(reason: "crashed repeatedly"), "crashed repeatedly")]
        for (state, phrase) in rows {
            for health in [HealthResult.healthy, .unhealthy("offline")] {
                let view = ViewState.resolve(supervisorState: state, healthResult: health, url: url)
                guard case let .sentence(text, _) = view else { Issue.record("Down state rendered a page"); continue }
                #expect(text.contains(phrase))
            }
        }
        #expect(ViewState.resolve(supervisorState: .running, healthResult: .healthy, url: url) == .page(url))
        #expect(ViewState.resolve(supervisorState: .running, healthResult: .healthy, pageLoadResult: .loaded, url: url) == .page(url))
        #expect(ViewState.resolve(supervisorState: .running, healthResult: .healthy, pageLoadResult: .failed("navigation cancelled"), url: url) == .sentence(text: "Bridge page could not load: navigation cancelled.", tone: .error))
        #expect(ViewState.resolve(supervisorState: .running, healthResult: .unhealthy("HTTP 503"), url: url) == .sentence(text: "Bridge health check failed: HTTP 503.", tone: .error))
    }
    @Test func menuRouteAndControllerActionBar() {
        #expect(MenuModel.items.map(\.title) == ["Open Window", "Start Bridge", "Stop Bridge", "Restart Bridge", "Show Log", "Launch at Login", "Quit"])
        for item in MenuModel.items { #expect(RouteTable.routes.contains(item.route)) }
        #expect(Set(RouteTable.routes.map(\.action)) == Set(ControllerAction.allCases))
        #expect(RouteTable.routes.count == 11)
        #expect(Set(RouteTable.routes.map { $0.method + " " + $0.path }).count == 11)
    }
    @Test func macAPIInventoryMatchesBothDocumentationTables() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let expected = Set(RouteTable.routes.map { $0.method + " " + $0.path })
        for name in ["api.md", "mac-host.md"] {
            let text = try String(contentsOf: root.appendingPathComponent("docs/" + name))
            let rows = text.components(separatedBy: "\n").filter { $0.hasPrefix("| ") && $0.contains("`/host/") }
            let routes = rows.map { row -> String in
                let columns = row.components(separatedBy: "|")
                let method = columns[1].trimmingCharacters(in: .whitespaces)
                let path = columns[2].trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "`", with: "")
                    .components(separatedBy: "?")[0]
                return method + " " + path
            }
            #expect(Set(routes) == expected, "\(name) must document exactly the host's real routes")
            #expect(routes.count == expected.count)
        }
    }
}

private final class RecordingHealthTransport: HealthTransport {
    var request: URLRequest?
    var data = Data("{}".utf8)
    var status = 200
    var failure: Error?
    func get(_ request: URLRequest) async throws -> (Data, Int) {
        self.request = request
        if let failure { throw failure }
        return (data, status)
    }
}
@Suite struct HealthTests {
    @Test func only200JSONObjectIsHealthyWithOneSecondTimeout() async {
        let transport = RecordingHealthTransport(), url = URL(string: "http://127.0.0.1:7723")!
        let probe = HealthProbe(transport: transport)
        #expect(await probe.check(uiURL: url) == .healthy)
        #expect(transport.request?.url?.absoluteString == "http://127.0.0.1:7723/api/settings")
        #expect(transport.request?.timeoutInterval == 1)
        #expect(transport.request?.cachePolicy == .reloadIgnoringLocalCacheData)
        for body in ["<html>catch-all</html>", "[]", "null", "false", "", "{"] {
            transport.data = Data(body.utf8)
            #expect(await probe.check(uiURL: url) != .healthy)
        }
        transport.data = Data("{}".utf8); transport.status = 503
        #expect(await probe.check(uiURL: url) == .unhealthy("HTTP 503"))
        transport.failure = HostError("timed out")
        #expect(await probe.check(uiURL: url) == .unhealthy("timed out"))
    }
}
