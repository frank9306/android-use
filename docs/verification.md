# 验证记录

日期：2026-10-09。测试环境：Windows、Python 3.12.8、USB 真机 NX737J、Android 15 / API 35、屏幕 1216 × 2688。

执行依赖：uiautomator2 3.7.0、MCP Python SDK 1.30.0、adbutils 2.12.0、Pillow 12.3.0、Pydantic 2.14.0。完整解析结果在 `uv.lock`，运行使用 `--frozen`。

## 基础工具验收（插件封装前）

| 检查 | 实际执行结果 |
|---|---|
| `uv run --frozen pytest` | 29 passed，2 个需要显式真机选择的测试 skipped |
| `uv run --frozen pytest --device-serial auto -q` | 31 passed，27.51 秒；包含真实 MCP stdio 流程及辅助输入法恢复 |
| `uv run --frozen ruff check .` | 通过 |
| `uv run --frozen ruff format --check .` | 通过 |
| `uv build --out-dir artifacts/dist` | wheel 与 sdist 构建通过 |
| GitHub CI | Windows、Linux、macOS 均通过冻结依赖安装、29 项离线测试、Ruff 与打包；[运行记录](https://github.com/frank9306/android-use/actions/runs/37885748955) |
| 完整真机验收 | 通过；11 种 MCP 工具共 30 次调用全部符合预期；原输入法及启用状态恢复 |

## 已验证的真实链路

真实 MCP stdio 客户端启动服务器并进行协议初始化，通过 uiautomator2 及 USB 操作独立 fixture App，验证全部 11 个 MCP 工具。实际检查包括：

- 设备发现、手机端服务、原生控件树、MCP JPEG ImageContent 与尺寸映射。
- 应用启动与前台包名；通过资源 ID 定位、中文替换与追加、读回核验。
- 缩放截图坐标点击，并通过 App 状态文字确认点击结果。
- 多个相同文字的控件触发 `ambiguous_selector`；指定 `index` 后操作目标正确。
- 批处理在失败步骤停止，后续按钮未被点击；有限等待出现、消失与超时。
- 指定可滚动区域滑动，实际可见行或位置变化。
- 真实横屏后观察与截图尺寸改变，旧坐标在动作发出前被拒绝。
- 返回主页；临时旋转设置恢复。
- 辅助输入法路径输入中文并读回，原默认输入法与启用列表恢复。

只操作无网络、存储、账户权限的 `com.androiduse.fixture`，未操作生产 App 数据。原始输出与测试签名在忽略的 `artifacts/`，不提交设备序列号或用户画面。

## 契约与故障验证

离线测试通过公开控制器接口覆盖坐标换算、观察失效、重复匹配、连接中断不切换设备、跨控制器独占锁、批处理失败/取消后停止、输入读回、截图失败回退、XML 格式/DTD 拒绝与 CLI 文件保护。

MCP 协议测试使用官方 SDK 的真实内存传输，检查工具 schema、结构化错误和图片返回。SDK 契约测试使用固定版本的真实请求包装层，在 HTTP 边界注入丢失响应与 `false` 点击结果，验证不会重启重发、拒绝点击不会被吞掉。这些故障注入没有模拟真实的物理 USB 断线时序。

## 设置恢复与限制

此前真机复核时 USB 设备消失，导致该次测试及恢复命令中断。2026-10-09 用户重新连接手机，并确认原自动旋转关闭。恢复后重新执行当前版本的全部 31 项测试，结果全部通过。

最终验收后独立读回确认 `user_rotation=0`、`accelerometer_rotation=0`。默认输入法与启用列表的恢复由真机测试断言验证，测试返回主页。任务创建的 `com.androiduse.fixture` 已卸载，ADB 返回 `Success`，随后查询该包不再返回安装路径；恢复记录文件已由测试在成功恢复后删除。测试保留断线时的恢复记录机制。

交付 wheel/sdist 保留在 `artifacts/dist/`。自动审批拒绝删除本地临时 APK、签名、中间构建文件目录 `artifacts/fixture/` 及诊断文件 `artifacts/device-verification.json`，仅返回 `blocked by policy`。因此这些任务产物仍留在忽略目录中，未进入 Git。

只验证上述一台 Android 15 手机。未验证真实 `FLAG_SECURE` 页面、所有厂商权限、自绘/WebView 控件或 scrcpy 预览。受保护截图可能失败或含黑色区域，不能由普通截图接口可靠判定原因。

## 提交审查

审查范围为根提交 `0f40792a462018d84352b448aaf77a7391d494aa`，使用 `git show --format= --root 0f40792a462018d84352b448aaf77a7391d494aa` 与文件级阅读核对实现及 Issue 验收条件。

发现一个 P2：方向滑动忽略 `coordinate_space`，把缩放截图区域当成原生区域。已增加回归测试，先观察测试失败，再限制方向滑动使用原生坐标。修复后全部 31 项测试通过，未发现其他 P0/P1 问题，真机验证已完成。

## Codex 插件封装验收

Codex CLI：`0.162.0-alpha.2`。插件：`android-use@android-use`，版本 `0.1.0`。封装使用受支持的 `.codex-plugin/plugin.json`、`.mcp.json` 和仓库 marketplace，格式依据 [OpenAI 官方插件文档](https://developers.openai.com/plugins/build/plugins)。

| 检查 | 实际执行结果 |
|---|---|
| 两个 Skill 的 `quick_validate.py` | 均通过 |
| 独立目录 MCP 启动测试 | 通过；真实 stdio 初始化、发现全部 11 个工具、查询设备；路径含空格 |
| 原生 Codex 插件安装 | 通过；隔离配置中执行 marketplace add、plugin add、plugin list，确认 enabled |
| 原生 Skill 发现 | 通过；`android-use:android-setup` 与 `android-use:android-control` |
| 原生 MCP 发现 | 通过；Codex app-server 实际启动打包服务并发现全部 11 个工具；安装缓存创建独立 `.venv` |
| 插件封装后的离线测试 | 30 passed，2 个需要显式真机选择的测试 skipped；Ruff 检查及格式检查通过 |
| 已安装插件的完整真机测试 | 30 passed，2 failed；手机锁屏休眠导致 App 未进入前台，等待解锁后复测 |

测试先复现缺失打包启动配置的失败，再增加配置。原生安装验证还发现路径占位启动握手失败，改为让 Codex 将相对 `cwd` 解析到安装目录后，原生 MCP 发现通过。验收脚本 `scripts/check_plugin.py` 使用临时 Codex 配置与干净插件快照，不读取或复制用户凭据、不更改既有客户端配置、不请求模型。协议请求按本机 Codex 导出的 JSON Schema 编写；原生安装与发现结果来自实际客户端，未使用手写插件管理 mock。

此阶段不重复声称已安装插件的手机操作通过。Skill 对话触发与客户端设备准备页面尚未进行模型对话/UI 测试；静态校验及原生发现只证明包可被加载。

插件提交审查使用 `git diff 89b274c..57dd7ed`。发现验收脚本的两项 P2：已安装启动器未接收显式选择的设备，及持续收到通知时请求等待可能超过期限。已分别固定子进程的 `ANDROID_SERIAL` 和检查请求期限；未改变运行时手机控制接口。修正后离线测试 30 项通过，真机复测还需要已连接且解锁的手机。后续 ADB 检查时设备已断开。
