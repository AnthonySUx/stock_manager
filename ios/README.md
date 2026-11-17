# Stock Manager iOS

原生 SwiftUI 客户端，最低支持 iOS 17，兼容 iPhone 与 iPad。客户端只调用仓库中的 FastAPI 后端，不包含离线数据库或第三方运行时依赖。

异步、导航、表单和连接流程的状态约定见 [STATE_MACHINES.md](STATE_MACHINES.md)。新增流程时应复用其中的状态原语，避免并列布尔值产生互相矛盾的界面状态。

## 运行

1. 在仓库根目录启动 MySQL、迁移和后端：

   ```bash
   docker compose up -d
   source .venv/bin/activate
   alembic upgrade head
   uvicorn stock_manager.api.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. 确保后端配置了 `API_TOKEN`。仅本地开发时也可显式设置 `API_AUTH_DISABLED=true`，但 App 的连接表单仍要求输入一个非空令牌。
3. 打开 `StockManager.xcodeproj`，选择 `StockManager` scheme 和 iPhone/iPad 模拟器。
4. 首次启动输入 API 根地址，例如 `http://localhost:8000/api`，以及共享令牌。连接真实设备时请改用 Mac 的局域网地址；生产环境应使用 HTTPS。

## 本机签名配置

模拟器构建不需要 Apple Developer Team。真机运行时，将示例配置复制为仅在本机保存的配置：

```bash
cp ios/Config/Local.xcconfig.example ios/Config/Local.xcconfig
```

打开 `ios/Config/Local.xcconfig`，把 `YOUR_TEAM_ID` 替换为 Xcode 中显示的 Team ID。该文件已被 Git 忽略；Debug、Release、单元测试和 UI 测试会自动读取它，因此共享工程不会包含个人 Team ID。

## 构建和测试

```bash
./scripts/build.sh build
./scripts/build.sh test       # 需要可用的 iOS Simulator
```

测试默认使用 `iPhone 17`。如果本机设备名称不同，可设置 `IOS_TEST_DESTINATION`，例如：

```bash
IOS_TEST_DESTINATION='platform=iOS Simulator,name=iPad (A16)' ./scripts/build.sh test
```

真实后端 UI 冒烟测试需要向测试进程提供 `STOCK_MANAGER_UI_URL` 与 `STOCK_MANAGER_UI_TOKEN`。未提供时该用例自动跳过。

## 安全与数据

- 服务器地址保存在 `UserDefaults`。
- API 令牌使用 Apple Security API 存在 `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` Keychain 项中。
- App 不打印或显示已保存令牌。
- 删除库存、补货、菜谱、分类和批量清理前都会再次确认。

## 已知开发环境要求

Xcode 和 macOS 自带的 CoreSimulator 必须为匹配版本。如果出现 `CoreSimulator is out of date` 或 Swift macro plugin malformed response，请先完成 macOS/Xcode 更新；不要通过修改项目代码绕过。
