import AppKit
import Foundation
import WebKit
import VocifyHostKit

final class Bridge: NSObject, WKScriptMessageHandlerWithReply {
    weak var webView: WKWebView?

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
        case "overlay:show", "overlay:hide":
            return ["ok": true]
        case "permissions:status":
            return ["platform": "darwin", "microphone": "not-determined", "systemAudio": "not-determined"]
        case "permissions:request", "permissions:open":
            return ["platform": "darwin", "microphone": "not-determined", "systemAudio": "not-determined"]
        case "system-audio:start":
            return ["ok": false, "reason": "no_system_audio"]
        case "system-audio:stop":
            return ["ok": true]
        case "capture:pending":
            return [] as [[String: Any]]
        case "shell:state", "shell:command":
            return nil
        case "capture:begin", "capture:append", "capture:channel-absent", "capture:confirm", "capture:discard":
            return ["ok": true]
        default:
            return nil
        }
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
        guard let webView else { return }
        emit("shell:command", name, in: webView)
    }
}
