import Foundation

public enum SaasProxy {
    public static func isAllowedApiBase(_ base: String) -> Bool {
        let trimmed = base.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed), let host = url.host else { return false }
        let scheme = url.scheme?.lowercased()
        guard scheme == "https" || scheme == "http" else { return false }
        if host == "api.getvocify.com" { return scheme == "https" }
        if host == "localhost" || host == "127.0.0.1" { return true }
        return false
    }

    public static func parseResponseBody(_ data: Data) -> Any {
        if data.isEmpty { return [:] as [String: Any] }
        do {
            return try JSONSerialization.jsonObject(with: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                return ["raw": text]
            }
            return [:] as [String: Any]
        }
    }

    public static func request(_ payload: [String: Any]) async -> [String: Any] {
        let base = payload["base"] as? String ?? ""
        guard isAllowedApiBase(base) else {
            return ["ok": false, "status": 0, "data": [:] as [String: Any], "error": "API base is not a Vocify host"]
        }

        let path = payload["path"] as? String ?? ""
        let method = (payload["method"] as? String ?? "GET").uppercased()
        let headers = payload["headers"] as? [String: String] ?? [:]
        let urlString = joinApiUrl(base: base, path: path)
        guard let url = URL(string: urlString) else {
            return ["ok": false, "status": 0, "data": [:] as [String: Any], "error": "Invalid URL"]
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        for (key, value) in headers {
            request.setValue(value, forHTTPHeaderField: key)
        }
        if let body = payload["body"] {
            if request.value(forHTTPHeaderField: "Content-Type") == nil {
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            }
            if let data = try? JSONSerialization.data(withJSONObject: body) {
                request.httpBody = data
            }
        }

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            let parsed = parseResponseBody(data)
            let ok = (200 ... 299).contains(status)
            if ok {
                return ["ok": true, "status": status, "data": parsed]
            }
            var error = "HTTP \(status)"
            if let dict = parsed as? [String: Any],
               let detail = dict["detail"] as? String,
               !detail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                error = detail
            }
            return ["ok": false, "status": status, "data": parsed, "error": error]
        } catch {
            return ["ok": false, "status": 0, "data": [:] as [String: Any], "error": error.localizedDescription]
        }
    }

    static func joinApiUrl(base: String, path: String) -> String {
        var root = base.trimmingCharacters(in: .whitespacesAndNewlines)
        while root.hasSuffix("/") { root.removeLast() }
        var suffix = path.trimmingCharacters(in: .whitespacesAndNewlines)
        if root.isEmpty {
            return suffix.hasPrefix("/") ? suffix : "/\(suffix)"
        }
        if !suffix.hasPrefix("/") { suffix = "/\(suffix)" }
        return "\(root)\(suffix)"
    }
}
