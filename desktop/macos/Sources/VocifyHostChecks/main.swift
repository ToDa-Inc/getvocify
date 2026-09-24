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

print("all checks passed")
