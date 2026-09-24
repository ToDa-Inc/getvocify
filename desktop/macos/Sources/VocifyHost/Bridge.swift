import AppKit
import AVFoundation
import Foundation
import WebKit
import VocifyHostKit

final class Bridge: NSObject, WKScriptMessageHandlerWithReply {
    weak var mainWebView: WKWebView?
    weak var overlayWebView: WKWebView?
    weak var host: HostController?

    private let systemAudio = SystemAudio()

    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage,
        replyHandler: @escaping (Any?, String?) -> Void
    ) {
        guard message.name == "vocify",
              let body = message.body as? [String: Any],
              let op = body["op"] as? String
        else {
            replyHandler(nil, "invalid message")
            return
        }
        let args = body["args"] as? [String: Any] ?? [:]
        Task {
            let result = await handle(op: op, args: args)
            replyHandler(result, nil)
        }
    }

    func handle(op: String, args: [String: Any]) async -> Any? {
        switch op {
        case "saas:request":
            let payload = args["payload"] as? [String: Any] ?? [:]
            return await SaasProxy.request(payload)
        case "shell:open-external":
            guard let urlStr = args["url"] as? String,
                  urlStr.range(of: #"^(https?://|mailto:)"#, options: .regularExpression) != nil,
                  let url = URL(string: urlStr)
            else {
                return ["ok": false]
            }
            NSWorkspace.shared.open(url)
            return ["ok": true]
        case "shell:resize":
            return ["ok": true]
        case "overlay:show":
            await MainActor.run { host?.overlay.show() }
            return ["ok": true]
        case "overlay:hide":
            await MainActor.run { host?.overlay.hide() }
            return ["ok": true]
        case "permissions:status":
            return permissionSnapshot()
        case "permissions:request":
            await requestPermission(type: args["type"] as? String)
            return permissionSnapshot()
        case "permissions:open":
            openPermissionSettings(type: args["type"] as? String)
            return permissionSnapshot()
        case "system-audio:start":
            return await startSystemAudio()
        case "system-audio:stop":
            await systemAudio.stop()
            return ["ok": true]
        case "capture:pending":
            return [] as [[String: Any]]
        case "shell:state":
            if let state = args["state"] as? [String: Any] {
                await MainActor.run {
                    host?.applyShellState(state)
                }
            }
            return nil
        case "shell:command":
            let name = args["name"] as? String ?? ""
            await MainActor.run {
                routeShellCommand(name)
            }
            return nil
        case "capture:begin", "capture:append", "capture:channel-absent", "capture:confirm", "capture:discard":
            return ["ok": true]
        default:
            return nil
        }
    }

    private func permissionSnapshot() -> [String: String] {
        [
            "platform": "darwin",
            "microphone": microphoneAccessStatus(),
            "systemAudio": systemAudioAccessStatus(),
        ]
    }

    private func microphoneAccessStatus() -> String {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            return "authorized"
        case .denied, .restricted:
            return "denied"
        case .notDetermined:
            return "never_requested"
        @unknown default:
            return "never_requested"
        }
    }

    private func systemAudioAccessStatus() -> String {
        CGPreflightScreenCaptureAccess() ? "authorized" : "never_requested"
    }

    private func requestPermission(type: String?) async {
        switch type {
        case "microphone":
            _ = await AVCaptureDevice.requestAccess(for: .audio)
        case "systemAudio":
            _ = CGRequestScreenCaptureAccess()
        default:
            break
        }
    }

    private func openPermissionSettings(type: String?) {
        let anchor = type == "microphone" ? "Privacy_Microphone" : "Privacy_ScreenCapture"
        let candidates = [
            "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?\(anchor)",
            "x-apple.systempreferences:com.apple.preference.security?\(anchor)",
        ]
        for raw in candidates {
            guard let url = URL(string: raw) else { continue }
            if NSWorkspace.shared.open(url) { break }
        }
    }

    private func startSystemAudio() async -> [String: Any] {
        await systemAudio.stop()
        guard CGPreflightScreenCaptureAccess() else {
            return ["ok": false, "reason": "no_system_audio"]
        }
        let webView = await MainActor.run { self.mainWebView }
        systemAudio.setHandlers(
            onPcm: { [weak self] data in
                guard let self, let webView else { return }
                let encoded = data.base64EncodedString()
                Task { @MainActor in
                    self.emit("system-audio:pcm", encoded, in: webView)
                }
            },
            onLost: { [weak self] _ in
                Task { @MainActor in
                    self?.emitSystemAudioLost()
                }
            }
        )
        do {
            try await systemAudio.start()
            return ["ok": true, "backend": "screencapturekit"]
        } catch {
            await systemAudio.stop()
            return ["ok": false, "reason": "no_system_audio"]
        }
    }

    private func emitSystemAudioLost() {
        guard let mainWebView else { return }
        emit("system-audio:lost", ["reason": "no_system_audio"], in: mainWebView)
    }

    @MainActor
    private func routeShellCommand(_ name: String) {
        switch name {
        case "show":
            activateMainWindow()
        case "dashboard":
            openDashboard()
        case "quit":
            NSApp.terminate(nil)
        case "assist-on", "assist-off":
            emitCommand(name)
        default:
            activateMainWindow()
            emitCommand(name)
        }
    }

    @MainActor
    private func activateMainWindow() {
        NSApp.activate(ignoringOtherApps: true)
        for window in NSApp.windows where !(window is NSPanel) {
            window.makeKeyAndOrderFront(nil)
            return
        }
    }

    @MainActor
    private func openDashboard() {
        let state = host?.mergedShellState() ?? [:]
        let apiBase = (state["apiBase"] as? String) ?? ""
        let trimmed = apiBase.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let origin: String
        if trimmed.contains("localhost") || trimmed.contains("127.0.0.1") {
            origin = "http://localhost:8080"
        } else {
            origin = "https://app.getvocify.com"
        }
        let urlString = "\(origin)/dashboard/memos"
        guard urlString.range(of: #"^https?://"#, options: .regularExpression) != nil,
              let url = URL(string: urlString)
        else { return }
        NSWorkspace.shared.open(url)
    }

    func emit(_ channel: String, _ payload: Any, in webView: WKWebView) {
        let channelJSON = (try? JSONSerialization.data(withJSONObject: channel))
            .flatMap { String(data: $0, encoding: .utf8) } ?? "\"\(channel)\""
        let payloadJS: String
        if JSONSerialization.isValidJSONObject(payload),
           let data = try? JSONSerialization.data(withJSONObject: payload),
           let json = String(data: data, encoding: .utf8) {
            payloadJS = json
        } else if let text = payload as? String,
                  let data = try? JSONSerialization.data(withJSONObject: text),
                  let json = String(data: data, encoding: .utf8) {
            payloadJS = json
        } else {
            payloadJS = "null"
        }
        webView.evaluateJavaScript("window.__vocifyEmit(\(channelJSON), \(payloadJS))")
    }

    func emitCommand(_ name: String) {
        guard let mainWebView else { return }
        emit("shell:command", name, in: mainWebView)
    }
}
