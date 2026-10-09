# Android Use

通过 **MCP + UIAutomator2 + USB ADB** 观察和操作安卓真机，提供 11 个工具、JSON 命令行和持久化会话。Python 3.12，支持 Windows、macOS、Linux；已在 Windows + Android 15 真机验证。

```text
AI / MCP 客户端
    ↓ MCP stdio（结构化结果 + JPEG 图片）
Android Use 控制器
    ↓ uiautomator2 / ADB
手机端 UI Automator 服务
    ↓
读取控件、点击、滑动、输入、启动 App
```

工具本身不调用模型 API，不需要 API Key。模型通过 MCP 获取界面并决定动作。移动端服务由 `uiautomator2` 首次连接时部署；无需 root。

## 安装与设备检查

准备 Python 3.12、[uv](https://docs.astral.sh/uv/getting-started/installation/) 和 [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools)，确保 `adb` 可在终端使用。

手机开启开发者选项、USB 调试，使用数据线连接，在手机上接受电脑的 USB 调试授权。部分厂商还需要启用 USB 输入控制权限。

```powershell
git clone https://github.com/frank9306/android-use.git
cd android-use
uv sync --frozen
adb devices -l
uv run --frozen android-use devices
uv run --frozen android-use ready
```

多台设备时，指定目标；选定后即使断线也不会自动改用其他设备：

```powershell
$env:ANDROID_SERIAL = "从 adb devices 获取的序列号"
uv run --frozen android-use ready
```

也可以使用 `android-use --serial SERIAL ready`。同一设备只允许一个 Android Use 进程持有控制权；关闭旧 MCP 会话后才能用另一个 MCP 或 CLI 进程操作。`devices` 不占用控制权。

## 接入 MCP 客户端

启动命令：

```powershell
uv run --frozen android-use-mcp
```

使用绝对项目路径配置客户端，避免依赖启动时的工作目录。例如在 Codex 中：

```powershell
codex mcp add android-use -- uv --directory "E:/private-store/myproject/private/android-use" run --frozen android-use-mcp
codex mcp list
```

也可参考 [examples/codex-mcp.toml](examples/codex-mcp.toml) 或 [examples/mcp.json](examples/mcp.json)，将示例目录改为实际克隆路径。Codex 的 stdio 配置与超时字段依据 [OpenAI 官方 MCP 文档](https://developers.openai.com/codex/mcp/)。配置后在新的客户端会话中使用工具。

可以这样发出任务：“使用 android-use 检查手机，打开设置，观察页面；每个关键动作后确认页面变化。”

## 工具接口

| MCP 工具 | 功能与关键参数 |
|---|---|
| `android_devices` | 列出设备及授权、离线状态 |
| `android_ready` | 检查执行服务、显示信息、控件树、截图 |
| `android_observe` | 当前包名、精简节点、JPEG；`screenshot`、`max_nodes`、`max_image_edge` |
| `android_find` | 按 `selector` 查询所有匹配，返回总数和有限节点 |
| `android_tap` | 唯一 `selector`、`node_id` 或 `x/y`；坐标与节点 ID 需要 `observation_id` |
| `android_swipe` | `direction` 或 `sx/sy/ex/ey`；支持观察过的区域 `bounds` |
| `android_type_text` | Unicode 替换/追加，`clear`、`verify`、`method` |
| `android_press` | `back`、`home`、`recent`、`enter` 等允许的按键 |
| `android_launch_app` | `package`、可选 `activity`；确认目标包进入前台 |
| `android_wait` | 有限等待出现/消失；`timeout` 为 0–30 秒 |
| `android_batch` | 1–20 个确定的步骤；错误后停止，返回完成步骤与失败位置 |

`Selector` 支持 `resource_id`、`text`、`text_contains`、`description`、`class_name`、`package_name`、`clickable`、`enabled`、`focused`、`scrollable`，多个字段按 AND 匹配。默认拒绝多个匹配；确实需要第几个时显式指定从 0 开始的 `index`。未知字段会报错。

`android_observe` 返回 `observation_id`、UTC `observed_at`、`screen`、`nodes`、`truncated` 和 `screenshot`。节点包含 ID、文本、资源 ID、描述、类型、包名、原生 `bounds` 与操作状态。密码节点的文本和描述会隐藏；截图仍是设备实际显示内容。前台包名取自 UI Automator；无法可靠确认的 Activity 返回 `null`。

截图按长边缩小，返回 `scale_x` / `scale_y`，MCP 同时返回可供模型查看的原生 ImageContent。坐标空间：

- `native`：当前设备屏幕像素。
- `screenshot`：返回的缩放 JPEG 像素，工具按比例换算到原生坐标。

方向滑动及其 `bounds` 只接受 `coordinate_space: "native"`；显式起止点可使用两种坐标空间。

观察保留在当前进程内，最多 32 份，60 秒过期。控件文本、状态、布局、包名、尺寸或方向变化后，旧坐标和节点 ID 会被拒绝；被动状态栏时钟、网速和电量的数值变化除外。选择器点击重新读取当前页面。动画、系统通知或状态栏布局变化也可能使坐标失效，需要重新观察。

点击、滑动和按键返回 `dispatched: true, verified: false`；这只表示已发出动作。使用新的观察或 `android_wait` 验证结果。启动 App 和默认输入读回会主动验证。输入默认 `method: "accessibility"`，通过 UI Automator 设置文本；自定义输入失败时可以**显式**选择 `method: "ime"`，部署辅助输入法、输入后恢复原输入法及启用状态。两种方式都通过真机测试。

## JSON 命令行

CLI 动作名为去掉 `android_` 前缀的工具名。参数使用 JSON；PowerShell 中使用单引号保留 JSON 的双引号：

```powershell
uv run --frozen android-use launch_app --params '{"package":"com.android.settings"}'
uv run --frozen android-use observe --image artifacts/screen.jpg
uv run --frozen android-use find --params '{"selector":{"text":"搜索"}}'
uv run --frozen android-use tap --params '{"selector":{"resource_id":"你的包名:id/search"}}'
uv run --frozen android-use type_text --params '{"text":"中文内容","selector":{"focused":true}}'
uv run --frozen android-use swipe --params '{"direction":"up"}'
uv run --frozen android-use press --params '{"key":"home"}'
uv run --frozen android-use batch --params-file examples/fixture-batch.json
```

资源 ID 和文字必须来自目标手机的实际观察。复杂参数推荐使用 `--params-file`，读取 UTF-8 JSON。截图只能写入新文件，不会覆盖已有文件。单次命令输出一个 JSON 对象，成功退出码为 0，失败为 1。

单次 CLI 命令不共享观察缓存。需要坐标操作时使用 MCP，或者保持同一个 JSON Lines 会话：

```powershell
uv run --frozen android-use session
```

依次输入并读取每行响应，第二行的观察 ID 来自第一行响应：

```json
{"action":"observe","params":{},"image_path":"artifacts/session-screen.jpg"}
{"action":"tap","params":{"x":200,"y":300,"coordinate_space":"screenshot","observation_id":"替换为上一行的 observation_id"}}
{"action":"press","params":{"key":"home"}}
```

批处理格式：

```json
{"steps":[
  {"action":"launch_app","params":{"package":"com.android.settings"}},
  {"action":"wait","params":{"selector":{"package_name":"com.android.settings"},"timeout":10}},
  {"action":"press","params":{"key":"home"}}
]}
```

批处理预先检查操作名称和参数结构；页面条件在每一步执行时检查。步骤失败不会回滚之前的动作，也不会执行后续步骤。收到 MCP 取消通知时停止后续步骤与轮询，并等待正在执行的命令结束；已经发出的手机动作不能撤销。

## 实时预览

需要实时画面时，可另行安装 [scrcpy](https://github.com/Genymobile/scrcpy) 并启动：

```powershell
scrcpy --serial "设备序列号" --no-control
```

这是独立桌面预览，不是嵌入 MCP 的视频流。`--no-control` 避免预览窗口同时操作手机。scrcpy 为可选外部软件，不是 Python 依赖；本项目的截图与操作不依赖它。

## 测试

默认测试不操作手机，覆盖 XML 契约、匹配与歧义、坐标映射、过期观察、断线、设备锁、失败停止、错误和图片的 MCP 协议、CLI 文件保护。

```powershell
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv build
```

真机验收使用 `tests/device_app` 下无网络、存储、账户权限的临时测试 App。构建需要 Android SDK 的 platform / build-tools 和 JDK 17+；无需 Gradle。

```powershell
$env:ANDROID_HOME = "C:/Users/你的用户名/AppData/Local/Android/Sdk"
$env:JAVA_HOME = "JDK 的安装目录"
uv run --frozen python scripts/build_fixture.py
adb install artifacts/fixture/fixture.apk
uv run --frozen pytest --device-serial auto
```

多台设备时用 `adb -s SERIAL install ...` 和 `pytest --device-serial SERIAL`。测试会临时旋转屏幕，随后恢复旋转设置与输入法并返回主页。如果测试中断线，原旋转设置保存在忽略的 `artifacts/device-settings-restore.json`；先按记录恢复，删除恢复文件后再复测。测试 App 不修改生产应用数据。复测已有**本项目生成**的测试 App 时可用 `adb install -r`。验收完成后可运行 `adb uninstall com.androiduse.fixture` 删除它。

版本与验证范围见 [docs/verification.md](docs/verification.md)。APK、签名密钥、截图和诊断输出位于忽略的 `artifacts/`；仓库不保存手机序列号或用户应用画面。

## 错误与边界

错误统一含 `code`、`message`、`details`。MCP 操作失败同时设置 `isError`，批处理还返回完成步骤与 `failed_index`。

| 错误 | 后续操作 |
|---|---|
| `device_selection_required` | 指定序列号，或只连接一台已授权设备 |
| `device_unavailable` | 检查数据线、USB 调试和手机授权 |
| `device_busy` | 关闭持有控制权的旧进程 |
| `ambiguous_selector` | 收窄选择器或显式指定 `index` |
| `stale_observation` / `unstable_screen` | 重新观察再决定动作 |
| `action_uncertain` / `verification_failed` | 先观察实际结果，再决定是否重试 |
| `screenshot_unavailable` | 使用控件树或人工处理受保护页面 |
| `input_method_restore_failed` | 先在手机上恢复键盘，再继续 |

依赖固定 `uiautomator2==3.7.0`，使用一个小适配层关闭上游 RPC 自动重发；MCP SDK 限定 1.x，完整版本写入 `uv.lock`。导航键通过 ADB 单次注入，避免厂商 UI Automator 返回键确认差异。所有动作在同一设备内串行执行，超时不自动重复。

目前只验证了一台 Android 15 真机。断线、丢失响应和截图失败通过故障注入验证，未实际拔线或测试所有厂商。自绘/WebView 控件可能没有完整控件树；受 `FLAG_SECURE` 保护的画面可能截图失败或显示黑色区域。解锁、密码、验证码由用户处理。
