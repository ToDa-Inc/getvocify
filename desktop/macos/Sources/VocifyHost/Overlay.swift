import AppKit
import WebKit
import VocifyHostKit

private let overlayWidth: CGFloat = 340
private let overlayHeight: CGFloat = 64
private let overlayMargin: CGFloat = 24

final class OverlayPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

private final class OverlayNavigationDelegate: NSObject, WKNavigationDelegate {
    weak var overlay: OverlayController?

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        overlay?.overlayPageDidStartLoading()
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        overlay?.overlayPageDidFinishLoading()
    }
}

final class OverlayController {
    weak var host: HostController?
    private var panel: OverlayPanel?
    private var overlayWebView: WKWebView?
    private weak var bridge: Bridge?
    private var uiDelegate: WebShellUIDelegate?
    private var rendererBase: URL?
    private var navigationDelegate: OverlayNavigationDelegate?
    private var lastOverlayState: [String: Any] = [:]
    private var overlayPageLoaded = false

    func attach(bridge: Bridge, uiDelegate: WebShellUIDelegate, rendererBase: URL) {
        self.bridge = bridge
        self.uiDelegate = uiDelegate
        self.rendererBase = rendererBase
        bridge.overlayWebView = nil
    }

    func pushState(_ state: [String: Any]) {
        lastOverlayState = state
        emitOverlayStateIfReady()
        repositionIfVisible()
    }

    fileprivate func overlayPageDidStartLoading() {
        overlayPageLoaded = false
    }

    fileprivate func overlayPageDidFinishLoading() {
        overlayPageLoaded = true
        emitOverlayStateIfReady()
    }

    private func emitOverlayStateIfReady() {
        guard overlayPageLoaded, let overlayWebView, !lastOverlayState.isEmpty else { return }
        bridge?.emit("overlay:state", lastOverlayState, in: overlayWebView)
    }

    func show() {
        ensurePanel()
        repositionIfVisible()
        panel?.orderFrontRegardless()
    }

    func hide() {
        panel?.orderOut(nil)
    }

    private func ensurePanel() {
        if panel != nil { return }
        guard let bridge, let uiDelegate, let rendererBase else { return }

        let frame = overlayFrame(for: NSScreen.main?.visibleFrame)
        let panel = OverlayPanel(
            contentRect: frame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.level = .statusBar
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.hidesOnDeactivate = false
        panel.isFloatingPanel = true
        panel.becomesKeyOnlyIfNeeded = true

        let config = WKWebViewConfiguration()
        config.preferences.isElementFullscreenEnabled = false
        if let scriptURL = Bundle.module.url(forResource: "bridge", withExtension: "js"),
           let source = try? String(contentsOf: scriptURL, encoding: .utf8) {
            let script = WKUserScript(source: source, injectionTime: .atDocumentStart, forMainFrameOnly: true)
            config.userContentController.addUserScript(script)
        }
        config.userContentController.addScriptMessageHandler(bridge, contentWorld: .page, name: "vocify")

        let webView = WKWebView(frame: panel.contentView!.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.setValue(false, forKey: "drawsBackground")
        webView.uiDelegate = uiDelegate
        let navigationDelegate = OverlayNavigationDelegate()
        navigationDelegate.overlay = self
        webView.navigationDelegate = navigationDelegate
        self.navigationDelegate = navigationDelegate
        panel.contentView = webView

        self.panel = panel
        self.overlayWebView = webView
        bridge.overlayWebView = webView

        if lastOverlayState.isEmpty, let state = host?.mergedShellState(), !state.isEmpty {
            lastOverlayState = state
        }

        let page = rendererBase.appendingPathComponent("renderer/overlay.html")
        webView.load(URLRequest(url: page))
    }

    private func repositionIfVisible() {
        guard panel?.isVisible == true || panel != nil else { return }
        let frame = overlayFrame(for: NSScreen.main?.visibleFrame)
        panel?.setFrame(frame, display: true)
    }

    private func overlayFrame(for visibleFrame: NSRect?) -> NSRect {
        let area = visibleFrame ?? NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let x = area.origin.x + area.width - overlayWidth - overlayMargin
        let y = area.origin.y + overlayMargin
        return NSRect(x: x, y: y, width: overlayWidth, height: overlayHeight)
    }
}
