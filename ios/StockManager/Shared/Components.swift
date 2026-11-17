import SwiftUI

struct LoadingView: View {
    var text = "正在加载…"
    var body: some View { ProgressView(text).frame(maxWidth: .infinity, maxHeight: .infinity) }
}

struct EmptyStateView: View {
    let title: String; let message: String; var icon = "tray"
    var body: some View {
        ContentUnavailableView(title, systemImage: icon, description: Text(message))
    }
}

struct FailureView: View {
    let message: String; let retry: () -> Void
    var body: some View {
        ContentUnavailableView {
            Label("加载失败", systemImage: "exclamationmark.triangle")
        } description: { Text(message) } actions: { Button("重试", action: retry).buttonStyle(.borderedProminent) }
    }
}

struct StatusBadge: View {
    let status: ItemStatus
    var color: Color {
        switch status { case .active: .green; case .consumed: .secondary; case .expiringSoon: .orange; case .expired: .red }
    }
    var body: some View {
        Text(status.title).font(.caption.weight(.semibold)).foregroundStyle(color)
            .padding(.horizontal, 8).padding(.vertical, 4).background(color.opacity(0.12), in: Capsule())
    }
}

struct ErrorAlert: ViewModifier {
    @Binding var message: String?
    func body(content: Content) -> some View {
        content.alert("操作失败", isPresented: Binding(get: { message != nil }, set: { if !$0 { message = nil } })) {
            Button("好", role: .cancel) { message = nil }
        } message: { Text(message ?? "") }
    }
}

extension View { func errorAlert(_ message: Binding<String?>) -> some View { modifier(ErrorAlert(message: message)) } }

struct SavingOverlay: ViewModifier {
    let saving: Bool
    func body(content: Content) -> some View {
        content.overlay { if saving { ZStack { Color.black.opacity(0.12).ignoresSafeArea(); ProgressView().padding(24).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16)) } } }
    }
}
extension View { func savingOverlay(_ saving: Bool) -> some View { modifier(SavingOverlay(saving: saving)) } }

struct LabeledValue: View {
    let label: String; let value: String
    var body: some View { LabeledContent(label) { Text(value).foregroundStyle(.secondary) } }
}
