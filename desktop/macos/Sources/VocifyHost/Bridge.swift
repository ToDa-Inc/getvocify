import AppKit
import AVFoundation
import Foundation
import ScreenCaptureKit
import WebKit
import VocifyHostKit

final class Bridge: NSObject, WKScriptMessageHandlerWithReply {
    weak var mainWebView: WKWebView?
    weak var overlayWebView: WKWebView?
    weak var host: HostController?

    private let systemAudio = SystemAudio()
    private lazy var captureStore = CaptureStore(root: CaptureStore.defaultCapturesRoot())
    /// Serializes capture bridge ops (WK messages run on concurrent Tasks; Electron IPC is single-threaded).
    private let captureQueue = DispatchQueue(label: "com.vocify.host.capture")

    private func withCaptureSerialization<T>(_ body: () -> T) -> T {
        captureQueue.sync(execute: body)
    }

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
            let safe = Self.webKitSafe(result)
            await MainActor.run {
                replyHandler(safe, nil)
            }
        }
    }

    /// WK only accepts property-list values. A raw JSON object from URLSession is not one.
    static func webKitSafe(_ value: Any?) -> Any {
        guard let value, JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value),
              let parsed = try? JSONSerialization.jsonObject(with: data) else {
            return [:]
        }
        return parsed
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
            return await permissionSnapshot()
        case "permissions:request":
            await requestPermission(type: args["type"] as? String)
            return await permissionSnapshot()
        case "permissions:open":
            openPermissionSettings(type: args["type"] as? String)
            return await permissionSnapshot()
        case "system-audio:start":
            return await startSystemAudio()
        case "system-audio:stop":
            await systemAudio.stop()
            return ["ok": true]
        case "capture:pending":
            return withCaptureSerialization { ["ok": true, "items": captureStore.pending()] }
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
        case "capture:begin":
            return withCaptureSerialization { handleCaptureBegin(args: args) }
        case "capture:append":
            return withCaptureSerialization { handleCaptureAppend(args: args) }
        case "capture:channel-absent":
            return withCaptureSerialization { handleCaptureChannelAbsent(args: args) }
        case "capture:confirm":
            return withCaptureSerialization { handleCaptureConfirm(args: args) }
        case "capture:discard":
            return withCaptureSerialization { handleCaptureDiscard(args: args) }
        default:
            return nil
        }
    }

    private func handleCaptureBegin(args: [String: Any]) -> [String: Any] {
        let payload = args["payload"] as? [String: Any] ?? [:]
        guard let id = payload["clientCaptureId"] as? String, !id.isEmpty else {
            return ["ok": false, "error": "clientCaptureId required"]
        }
        do {
            let manifest = try captureStore.begin(clientCaptureId: id, meta: payload)
            return ["ok": true, "manifest": manifest]
        } catch {
            return ["ok": false, "error": error.localizedDescription]
        }
    }

    private func handleCaptureAppend(args: [String: Any]) -> [String: Any] {
        let payload = args["payload"] as? [String: Any] ?? [:]
        guard let id = payload["clientCaptureId"] as? String else {
            return ["ok": false, "error": "clientCaptureId required", "code": "append_failed"]
        }
        guard let channel = payload["channel"] as? String else {
            return ["ok": false, "error": "channel required", "code": "append_failed"]
        }
        let chunk = Self.dataFromChunkPayload(payload["chunk"])
        do {
            let manifest = try captureStore.append(clientCaptureId: id, channel: channel, chunk: chunk)
            return ["ok": true, "manifest": manifest]
        } catch let error as DiskFullError {
            return ["ok": false, "error": error.localizedDescription, "code": DiskFullError.code]
        } catch {
            let ns = error as NSError
            return ["ok": false, "error": error.localizedDescription, "code": ns.userInfo["code"] as? String ?? "append_failed"]
        }
    }

    private func handleCaptureChannelAbsent(args: [String: Any]) -> [String: Any] {
        let payload = args["payload"] as? [String: Any] ?? [:]
        guard let id = payload["clientCaptureId"] as? String,
              let channel = payload["channel"] as? String
        else {
            return ["ok": false, "error": "clientCaptureId and channel required"]
        }
        do {
            let reason = payload["reason"] as? String
            let manifest = try captureStore.noteChannelAbsent(clientCaptureId: id, channel: channel, reason: reason)
            return ["ok": true, "manifest": manifest]
        } catch {
            return ["ok": false, "error": error.localizedDescription]
        }
    }

    private func handleCaptureConfirm(args: [String: Any]) -> [String: Any] {
        guard let id = args["id"] as? String else {
            return ["ok": false, "error": "id required"]
        }
        do {
            let manifest = try captureStore.confirmRemote(clientCaptureId: id)
            return ["ok": true, "manifest": manifest]
        } catch {
            return ["ok": false, "error": error.localizedDescription]
        }
    }

    private func handleCaptureDiscard(args: [String: Any]) -> [String: Any] {
        guard let id = args["id"] as? String else {
            return ["ok": false, "error": "id required"]
        }
        do {
            try captureStore.discard(clientCaptureId: id)
            return ["ok": true]
        } catch {
            return ["ok": false, "error": error.localizedDescription]
        }
    }

    private static func dataFromChunkPayload(_ value: Any?) -> Data {
        if let bytes = value as? [Int] {
            return Data(bytes.map { UInt8(clamping: $0) })
        }
        if let bytes = value as? [UInt8] {
            return Data(bytes)
        }
        if let bytes = value as? [NSNumber] {
            return Data(bytes.map { UInt8(clamping: $0.intValue) })
        }
        return Data()
    }

    private func permissionSnapshot() async -> [String: String] {
        [
            "platform": "darwin",
            "microphone": microphoneAccessStatus(),
            "systemAudio": await systemAudioAccessStatus(),
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

    private func systemAudioAccessStatus() async -> String {
        if CGPreflightScreenCaptureAccess() { return "authorized" }
        do {
            _ = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
            if CGPreflightScreenCaptureAccess() { return "authorized" }
        } catch {
            fputs("VocifyHost permission probe: \(error.localizedDescription)\n", stderr)
        }
        return "never_requested"
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
        if host?.usesWebDashboard == true, let url = host?.resolveWebDashboardEntry() {
            mainWebView?.load(URLRequest(url: url))
            activateMainWindow()
            return
        }
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
        let channelJSON = Self.jsonLiteral(channel)
        let payloadJS = Self.jsonLiteral(forPayload: payload)
        webView.evaluateJavaScript("window.__vocifyEmit(\(channelJSON), \(payloadJS))")
    }

    /// NSJSONSerialization throws NSException (not Swift errors) for top-level strings; never pass those through.
    private static func jsonLiteral(_ text: String) -> String {
        guard let data = try? JSONEncoder().encode(text),
              let encoded = String(data: data, encoding: .utf8) else {
            return "\"\""
        }
        return encoded
    }

    private static func jsonLiteral(forPayload payload: Any) -> String {
        if let text = payload as? String {
            return jsonLiteral(text)
        }
        let safe = webKitSafe(payload)
        guard JSONSerialization.isValidJSONObject(safe),
              let data = try? JSONSerialization.data(withJSONObject: safe),
              let json = String(data: data, encoding: .utf8) else {
            return "null"
        }
        return json
    }

    func emitCommand(_ name: String) {
        guard let mainWebView else { return }
        emit("shell:command", name, in: mainWebView)
    }
}
