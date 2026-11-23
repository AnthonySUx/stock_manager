# Stock Manager iOS 设计规范

本文档是 iOS 客户端的设计地基。页面骨架坚持 Apple 原生 SwiftUI：系统语义色、Dynamic Type 字体档位、SF Symbols、`List` / `Form`、系统导航与搜索。色卡只改变强调、选中、分类和状态表达，不改变背景与正文颜色。

## 1. 颜色

### 系统语义色与色卡边界

- 页面、列表、表单与卡片背景必须使用系统语义背景（例如 `systemBackground`、`secondarySystemGroupedBackground`、Material），不得由色卡改变。
- 正文、标题、辅助文字必须使用系统 `primary`、`secondary`、`tertiary`；分隔线使用系统默认 separator / `List` 分隔线。不得写死黑、白或灰作为普通背景和文字。
- 当前色卡的 `theme.accent` 仅用于主按钮、Tab / 侧栏选中态、可交互强调图标和系统 tint。
- `theme.categories` 仅用于分类、标签和图表。不得用分类颜色替代文字标签；Okabe-Ito 下尤其不得只以红/绿表达差异。
- 状态色固定映射到语义 token：正常 `statusActive`、快过期 `statusExpiring`、已过期 `statusExpired`、已消耗 `statusConsumed`。`StatusBadge` 必须同时显示状态文字、不同 SF Symbol 与颜色；文字保持系统主文字色以确保低对比色卡也可读。
- Paul Tol 的 `#DDDDDD` 只保留给“缺失/不适用”，不得用于普通分类或已消耗状态。

### 色值表

“系统动态”表示直接使用 SwiftUI 系统色，浅色基准值列于括号中，深色由 UIKit/SwiftUI 自带动态色提供。③④ 的深色值是在不改变色相角色的前提下提高亮度的派生值。

| 套装 | 主强调色（浅 / 深） | 辅助色（浅 / 深） | 状态：正常 / 快过期 / 已过期 / 已消耗 |
|---|---|---|---|
| 默认 | system blue / 系统动态 | system blue、green、yellow、pink、orange、purple / 系统动态 | system green / orange / red / secondary（均系统动态） |
| 色盲友好（Okabe-Ito） | `#0072B2` / `#4FA9DD` | `#0072B2/#4FA9DD`、`#E69F00/#F2B94B`、`#56B4E9/#78C8F0`、`#009E73/#42C99B`、`#F0E442/#F5EA70`、`#D55E00/#F08A42`、`#CC79A7/#E39BC2`、`#000000/#BFBFBF` | `#009E73/#42C99B` / `#E69F00/#F2B94B` / `#D55E00/#F08A42` / `#000000/#BFBFBF` |
| 低饱和（Paul Tol Muted） | `#332288` / `#8F80D8` | `#332288/#8F80D8`、`#CC6677/#F08FA0`、`#DDCC77/#E7D991`、`#117733/#5BD69A`、`#88CCEE/#A8DDF5`、`#882255/#D472A0`、`#44AA99/#74CFBF`、`#999933/#D0D06A`、`#AA4499/#D77BC7` | `#117733/#5BD69A` / `#999933/#D0D06A` / `#CC6677/#F08FA0` / `#332288/#8F80D8` |

浅色主强调色在白色背景上的对比度：Okabe-Ito `#0072B2` 为 5.19:1，Tol Muted `#332288` 为 12.17:1。深色主强调色在黑色背景上的对比度：`#4FA9DD` 为 8.05:1，`#8F80D8` 为 6.25:1。系统 blue 使用 Apple 动态色；主按钮采用 headline 粗体及实色背景。状态徽标的文字不使用状态色，因此黄、橙等较低对比颜色不会降低文字可读性。

色卡来源：Apple system colors；Okabe-Ito / Color Universal Design；Paul Tol, *Colour schemes* / SRON technical note。

## 2. 字体层级

| 角色 | 系统字体档位 |
|---|---|
| 页面主角、核心数字 | `.largeTitle`（需要强调可加 `.bold()`） |
| 分区标题 | `.title2` 或系统 `Section` header |
| 列表行标题 | `.headline` |
| 辅助文字 | `.subheadline`、`.footnote`、`.caption`；更弱元数据可用 `.caption2` |

所有字体必须使用支持 Dynamic Type 的系统档位。禁止自定义点数、禁止 `.system(size:)`，禁止 `.rounded` 等特殊设计字体。图标统一使用 SF Symbols。

## 3. 间距与圆角

- 只允许 `4 / 8 / 12 / 16 / 24`，分别通过 `AppSpacing.xSmall / small / medium / large / xLarge` 使用。
- 页面左右边距固定 `AppSpacing.page = 16`。
- 卡片圆角固定 `AppRadius.card = 16`；系统 `List`、`Form`、按钮、Capsule 等保留系统默认形状，不另设圆角。
- `spacing: 0` 只用于让相邻系统容器无额外缝隙，不是新的设计间距档位。

## 4. 共享组件清单

- `LoadingView`：全屏系统加载状态，进度 tint 跟随当前强调色。
- `EmptyStateView`：基于 `ContentUnavailableView` 的空状态。
- `FailureView`：统一错误说明与主操作重试按钮。
- `StatusBadge`：状态文字 + SF Symbol + 当前色卡状态色；禁止只靠颜色。
- `AppCard`：系统次级分组背景、16 内边距、16 圆角的统一卡片容器。
- `PrimaryActionButtonStyle`：当前强调色背景的主操作按钮样式。
- `LabeledValue`：系统 `LabeledContent` 的只读键值行。
- `SavingOverlay`：保存期间的系统 Material 阻塞层。

## 5. 交互规则

- 新增按钮永远位于导航栏右上角，使用 `plus` SF Symbol。
- 列表滑动操作全 App 统一：左滑（trailing edge）用于主要动作，例如消耗、已购买；右滑（leading edge）或长按菜单用于编辑、删除。破坏性操作必须使用系统 destructive role。
- 搜索框一律放页面顶部，使用 `.searchable` 默认位置。
- 设置与数据录入表单一律使用系统 `Form`，不自绘表单控件。
- 主操作、选中态和交互强调必须读取 `theme.accent`；页面不得直接写颜色字面值。

## 6. 导航规则

- 底部 Tab 固定为 5 个：首页、库存、补货、菜谱、设置；不增不减、不改变顺序。
- 每个 Tab 保持系统 `NavigationStack`；iPad 常规宽度保持系统 `NavigationSplitView`。
- 色卡切换不得改变导航层级、信息顺序或功能，只改变全局 tint、选中态、主操作与状态/分类颜色。
