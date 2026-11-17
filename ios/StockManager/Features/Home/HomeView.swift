import SwiftUI

struct HomeView: View {
    @Binding var selectedTab: AppTab
    @Environment(InventoryStore.self) private var inventory
    @Environment(RestockStore.self) private var restock
    @Environment(RecipeStore.self) private var recipes
    @State private var recommendationState: LoadState<RecommendationSnapshot> = .idle

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 20) {
                Text("今天的家庭库存").font(.largeTitle.bold())
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 145))], spacing: 12) {
                    metric("有效库存", count: inventory.items.filter { $0.status == .active }.count, icon: "shippingbox", color: .blue) { selectedTab = .inventory }
                    metric("即将过期", count: inventory.items.filter { $0.status == .expiringSoon }.count, icon: "clock.badge.exclamationmark", color: .orange) { }
                    metric("已经过期", count: inventory.items.filter { $0.status == .expired }.count, icon: "exclamationmark.triangle", color: .red) { }
                    metric("待补货", count: restock.items.filter { $0.status == .pending }.count, icon: "cart", color: .green) { selectedTab = .restock }
                }
                NavigationLink { ReminderView() } label: {
                    Label("查看过期提醒", systemImage: "bell.badge").frame(maxWidth: .infinity, alignment: .leading)
                        .padding().background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))
                }.buttonStyle(.plain)

                HStack { Text("今日推荐").font(.title2.bold()); Spacer(); Button("全部菜谱") { selectedTab = .recipes } }
                switch recommendationState {
                case .idle, .loading: ProgressView().frame(maxWidth: .infinity, minHeight: 120)
                case .failed(let message): FailureView(message: message) { Task { await loadRecommendations() } }
                case .loaded(let snapshot) where snapshot.recommendations.isEmpty:
                    ContentUnavailableView("暂无推荐", systemImage: "fork.knife", description: Text(snapshot.emptyMessage))
                        .frame(minHeight: 180)
                case .loaded(let snapshot):
                    ForEach(snapshot.recommendations.prefix(5)) { item in
                        NavigationLink { RecipeDetailView(recipeID: item.recipeId) } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(item.title).font(.headline)
                                if let reason = item.reason { Text(reason).font(.subheadline).foregroundStyle(.secondary).lineLimit(2) }
                                HStack { if !item.expiringInventoryItems.isEmpty { Label("优先消耗", systemImage: "clock").foregroundStyle(.orange) }; Spacer(); Text("匹配 \(item.matchedInventoryItems.count)") }
                                    .font(.caption)
                            }.padding().background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 14))
                        }.buttonStyle(.plain)
                    }
                }
            }.padding()
        }
        .navigationTitle("首页").navigationBarTitleDisplayMode(.inline)
        .toolbar { Button { Task { await reload() } } label: { Image(systemName: "arrow.clockwise") } }
        .task { await reload() }.refreshable { await reload() }
    }

    private func metric(_ title: String, count: Int, icon: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 10) {
                Image(systemName: icon).font(.title2).foregroundStyle(color)
                Text(count.formatted()).font(.system(.largeTitle, design: .rounded).bold())
                Text(title).foregroundStyle(.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading).padding().background(color.opacity(0.1), in: RoundedRectangle(cornerRadius: 16))
        }.buttonStyle(.plain)
    }

    private func reload() async {
        async let a: Void = inventory.load(); async let b: Void = restock.load(); async let c: Void = loadRecommendations()
        _ = await (a, b, c)
    }

    private func loadRecommendations() async {
        recommendationState = .loading
        do { recommendationState = .loaded(try await recipes.recommendations(scene: .all)) }
        catch is CancellationError { return }
        catch { recommendationState = .failed(error.localizedDescription) }
    }
}
