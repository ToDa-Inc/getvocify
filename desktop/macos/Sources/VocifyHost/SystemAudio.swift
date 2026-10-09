import AVFoundation
import CoreMedia
import Foundation
import ScreenCaptureKit

enum SystemAudioError: Error {
    case noDisplay
}

final class SystemAudio: NSObject, SCStreamOutput, SCStreamDelegate {
    private var stream: SCStream?
    private var pcmHandler: ((Data) -> Void)?
    private var lostHandler: ((Error) -> Void)?
    private let sampleQueue = DispatchQueue(label: "vocify.system-audio")
    private let handlerQueue = DispatchQueue(label: "vocify.system-audio.handlers")

    func setHandlers(onPcm: ((Data) -> Void)?, onLost: ((Error) -> Void)?) {
        handlerQueue.sync {
            pcmHandler = onPcm
            lostHandler = onLost
        }
    }

    func start() async throws {
        await stopStreamOnly()
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else { throw SystemAudioError.noDisplay }
        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.showsCursor = false
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        config.sampleRate = 16_000
        config.channelCount = 1

        let stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: sampleQueue)
        try await stream.startCapture()
        self.stream = stream
    }

    func stop() async {
        await stopStreamOnly()
        handlerQueue.sync {
            pcmHandler = nil
            lostHandler = nil
        }
    }

    private func stopStreamOnly() async {
        let active = stream
        stream = nil
        if let active {
            try? await active.stopCapture()
        }
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio else { return }
        guard let data = Self.s16leMono(sampleBuffer) else { return }
        let handler = handlerQueue.sync { pcmHandler }
        handler?(data)
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        fputs("VocifyHost system-audio: \(error.localizedDescription)\n", stderr)
        Task {
            guard self.stream === stream else { return }
            self.stream = nil
            let lost: ((Error) -> Void)? = handlerQueue.sync {
                defer {
                    pcmHandler = nil
                    lostHandler = nil
                }
                return lostHandler
            }
            guard let lost else { return }
            await MainActor.run {
                lost(error)
            }
        }
    }

    private static func s16leMono(_ sampleBuffer: CMSampleBuffer) -> Data? {
        guard let format = CMSampleBufferGetFormatDescription(sampleBuffer) else { return nil }
        guard let asbdPointer = CMAudioFormatDescriptionGetStreamBasicDescription(format) else { return nil }
        let asbd = asbdPointer.pointee
        var blockBuffer: CMBlockBuffer?
        var audioBufferList = AudioBufferList()
        let status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: nil,
            bufferListOut: &audioBufferList,
            bufferListSize: MemoryLayout<AudioBufferList>.size,
            blockBufferAllocator: nil,
            blockBufferMemoryAllocator: nil,
            flags: 0,
            blockBufferOut: &blockBuffer
        )
        guard status == noErr else { return nil }
        let buffer = audioBufferList.mBuffers
        guard buffer.mDataByteSize > 0, let pointer = buffer.mData else { return nil }
        let channels = max(Int(asbd.mChannelsPerFrame), 1)
        let rate = Int(asbd.mSampleRate == 0 ? 16_000 : asbd.mSampleRate)
        let stride = max(Int(rate / 16_000), 1)

        if asbd.mFormatFlags & kAudioFormatFlagIsFloat != 0 {
            let count = Int(buffer.mDataByteSize) / MemoryLayout<Float>.size
            let samples = UnsafeBufferPointer(start: pointer.assumingMemoryBound(to: Float.self), count: count)
            return encodeDownsampled(samples, channels: channels, stride: stride)
        }

        let count = Int(buffer.mDataByteSize) / MemoryLayout<Int16>.size
        let samples = UnsafeBufferPointer(start: pointer.assumingMemoryBound(to: Int16.self), count: count)
        var out = Data()
        var index = 0
        while index < samples.count {
            out.append(contentsOf: withUnsafeBytes(of: samples[index].littleEndian) { Array($0) })
            index += channels * stride
        }
        return out
    }

    private static func encodeDownsampled(_ samples: UnsafeBufferPointer<Float>, channels: Int, stride: Int) -> Data {
        var out = Data()
        var index = 0
        while index < samples.count {
            let clipped = max(-1.0, min(1.0, samples[index]))
            let int16 = clipped < 0 ? Int16(clipped * 32768.0) : Int16(clipped * 32767.0)
            out.append(contentsOf: withUnsafeBytes(of: int16.littleEndian) { Array($0) })
            index += channels * stride
        }
        return out
    }
}
