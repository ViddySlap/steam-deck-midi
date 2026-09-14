// swift-tools-version:5.9
// All decisions live in the headless library. The executable only supplies
// platform adapters. CLT supplies swift-testing; no Xcode or dependencies.
import PackageDescription

let package = Package(
    name: "SteamDeckMIDI",
    platforms: [.macOS(.v13)],
    products: [.library(name: "SteamDeckHostKit", targets: ["SteamDeckHostKit"]),
               .executable(name: "SteamDeckMIDI", targets: ["SteamDeckMIDI"])],
    targets: [
        .target(name: "SteamDeckHostKit"),
        .executableTarget(name: "SteamDeckMIDI", dependencies: ["SteamDeckHostKit"]),
        .testTarget(name: "SteamDeckHostKitTests", dependencies: ["SteamDeckHostKit"],
                    resources: [.copy("Fixtures")])
    ]
)
