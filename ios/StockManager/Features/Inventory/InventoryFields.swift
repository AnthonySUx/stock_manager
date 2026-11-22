import SwiftUI

struct InventoryTextField: View {
    enum Field {
        case name, owner, location, quantity, unit

        var title: String {
            switch self {
            case .name: "名称"
            case .owner: "所有者"
            case .location: "位置"
            case .quantity: "数量"
            case .unit: "单位"
            }
        }
    }

    let field: Field
    @Binding var text: String

    init(_ field: Field, text: Binding<String>) {
        self.field = field
        _text = text
    }

    var body: some View {
        TextField(field.title, text: $text)
            .keyboardType(field == .quantity ? .decimalPad : .default)
    }
}

struct InventoryCategoryPicker: View {
    let categories: [Category]
    @Binding var selection: Int?

    var body: some View {
        Picker("分类", selection: $selection) {
            Text("请选择").tag(Int?.none)
            if let selection, !categories.contains(where: { $0.id == selection }) {
                Text("分类 \(selection)").tag(Optional(selection))
            }
            ForEach(categories) { Text($0.name).tag(Optional($0.id)) }
        }
    }
}
