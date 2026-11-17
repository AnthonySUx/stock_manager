import SwiftUI

/// A single source of truth for one user-triggered asynchronous operation.
/// Invalid combinations such as `isSaving == false` plus a stale error cannot exist.
enum ActionState: Equatable {
    case idle
    case running
    case failed(String)
    case succeeded(String?)

    var isRunning: Bool { if case .running = self { true } else { false } }
    var errorMessage: String? { if case .failed(let message) = self { message } else { nil } }
}

private struct ActionErrorAlert: ViewModifier {
    @Binding var state: ActionState

    func body(content: Content) -> some View {
        content.alert("操作失败", isPresented: Binding(
            get: { state.errorMessage != nil },
            set: { if !$0 { state = .idle } }
        )) {
            Button("好", role: .cancel) { state = .idle }
        } message: {
            Text(state.errorMessage ?? "")
        }
    }
}

extension View {
    func actionErrorAlert(_ state: Binding<ActionState>) -> some View {
        modifier(ActionErrorAlert(state: state))
    }
}

enum ExpirationChoice: Hashable {
    case infinite
    case dated(Date)

    var apiValue: String {
        switch self { case .infinite: "infinite"; case .dated(let date): API.string(date) }
    }
}

/// Loading state for collection stores. The collection itself remains the only
/// source of data, so phase and content cannot silently drift apart.
enum LoadPhase: Equatable {
    case idle
    case loading
    case loaded
    case failed(String)
}
