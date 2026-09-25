import AppKit
import SwiftUI
import WebKit
import VocifyHostKit

private let shellBackground = NSColor(
    red: 0xf7 / 255,
    green: 0xf4 / 255,
    blue: 0xee / 255,
    alpha: 1
)

final class HostController: ObservableObject {
    let bridge: Bridge
    let overlay = OverlayController()
    @Published var isListening = false
    /// Main window loads the web dashboard (app.getvocify.com) instead of bundled `desktop/renderer`.
    @Published var usesWebDashboard = false
    private var shellState: [String: Any] = [:]

    init() {
        let bridge = Bridge()
        self.bridge = bridge
        bridge.host = self
        overlay.host = self
    }

    func mergedShellState() -> [String: Any] {
        shellState
    }

    func emitCommand(_ name: String) {
        bridge.emitCommand(name)
    }

    func toggleListenStop() {
        emitCommand(isListening ? "stop" : "listen")
    }

    func applyShellState(_ patch: [String: Any]) {
        for (key, value) in patch {
            if value is NSNull {
                shellState.removeValue(forKey: key)
            } else {
                shellState[key] = value
            }
        }
        if let listening = shellState["listening"] as? Bool {
            isListening = listening
        }
        overlay.pushState(shellState)
    }

    /// Entry URL for the React dashboard. Set `VOCIFY_USE_LOCAL_RENDERER=1` to use bundled vanilla renderer.
    func resolveWebDashboardEntry() -> URL? {
        if ProcessInfo.processInfo.environment["VOCIFY_USE_LOCAL_RENDERER"] == "1" {
            return nil
        }
        let origin: String
        if let env = ProcessInfo.processInfo.environment["VOCIFY_WEB_ORIGIN"], !env.isEmpty {
            origin = env.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        } else if let plist = Bundle.main.infoDictionary?["VocifyWebOrigin"] as? String, !plist.isEmpty {
            origin = plist.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        } else {
            origin = "https://app.getvocify.com"
        }
        let path: String
        if let env = ProcessInfo.processInfo.environment["VOCIFY_WEB_PATH"], !env.isEmpty {
            path = env.hasPrefix("/") ? env : "/\(env)"
        } else if let plist = Bundle.main.infoDictionary?["VocifyWebPath"] as? String, !plist.isEmpty {
            path = plist.hasPrefix("/") ? plist : "/\(plist)"
        } else {
            path = "/dashboard/memos"
        }
        guard let url = URL(string: "\(origin)\(path)") else { return nil }
        return url
    }

    func resolveRendererRoot() -> URL {
        if let raw = ProcessInfo.processInfo.environment["VOCIFY_RENDERER_ROOT"], !raw.isEmpty {
            return URL(fileURLWithPath: raw, isDirectory: true).standardizedFileURL
        }
        if let resources = Bundle.main.resourceURL {
            let index = resources.appendingPathComponent("renderer/index.html")
            if FileManager.default.fileExists(atPath: index.path) {
                return resources
            }
        }
        let fromCwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("..")
            .standardizedFileURL
        if FileManager.default.fileExists(atPath: fromCwd.appendingPathComponent("renderer/index.html").path) {
            return fromCwd
        }
        return fromCwd
    }
}

final class WebShellUIDelegate: NSObject, WKUIDelegate {
    private func trustedMediaCaptureHost(_ host: String) -> Bool {
        let h = host.lowercased()
        if h == "127.0.0.1" || h == "localhost" { return true }
        if h == "app.getvocify.com" || h == "staging.getvocify.com" { return true }
        if h.hasSuffix(".getvocify.com") { return true }
        return false
    }

    func webView(
        _ webView: WKWebView,
        requestMediaCapturePermissionFor origin: WKSecurityOrigin,
        initiatedByFrame frame: WKFrameInfo,
        type: WKMediaCaptureType,
        decisionHandler: @escaping (WKPermissionDecision) -> Void
    ) {
        if trustedMediaCaptureHost(origin.host) {
            decisionHandler(.grant)
        } else {
            decisionHandler(.deny)
        }
    }
}

struct WebShellView: NSViewRepresentable {
    @ObservedObject var host: HostController

    func makeCoordinator() -> Coordinator {
        Coordinator(host: host)
    }

    func makeNSView(context: Context) -> NSView {
        let container = NSView(frame: .zero)
        container.wantsLayer = true
        container.layer?.backgroundColor = shellBackground.cgColor

        let config = WKWebViewConfiguration()
        config.preferences.isElementFullscreenEnabled = false

        if let source = HostBridgeScript.source() {
            let script = WKUserScript(source: source, injectionTime: .atDocumentStart, forMainFrameOnly: true)
            config.userContentController.addUserScript(script)
        }
        config.userContentController.addScriptMessageHandler(host.bridge, contentWorld: .page, name: "vocify")

        let webView = WKWebView(frame: container.bounds, configuration: config)
        webView.translatesAutoresizingMaskIntoConstraints = false
        webView.setValue(false, forKey: "drawsBackground")
        webView.uiDelegate = context.coordinator.uiDelegate
        host.bridge.mainWebView = webView

        container.addSubview(webView)
        NSLayoutConstraint.activate([
            webView.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            webView.topAnchor.constraint(equalTo: container.topAnchor),
            webView.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])

        context.coordinator.server?.stop()
        let root = host.resolveRendererRoot()
        let server = RendererServer(root: root)
        context.coordinator.server = server
        do {
            let base = try server.start()
            host.overlay.attach(bridge: host.bridge, uiDelegate: context.coordinator.uiDelegate, rendererBase: base)
            if let dashboard = host.resolveWebDashboardEntry() {
                host.usesWebDashboard = true
                webView.load(URLRequest(url: dashboard))
            } else {
                host.usesWebDashboard = false
                let page = base.appendingPathComponent("renderer/index.html")
                webView.load(URLRequest(url: page))
            }
        } catch {
            fputs("WebShell: failed to start renderer server: \(error)\n", stderr)
        }

        return container
    }

    func updateNSView(_ nsView: NSView, context: Context) {}

    static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
        coordinator.server?.stop()
    }

    final class Coordinator {
        let host: HostController
        let uiDelegate = WebShellUIDelegate()
        var server: RendererServer?

        init(host: HostController) {
            self.host = host
        }
    }
}
