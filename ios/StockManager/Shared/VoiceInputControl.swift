import SwiftUI
import UIKit

struct VoiceInputControl: View {
    @Environment(\.openURL) private var openURL
    let voice: VoiceInputStore
    let isAvailable: Bool
    let isDisabled: Bool
    let onStart: () -> Void

    var body: some View {
        if voice.action.isRunning {
            VStack(alignment: .leading, spacing: 10) {
                if voice.recorder.isRecording {
                    HStack {
                        Label("正在录音", systemImage: "mic.fill").foregroundStyle(.red)
                        Spacer()
                        Text("剩余 \(voice.recorder.remainingSeconds) 秒").monospacedDigit()
                    }
                    ProgressView(value: voice.recorder.level)
                        .tint(.red)
                        .accessibilityLabel("麦克风音量")
                    Button("完成录音", action: voice.recorder.stop)
                        .accessibilityIdentifier("voice.finish")
                } else {
                    ProgressView(voice.isTranscribing ? "正在转写语音…" : "正在准备录音…")
                }
                Button("取消", role: .cancel, action: voice.cancel)
                    .accessibilityIdentifier("voice.cancel")
            }
            .buttonStyle(.borderless)
        } else if isAvailable {
            Button("语音输入", systemImage: "mic", action: onStart)
                .disabled(isDisabled)
                .accessibilityIdentifier("voice.record")
        }

        if let message = voice.action.errorMessage {
            VStack(alignment: .leading, spacing: 8) {
                Label(message, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red)
                if voice.permissionDenied, let settings = URL(string: UIApplication.openSettingsURLString) {
                    Button("打开系统设置") { openURL(settings) }.buttonStyle(.borderless)
                }
            }
        }
    }
}
