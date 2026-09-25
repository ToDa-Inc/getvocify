import Foundation

public struct DiskFullError: Error, Equatable {
    public static let code = "ENOSPC"

    public init() {}

    public var localizedDescription: String {
        "No queda espacio para seguir grabando. El audio ya guardado se conserva."
    }
}

public final class CaptureStore {
    public let root: URL
    private let fileManager: FileManager
    private let customAppendFile: ((URL, Data) throws -> Void)?

    public init(
        root: URL,
        fileManager: FileManager = .default,
        appendFile: ((URL, Data) throws -> Void)? = nil
    ) {
        self.root = root.standardizedFileURL
        self.fileManager = fileManager
        self.customAppendFile = appendFile
        try? fileManager.createDirectory(at: self.root, withIntermediateDirectories: true)
    }

    public static func defaultCapturesRoot(fileManager: FileManager = .default) -> URL {
        let appSupport = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        return appSupport.appendingPathComponent("Vocify/captures", isDirectory: true)
    }

    @discardableResult
    public func begin(clientCaptureId: String, meta: [String: Any] = [:]) throws -> [String: Any] {
        let dir = captureDir(clientCaptureId)
        try fileManager.createDirectory(at: dir, withIntermediateDirectories: true)
        let manifestURL = manifestPath(clientCaptureId)
        if !fileManager.fileExists(atPath: manifestURL.path) {
            let startedAt = meta["startedAt"] as? String
            try write(emptyManifest(clientCaptureId: clientCaptureId, startedAt: startedAt), clientCaptureId: clientCaptureId)
        }
        return try read(clientCaptureId: clientCaptureId)
    }

    @discardableResult
    public func append(clientCaptureId: String, channel: String, chunk: Data) throws -> [String: Any] {
        _ = try begin(clientCaptureId: clientCaptureId)
        var manifest = try read(clientCaptureId: clientCaptureId)
        var channels = manifest["channels"] as? [String: Any] ?? [:]
        let current = channels[channel] as? [String: Any] ?? [:]
        if current["absent"] as? Bool == true {
            throw NSError(
                domain: "CaptureStore",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "El canal \(channel) está marcado como ausente"]
            )
        }

        let dir = captureDir(clientCaptureId)
        let audioPath = (current["path"] as? String).map { URL(fileURLWithPath: $0) }
            ?? dir.appendingPathComponent("\(channel).bin")

        do {
            try appendData(to: audioPath, chunk: chunk)
        } catch let error as DiskFullError {
            throw error
        } catch {
            if Self.isDiskFull(error) {
                throw DiskFullError()
            }
            throw error
        }

        let previousBytes = current["bytes"] as? Int ?? 0
        channels[channel] = [
            "path": audioPath.path,
            "bytes": previousBytes + chunk.count,
            "absent": false,
        ] as [String: Any]
        manifest["channels"] = channels
        refresh(&manifest)
        try write(manifest, clientCaptureId: clientCaptureId)
        return manifest
    }

    @discardableResult
    public func noteChannelAbsent(clientCaptureId: String, channel: String, reason: String?) throws -> [String: Any] {
        _ = try begin(clientCaptureId: clientCaptureId)
        var manifest = try read(clientCaptureId: clientCaptureId)
        var channels = manifest["channels"] as? [String: Any] ?? [:]
        let previous = channels[channel] as? [String: Any] ?? [:]
        var next = previous
        next["absent"] = true
        next["reason"] = reason ?? "absent"
        channels[channel] = next
        manifest["channels"] = channels
        refresh(&manifest)
        try write(manifest, clientCaptureId: clientCaptureId)
        return manifest
    }

    public func read(clientCaptureId: String) throws -> [String: Any] {
        let data = try Data(contentsOf: manifestPath(clientCaptureId))
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw NSError(domain: "CaptureStore", code: 2, userInfo: [NSLocalizedDescriptionKey: "Invalid manifest"])
        }
        return json
    }

    public func pending() -> [[String: Any]] {
        guard let names = try? fileManager.contentsOfDirectory(atPath: root.path) else { return [] }
        return names.compactMap { name -> [String: Any]? in
            do {
                let manifest = try read(clientCaptureId: name)
                if manifest["remoteConfirmed"] as? Bool == false {
                    return manifest
                }
                return nil
            } catch {
                return nil
            }
        }
    }

    @discardableResult
    public func confirmRemote(clientCaptureId: String) throws -> [String: Any] {
        var manifest = try read(clientCaptureId: clientCaptureId)
        manifest["remoteConfirmed"] = true
        try write(manifest, clientCaptureId: clientCaptureId)
        return manifest
    }

    public func discard(clientCaptureId: String) throws {
        let manifest = try read(clientCaptureId: clientCaptureId)
        if manifest["remoteConfirmed"] as? Bool != true {
            throw NSError(
                domain: "CaptureStore",
                code: 3,
                userInfo: [NSLocalizedDescriptionKey: "No se borra la captura local antes de la confirmación remota"]
            )
        }
        try fileManager.removeItem(at: captureDir(clientCaptureId))
    }

    private func emptyManifest(clientCaptureId: String, startedAt: String?) -> [String: Any] {
        [
            "clientCaptureId": clientCaptureId,
            "startedAt": startedAt as Any? ?? NSNull(),
            "remoteConfirmed": false,
            "audioStatus": "partial",
            "channelsComplete": false,
            "channels": [String: Any](),
        ]
    }

    private func refresh(_ manifest: inout [String: Any]) {
        let channels = manifest["channels"] as? [String: Any] ?? [:]
        let mic = channels["mic"] as? [String: Any]
        let system = channels["system"] as? [String: Any]
        let micOk = channelHasAudio(mic)
        let systemOk = channelHasAudio(system)
        manifest["channelsComplete"] = micOk && systemOk
        manifest["audioStatus"] = (micOk && systemOk) ? "complete" : "partial"
    }

    private func channelHasAudio(_ channel: [String: Any]?) -> Bool {
        guard let channel else { return false }
        if channel["absent"] as? Bool == true { return false }
        return (channel["bytes"] as? Int ?? 0) > 0
    }

    private func captureDir(_ clientCaptureId: String) -> URL {
        root.appendingPathComponent(clientCaptureId, isDirectory: true)
    }

    private func manifestPath(_ clientCaptureId: String) -> URL {
        captureDir(clientCaptureId).appendingPathComponent("manifest.json")
    }

    private func write(_ manifest: [String: Any], clientCaptureId: String) throws {
        try fileManager.createDirectory(at: captureDir(clientCaptureId), withIntermediateDirectories: true)
        let data = try JSONSerialization.data(withJSONObject: manifest)
        try data.write(to: manifestPath(clientCaptureId), options: .atomic)
    }

    private func appendData(to url: URL, chunk: Data) throws {
        if let customAppendFile {
            try customAppendFile(url, chunk)
            return
        }
        if fileManager.fileExists(atPath: url.path) {
            let handle = try FileHandle(forWritingTo: url)
            defer { try? handle.close() }
            try handle.seekToEnd()
            try handle.write(contentsOf: chunk)
        } else {
            try chunk.write(to: url, options: .atomic)
        }
    }

    private static func isDiskFull(_ error: Error) -> Bool {
        if error is DiskFullError { return true }
        let ns = error as NSError
        if ns.domain == NSPOSIXErrorDomain, ns.code == Int(POSIXError.ENOSPC.rawValue) { return true }
        if ns.domain == NSCocoaErrorDomain, ns.code == NSFileWriteOutOfSpaceError { return true }
        if let underlying = ns.userInfo[NSUnderlyingErrorKey] as? NSError {
            return isDiskFull(underlying)
        }
        return false
    }
}
