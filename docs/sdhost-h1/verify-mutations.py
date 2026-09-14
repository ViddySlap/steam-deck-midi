from pathlib import Path
import shutil, subprocess, json, sys
root = Path(__file__).resolve().parents[2]
scratch = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/tmp/sdhost-h1/mutations-reproduce')
scratch.mkdir(parents=True, exist_ok=True)
package = scratch / 'mac'
if package.exists():
    raise SystemExit('Refusing to replace existing mutation tree')
shutil.copytree(root / 'mac', package, ignore=shutil.ignore_patterns('.build'))
cases = [
 ('settings-unknown', 'HostSettings.swift', 'JSONSerialization.data(withJSONObject: raw, options:', 'JSONSerialization.data(withJSONObject: raw.filter { $0.key != "future" }, options:', 'settingsRoundTripAndAtomicReplacementPreserveUnknownKeys'),
 ('health-html', 'HealthProbe.swift', 'guard (try? JSONSerialization.jsonObject(with: data)) is [String: Any] else {', 'guard !data.isEmpty else {', 'only200JSONObjectIsHealthyWithOneSecondTimeout'),
 ('down-page', 'Presentation.swift', 'case .stopped: return .sentence(text: "Bridge is stopped.", tone: .neutral)', 'case .stopped: return .page(url)', 'everyViewStateRowIsDistinctFromAHealthyPage'),
 ('menu-route', 'HostController.swift', '.init("Open Window", .init("POST", "/host/window/open", .openWindow))', '.init("Open Window", .init("POST", "/host/window/missing", .openWindow))', 'menuRouteAndControllerActionBar'),
 ('environment', 'BridgeSupervisor.swift', 'ProcessInfo.processInfo.environment.merging(configuration.bridgeEnvironment) { _, override in override }', 'ProcessInfo.processInfo.environment', 'exactlyTwoEnvironmentOverridesAndOneOwnedChild'),
 ('port-ownership', 'ProcessSupport.swift', 'if code == EADDRINUSE { return (endpoint.port, owner(endpoint)) }', 'if code == EADDRINUSE { return nil }', 'heldPortStaysHeldAndHolderIsNeverSignalled'),
 ('login-route', 'HostController.swift', 'try loginItem.setEnabled(enabled); return loginItemStatus()', 'return loginItemStatus()', 'ephemeralHTTPServerEveryRouteHappyPathAndErrors'),
 ('orphan-ownership', 'BridgeGuard.swift', 'guard original.contains("windows.win_recv") else', 'guard false else', 'orphanDecisionWithInjectedIdentityStillAssertsRealProcess'),
]
results = []
def run(name, test):
    command = ['swift', 'test', '--disable-sandbox', '--jobs', '1', '--filter', test]
    result = subprocess.run(command, cwd=package, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    text = result.stdout.decode('utf-8', errors='replace')
    (scratch / (name + '.log')).write_text(text.encode('ascii', 'backslashreplace').decode('ascii'))
    summaries = [line for line in text.splitlines() if 'Test run with' in line]
    return result.returncode, summaries[-1] if summaries else 'NO TEST SUMMARY'
for name, file, before, after, test in cases:
    path = package / 'Sources/SteamDeckHostKit' / file
    original = path.read_text()
    assert original.count(before) == 1, (name, 'mutation anchor mismatch')
    baseline, _ = run(name + '-baseline', test)
    assert baseline == 0, (name, 'baseline must pass')
    try:
        path.write_text(original.replace(before, after))
        red, summary = run(name + '-red', test)
        assert red != 0 and 'Test run with' in summary, (name, 'mutation did not produce behavioral failure')
    finally:
        path.write_text(original)
    restored, restored_summary = run(name + '-restored', test)
    assert restored == 0, (name, 'restore did not pass')
    entry = {'mutation': name, 'test': test, 'baseline': baseline, 'mutated': red, 'restored': restored,
             'red_summary': summary, 'restored_summary': restored_summary}
    results.append(entry)
    (scratch / 'results.json').write_text(json.dumps(results, indent=2, ensure_ascii=True) + '\n')
    print(name + ': GREEN / RED / GREEN', flush=True)
print('ALL 8 MUTATIONS BITE', flush=True)
