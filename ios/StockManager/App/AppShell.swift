import SwiftUI

enum AppTab: String, CaseIterable, Identifiable {
    case home, inventory, restock, recipes, settings
    var id: String { rawValue }
    var title: String { switch self { case .home: "首页"; case .inventory: "库存"; case .restock: "补货"; case .recipes: "菜谱"; case .settings: "设置" } }
    var icon: String { switch self { case .home: "house"; case .inventory: "shippingbox"; case .restock: "cart"; case .recipes: "fork.knife"; case .settings: "gearshape" } }
}

struct ConnectedAppView: View {
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var selected: AppTab = .home
    @State private var inventory: InventoryStore
    @State private var categories: CategoryStore
    @State private var restock: RestockStore
    @State private var recipes: RecipeStore

    init(client: any APIClientProtocol) {
        _inventory = State(initialValue: InventoryStore(client: client))
        _categories = State(initialValue: CategoryStore(client: client))
        _restock = State(initialValue: RestockStore(client: client))
        _recipes = State(initialValue: RecipeStore(client: client))
    }

    var body: some View {
        Group {
            if sizeClass == .regular {
                NavigationSplitView {
                    List(AppTab.allCases) { tab in
                        Button { selected = tab } label: {
                            Label(tab.title, systemImage: tab.icon)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .foregroundStyle(selected == tab ? Color.accentColor : Color.primary)
                        }.buttonStyle(.plain).listRowBackground(selected == tab ? Color.accentColor.opacity(0.12) : Color.clear)
                    }
                        .navigationTitle("Stock Manager")
                } detail: { NavigationStack { tabContent(selected) } }
            } else {
                TabView(selection: $selected) {
                    ForEach(AppTab.allCases) { tab in
                        NavigationStack { tabContent(tab) }.tabItem { Label(tab.title, systemImage: tab.icon) }.tag(tab)
                    }
                }
            }
        }
        .environment(inventory).environment(categories).environment(restock).environment(recipes)
    }

    @ViewBuilder private func tabContent(_ tab: AppTab) -> some View {
        switch tab {
        case .home: HomeView(selectedTab: $selected)
        case .inventory: InventoryListView()
        case .restock: RestockListView()
        case .recipes: RecipeLibraryView()
        case .settings: SettingsView()
        }
    }
}
