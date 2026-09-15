// sdauto gate: list on-screen/offscreen windows owned by a pid (layer, owner name, bounds). No window titles needed.
import Foundation
import CoreGraphics
let pid = Int(CommandLine.arguments[1])!
let info = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID) as! [[String: Any]]
var n = 0
var status = 0
for w in info {
    guard let owner = w[kCGWindowOwnerPID as String] as? Int, owner == pid else { continue }
    let layer = w[kCGWindowLayer as String] as? Int ?? -1
    let name = w[kCGWindowOwnerName as String] as? String ?? ""
    let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
    print("WINDOW pid=\(owner) owner=\(name) layer=\(layer) bounds=\(b)")
    n += 1
    if layer == 25 { status += 1 }
}
print("PID_WINDOWS \(n) STATUS_LAYER_25 \(status) TOTAL_WINDOWS \(info.count)")
