import Foundation
import Network

public final class RendererServer {
    private let root: URL
    private var listener: NWListener?
    private let queue = DispatchQueue(label: "com.vocify.RendererServer")

    public init(root: URL) {
        self.root = root.standardizedFileURL
    }

    public func start() throws -> URL {
        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = NWEndpoint.hostPort(host: .ipv4(.loopback), port: .any)
        let listener = try NWListener(using: parameters)

        let sem = DispatchSemaphore(value: 0)
        var readyPort: UInt16?
        var startError: Error?

        listener.stateUpdateHandler = { state in
            switch state {
            case .ready:
                readyPort = listener.port?.rawValue
                sem.signal()
            case .failed(let error):
                startError = error
                sem.signal()
            default:
                break
            }
        }

        listener.newConnectionHandler = { [weak self] connection in
            self?.serve(connection: connection)
        }

        listener.start(queue: queue)

        if sem.wait(timeout: .now() + 2) == .timedOut {
            listener.cancel()
            throw RendererServerError.listenerTimeout
        }
        if let startError {
            listener.cancel()
            throw startError
        }
        guard let port = readyPort else {
            listener.cancel()
            throw RendererServerError.noPort
        }

        self.listener = listener
        guard let url = URL(string: "http://127.0.0.1:\(port)/") else {
            throw RendererServerError.noPort
        }
        return url
    }

    public func stop() {
        listener?.cancel()
        listener = nil
    }

    public static func mime(for path: String) -> String {
        if path.hasSuffix(".html") { return "text/html; charset=utf-8" }
        if path.hasSuffix(".css") { return "text/css; charset=utf-8" }
        if path.hasSuffix(".js") || path.hasSuffix(".mjs") { return "text/javascript; charset=utf-8" }
        if path.hasSuffix(".json") { return "application/json; charset=utf-8" }
        if path.hasSuffix(".svg") { return "image/svg+xml" }
        if path.hasSuffix(".png") { return "image/png" }
        if path.hasSuffix(".jpg") || path.hasSuffix(".jpeg") { return "image/jpeg" }
        return "application/octet-stream"
    }

    private func serve(connection: NWConnection) {
        connection.start(queue: queue)
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, _, _ in
            guard let self else {
                connection.cancel()
                return
            }
            guard let data, let request = String(data: data, encoding: .utf8) else {
                self.send(status: 400, headers: [:], body: Data(), on: connection)
                return
            }
            guard let line = request.split(separator: "\n", maxSplits: 1, omittingEmptySubsequences: false).first else {
                self.send(status: 400, headers: [:], body: Data(), on: connection)
                return
            }
            let parts = line.split(separator: " ", omittingEmptySubsequences: true)
            guard parts.count >= 2, parts[0] == "GET" else {
                self.send(status: 405, headers: [:], body: Data(), on: connection)
                return
            }
            var rawPath = String(parts[1])
            if let q = rawPath.firstIndex(of: "?") {
                rawPath = String(rawPath[..<q])
            }
            guard let decoded = rawPath.removingPercentEncoding else {
                self.send(status: 400, headers: [:], body: Data(), on: connection)
                return
            }
            let relative = decoded.hasPrefix("/") ? String(decoded.dropFirst()) : decoded
            let fileURL = self.root.appendingPathComponent(relative).standardizedFileURL
            let rootPath = self.root.path
            let filePath = fileURL.path
            let insideRoot = filePath == rootPath || filePath.hasPrefix(rootPath + "/")
            guard insideRoot, FileManager.default.fileExists(atPath: filePath) else {
                self.send(status: 404, headers: [:], body: Data(), on: connection)
                return
            }
            guard let body = try? Data(contentsOf: fileURL) else {
                self.send(status: 404, headers: [:], body: Data(), on: connection)
                return
            }
            let contentType = Self.mime(for: filePath)
            self.send(
                status: 200,
                headers: [
                    "Content-Type": contentType,
                    "Cache-Control": "no-store",
                ],
                body: body,
                on: connection
            )
        }
    }

    private func send(status: Int, headers: [String: String], body: Data, on connection: NWConnection) {
        let reason = status == 200 ? "OK" : (status == 404 ? "Not Found" : "Error")
        var allHeaders = headers
        allHeaders["Content-Length"] = String(body.count)
        allHeaders["Connection"] = "close"
        var header = "HTTP/1.1 \(status) \(reason)\r\n"
        for (key, value) in allHeaders.sorted(by: { $0.key < $1.key }) {
            header += "\(key): \(value)\r\n"
        }
        header += "\r\n"
        var response = Data(header.utf8)
        response.append(body)
        connection.send(content: response, completion: .contentProcessed { _ in
            connection.cancel()
        })
    }
}

private enum RendererServerError: Error {
    case listenerTimeout
    case noPort
}
