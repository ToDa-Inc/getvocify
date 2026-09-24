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
    let bridge = Bridge()
    @Published var isListening = false

    func emitCommand(_ name: String) {
        bridge.emitCommand(name)
    }

    func toggleListenStop() {
        emitCommand(isListening ? "stop" : "listen")
        isListening.toggle()
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
    func webView(
        _ webView: WKWebView,
        requestMediaCapturePermissionFor origin: WKSecurityOrigin,
        initiatedByFrame frame: WKFrameInfo,
        type: WKMediaCaptureType,
        decisionHandler: @escaping (WKPermissionDecision) -> Void
    ) {
        if origin.host == "127.0.0.1" {
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

        if let scriptURL = Bundle.module.url(forResource: "bridge", withExtension: "js"),
           let source = try? String(contentsOf: scriptURL, encoding: .utf8) {
            let script = WKUserScript(source: source, injectionTime: .atDocumentStart, forMainFrameOnly: true)
            config.userContentController.addUserScript(script)
        }
        config.userContentController.addScriptMessageHandler(host.bridge, contentWorld: .page, name: "vocify")

        let webView = WKWebView(frame: container.bounds, configuration: config)
        webView.translatesAutoresizingMaskIntoConstraints = false
        webView.setValue(false, forKey: "drawsBackground")
        webView.uiDelegate = context.coordinator.uiDelegate
        host.bridge.webView = webView

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
            let page = base.appendingPathComponent("renderer/index.html")
            webView.load(URLRequest(url: page))
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
