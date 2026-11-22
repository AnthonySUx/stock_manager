# 前端状态机清单

这份文件是 SwiftUI 前端的状态地图。修改异步流程、表单、导航或弹窗前，先检查这里；目标是让界面只能进入有意义的状态，并让测试与自动化代理能从类型名直接理解流程。

## 统一状态原语

| 类型 | 状态 | 用途 |
| --- | --- | --- |
| `LoadState<Value>` | `idle → loading → loaded / failed` | 单个详情、提醒、设置快照、推荐和烹饪预览 |
| `LoadPhase` | `idle → loading → loaded / failed` | 已由 Store 单独持有数据的列表，避免状态里再复制一份数组 |
| `ActionState` | `idle → running → succeeded / failed` | 保存、删除、收藏、复刻、清理等用户动作 |
| `AppSessionState` | `disconnected → restoring / connecting → connected` | Keychain 恢复、首次连接和重新验证 |

失败后重试会回到 `loading` 或 `running`；取消的任务不显示错误。重新验证服务器失败时，如果此前已有可用连接，会恢复旧连接，不把用户踢回欢迎页。

## 功能状态机

- App 壳层：`AppSessionState` 决定显示欢迎页、连接进度或主界面。`client` 和 `health` 都由该状态派生，不再分别保存。
- AI 能力：连接成功、回到前台或下拉时刷新 `CapabilitiesStore`。`LoadPhase` 跟踪请求，刷新期间保留当前值，失败或切换服务器时将能力归为不可用，旧连接的响应无法覆盖新连接。
- 首页：今日推荐使用 `LoadState<[RecipeRecommendation]>`；库存与补货卡片读取各自 Store 的 `LoadPhase` 和唯一数据源。
- 库存列表：`InventoryPresentation` 独占新增、筛选和批量清理展示；列表加载使用 `LoadPhase`。
- 库存详情：`LoadState<StockItem>` 管理详情；`ItemDetailPresentation` 独占编辑、消耗和删除确认。
- 库存表单：`ExpirationChoice` 表示无限期或指定日期。新增库存时，`UnopenedExpirationSource` 区分初始值、分类保质期和手动选择。手动选择后保留该到期日。仅手动设置的购买日期会随新增请求发送。`OpeningChoice` 将开封日期与开封后期限绑定在同一状态中。
- 分类：`CategoryPresentation` 独占新增、编辑和删除确认；系统分类限制仍由后端与界面共同执行。
- 补货：`RestockFilter` 与 `RestockStatus` 取代自由字符串；`RestockPresentation` 独占新增、编辑、完成、删除和清理。
- 菜谱库：`RecipeMode` 决定菜谱库、今日推荐或探索；列表加载使用 `LoadPhase`，分页数据只保存在 `RecipeStore.recipes`。
- 菜谱分页：`PaginationState` 明确区分可加载、正在加载和已到底，防止列表尾部重复触发相同页；偏移量直接由当前数组数量派生，请求代次确保较旧搜索结果不能覆盖新筛选结果。
- 菜谱详情：`LoadState<Recipe>` 管理详情；`RecipeDetailPresentation` 独占编辑、烹饪和删除确认。
- 烹饪：`LoadState<ConsumePreview>` 管理扣库存预览；提交使用 `ActionState`，预览未完成时不能提交。
- AI 探索：`ExploreState` 在流式生成中逐张发布创意，收到 `done` 后才显示最终警告。停止和离开页面均取消请求，并保留已收到的创意。流内错误或 502 保留当前创意并提供原请求的重试操作。503 立即禁用 AI 文本操作并刷新能力；已有菜谱仍可打开。
- 设置：设置与来源作为一个 `SettingsSnapshot` 原子加载。`HouseholdSettingsDraft` 仅提交与已保存快照不同的字段，成功则采用服务器返回值，422 则恢复快照。`SettingsPresentation` 独占连接编辑和断开确认。

- AI 入库：`IntakeStore` 在内存维护草稿。`ActionState` 避免解析、确认和编辑重叠。解析和确认前检查草稿字段，错误定位到候选条目和字段。解析按顺序在暂存副本应用操作。解析失败或确认被拒绝时保留草稿。确认一旦发出，即使调用任务取消也继续执行。成功后按临时 ID 移除已创建的条目，再刷新库存和补货。后端字段错误绑定到请求里的临时 ID。

- 入库界面：连接期间共享同一个入库草稿。全屏审核期间，解析与确认独占操作状态，禁用重复提交和关闭。条目编辑采用局部副本，保存才替换草稿，清空日期写入 `nil`。校验问题在草稿条目及对应编辑字段标出。

## 约束

1. 不要同时添加 `isLoading`、`error` 和可选结果来描述同一请求；使用 `LoadState`。
2. 不要同时添加 `isSaving` 和 `error` 来描述同一动作；使用 `ActionState`。
3. 同一页面的 sheet、alert 和 confirmation dialog 使用一个带关联值的 `Presentation` 枚举。
4. API 的有限字符串集合使用 `String` 原始值枚举；只有真正自由输入的字段保留 `String`。
5. 派生值（例如 `isConnected`、`isRunning`）只做计算属性，不另存一份可变状态。
6. 列表 Store 使用 `LoadPhase + items`；详情使用 `LoadState<Value>`，不要在两处保存同一数据。
7. 新增状态后，在单元测试里覆盖解码值、派生值和关键恢复路径，并更新本文件。

