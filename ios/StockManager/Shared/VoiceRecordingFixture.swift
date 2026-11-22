#if DEBUG
import AVFoundation

@MainActor
enum VoiceRecordingFixture {
    static func make() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString).appendingPathExtension("wav")
        let rate = VoiceRecorder.sampleRate
        guard let format = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: Double(rate),
                                         channels: 1, interleaved: true),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(rate * 3)),
              let samples = buffer.int16ChannelData?.pointee else { throw VoiceRecorder.Failure.recordingFailed }
        buffer.frameLength = buffer.frameCapacity
        samples.update(repeating: 0, count: Int(buffer.frameLength))

        do {
            let file = try AVAudioFile(forWriting: url, settings: VoiceRecorder.settings,
                                       commonFormat: .pcmFormatInt16, interleaved: true)
            try file.write(from: buffer)
            return url
        } catch {
            try? FileManager.default.removeItem(at: url)
            throw error
        }
    }
}
#endif
