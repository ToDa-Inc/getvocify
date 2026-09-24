// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "VocifyHost",
    platforms: [.macOS(.v14)],
    targets: [
        .target(name: "VocifyHostKit"),
        .executableTarget(name: "VocifyHost", dependencies: ["VocifyHostKit"], resources: [.copy("bridge.js")]),
        .executableTarget(name: "VocifyHostChecks", dependencies: ["VocifyHostKit"]),
    ]
)
