import Foundation
import VocifyHostKit

func check(_ ok: Bool, _ name: String) {
    if ok { print("ok  \(name)") } else { fputs("FAIL \(name)\n", stderr); exit(1) }
}

func tempDir() throws -> URL {
    let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    return dir
}

// RendererServer
do {
    let dir = try tempDir()
    try "<p>ok</p>".write(to: dir.appendingPathComponent("index.html"), atomically: true, encoding: .utf8)
    let server = RendererServer(root: dir)
    let base = try server.start()
    let (data, response) = try await URLSession.shared.data(from: base.appendingPathComponent("index.html"))
    let http = response as? HTTPURLResponse
    check(http?.value(forHTTPHeaderField: "Content-Type") == "text/html; charset=utf-8", "server html type")
    check(String(data: data, encoding: .utf8) == "<p>ok</p>", "server html body")
    let (_, escape) = try await URLSession.shared.data(from: URL(string: "\(base.absoluteString)../etc/hosts")!)
    check((escape as? HTTPURLResponse)?.statusCode == 404, "server refuses traversal")
    server.stop()
}
check(RendererServer.mime(for: "a.js") == "text/javascript; charset=utf-8", "mime js")
check(RendererServer.mime(for: "a.css") == "text/css; charset=utf-8", "mime css")
check(RendererServer.mime(for: "a.png") == "image/png", "mime png")

// SaasProxy
check(SaasProxy.isAllowedApiBase("https://api.getvocify.com/api/v1"), "api host allowed")
check(SaasProxy.isAllowedApiBase("http://localhost:8888/api/v1"), "localhost allowed")
check(!SaasProxy.isAllowedApiBase("http://api.getvocify.com/api/v1"), "plain http prod refused")
check(!SaasProxy.isAllowedApiBase("https://evil.example"), "foreign host refused")
do {
    let result = await SaasProxy.request(["base": "https://evil.example", "path": "/auth/me", "method": "GET"])
    check(result["ok"] as? Bool == false, "foreign request not sent")
    check(result["error"] as? String == "API base is not a Vocify host", "foreign request error text")
}
do {
    let fixture = Data(#"[{"id":"m1"}]"#.utf8)
    let parsed = SaasProxy.parseResponseBody(fixture)
    check(parsed is [Any], "json array parses as array")
    check((parsed as? [Any])?.count == 1, "json array element count")
}

// CaptureStore — mirrors desktop/lib/capture-store.test.js
do {
    let root = try tempDir()
    defer { try? FileManager.default.removeItem(at: root) }
    let store = CaptureStore(root: root)
    try store.begin(clientCaptureId: "cap-local-1", meta: ["startedAt": "2026-09-22T08:00:00Z"])
    _ = try store.append(clientCaptureId: "cap-local-1", channel: "mic", chunk: Data("before-ws-cut".utf8))
    _ = try store.append(clientCaptureId: "cap-local-1", channel: "mic", chunk: Data("-after-ws-cut".utf8))
    let view = try store.read(clientCaptureId: "cap-local-1")
    let mic = (view["channels"] as? [String: Any])?["mic"] as? [String: Any]
    let path = mic?["path"] as? String ?? ""
    let audio = try String(contentsOf: URL(fileURLWithPath: path), encoding: .utf8)
    check(audio == "before-ws-cut-after-ws-cut", "capture ws cut audio preserved")
}
do {
    let root = try tempDir()
    defer { try? FileManager.default.removeItem(at: root) }
    let store = CaptureStore(root: root)
    try store.begin(clientCaptureId: "cap-local-1", meta: ["startedAt": "2026-09-22T08:00:00Z"])
    _ = try store.append(clientCaptureId: "cap-local-1", channel: "mic", chunk: Data("chunk-a".utf8))
    let reopened = CaptureStore(root: root)
    let pending = reopened.pending()
    check(pending.count == 1, "capture restart pending count")
    check(pending[0]["clientCaptureId"] as? String == "cap-local-1", "capture restart clientCaptureId")
    check(pending[0]["remoteConfirmed"] as? Bool == false, "capture restart remoteConfirmed")
    let mic = (pending[0]["channels"] as? [String: Any])?["mic"] as? [String: Any]
    let path = mic?["path"] as? String ?? ""
    let audio = try String(contentsOf: URL(fileURLWithPath: path), encoding: .utf8)
    check(audio == "chunk-a", "capture restart audio bytes")
    var discardFailed = false
    do {
        try reopened.discard(clientCaptureId: "cap-local-1")
    } catch {
        discardFailed = error.localizedDescription.contains("confirmación remota")
    }
    check(discardFailed, "capture discard blocked before remote confirm")
}
do {
    let root = try tempDir()
    defer { try? FileManager.default.removeItem(at: root) }
    let store = CaptureStore(root: root)
    try store.begin(clientCaptureId: "cap-local-1", meta: ["startedAt": "2026-09-22T08:00:00Z"])
    _ = try store.append(clientCaptureId: "cap-local-1", channel: "mic", chunk: Data("ok".utf8))
    let view = try store.noteChannelAbsent(clientCaptureId: "cap-local-1", channel: "system", reason: "permission")
    check(view["audioStatus"] as? String == "partial", "capture partial audioStatus")
    check(view["channelsComplete"] as? Bool == false, "capture partial channelsComplete")
    let system = (view["channels"] as? [String: Any])?["system"] as? [String: Any]
    check(system?["absent"] as? Bool == true, "capture system channel absent")
    let micPath = ((view["channels"] as? [String: Any])?["mic"] as? [String: Any])?["path"] as? String ?? ""
    let failing = CaptureStore(root: root, appendFile: { _, _ in
        throw NSError(domain: NSPOSIXErrorDomain, code: Int(POSIXError.ENOSPC.rawValue), userInfo: nil)
    })
    var diskFull = false
    do {
        _ = try failing.append(clientCaptureId: "cap-local-1", channel: "mic", chunk: Data("more".utf8))
    } catch is DiskFullError {
        diskFull = true
    }
    check(diskFull, "capture disk full throws DiskFullError")
    let kept = try String(contentsOf: URL(fileURLWithPath: micPath), encoding: .utf8)
    check(kept == "ok", "capture disk full keeps prior audio")
}
do {
    let root = try tempDir()
    defer { try? FileManager.default.removeItem(at: root) }
    let store = CaptureStore(root: root)
    try store.begin(clientCaptureId: "cap-local-1", meta: ["startedAt": "2026-09-22T08:00:00Z"])
    _ = try store.append(clientCaptureId: "cap-local-1", channel: "mic", chunk: Data("ok".utf8))
    _ = try store.confirmRemote(clientCaptureId: "cap-local-1")
    try store.discard(clientCaptureId: "cap-local-1")
    check(store.pending().isEmpty, "capture discard after confirm clears pending")
}

print("all checks passed")
