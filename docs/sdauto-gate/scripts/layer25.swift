// sdauto gate: count layer-25 (status) windows per owner name and pid, all processes.
import Foundation
import CoreGraphics
let info = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID) as! [[String: Any]]
var counts: [String: Int] = [:]
for w in info {
    let layer = w[kCGWindowLayer as String] as? Int ?? -1
    if layer != 25 { continue }
    let name = w[kCGWindowOwnerName as String] as? String ?? ""
    let pid = w[kCGWindowOwnerPID as String] as? Int ?? -1
    let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
    counts["\(name)(\(pid))", default: 0] += 1
    if name != "ControlCenter" && name != "SystemUIServer" { print("L25 \(name) pid=\(pid) bounds=\(b)") }
}
print("LAYER25 " + counts.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: " "))
