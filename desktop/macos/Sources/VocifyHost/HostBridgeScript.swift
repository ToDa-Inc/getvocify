import Foundation

enum HostBridgeScript {
    static func source() -> String? {
        for url in candidates() {
            if let text = try? String(contentsOf: url, encoding: .utf8), !text.isEmpty {
                return text
            }
        }
        return nil
    }

    private static func candidates() -> [URL] {
        var urls: [URL] = []
        if let bundled = Bundle.main.url(forResource: "bridge", withExtension: "js") {
            urls.append(bundled)
        }
        if let resources = Bundle.main.resourceURL {
            urls.append(resources.appendingPathComponent("bridge.js"))
        }
        let executable = URL(fileURLWithPath: CommandLine.arguments[0]).deletingLastPathComponent()
        urls.append(executable.appendingPathComponent("bridge.js"))
        urls.append(executable.appendingPathComponent("VocifyHost_VocifyHost.bundle/bridge.js"))
        if let root = ProcessInfo.processInfo.environment["VOCIFY_RENDERER_ROOT"] {
            urls.append(URL(fileURLWithPath: root).appendingPathComponent("macos/Sources/VocifyHost/bridge.js"))
        }
        return urls
    }
}
