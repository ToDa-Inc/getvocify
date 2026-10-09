import Foundation
import ScreenCaptureKit
import CoreMedia
import AVFoundation

enum TapError: Error {
    case noDisplay
}

final class SystemAudioTap: NSObject, SCStreamOutput, SCStreamDelegate {
    private var stream: SCStream?

    func start() async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else { throw TapError.noDisplay }
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
        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: DispatchQueue(label: "vocify.system-audio"))
        try await stream.startCapture()
        self.stream = stream
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio else { return }
        guard let data = Self.s16leMono(sampleBuffer) else { return }
        data.withUnsafeBytes { raw in
            guard let base = raw.baseAddress else { return }
            _ = fwrite(base, 1, raw.count, stdout)
        }
        fflush(stdout)
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        fputs("vocify-tap: \(error.localizedDescription)\n", stderr)
        exit(1)
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

let tap = SystemAudioTap()
signal(SIGTERM) { _ in exit(0) }
signal(SIGINT) { _ in exit(0) }

Task {
    do {
        try await tap.start()
    } catch {
        fputs("vocify-tap: \(error.localizedDescription)\n", stderr)
        exit(1)
    }
}

RunLoop.main.run()
