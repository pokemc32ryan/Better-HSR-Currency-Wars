# Better HSR-Currency Wars V12.8

用于《崩坏：星穹铁道》“货币战争”玩法的 OCR 自动化辅助工具。

## 普通用户

请前往 GitHub Releases 下载完整的 V1XX 自包含发行包。发行包包含 OCR 运行环境，不要求系统预装 .NET Desktop Runtime。

## 源码

- 主项目：`Better HSR-Currency Wars V11.csproj`
- 局外流程：`HsrCurrencyWarsCleanWpf/Core/CurrencyWarsFlow.cs`
- 局内流程：`HsrCurrencyWarsCleanWpf/Core/InGameOpeningFlow.cs`
- 局外+局内组合规则：`HsrCurrencyWarsCleanWpf/Core/CombinedFlowRules.cs`
- 主界面与自动化编排：`HsrCurrencyWarsCleanWpf/MainWindow.cs`
- OCR 桥接源码：`Tools/rapidocr_bridge.py`
- OCR 运行时构建说明：`Tools/OCRBuild/README.md`

本机配置文件 `config.clean.json`、编译输出和 OCR 可执行文件不会提交到源码仓库。

[已有 Mirror酱CDK?前往 Mirror酱 高速下载](https://mirrorchyan.com/zh/projects?rid=Better-HSR-Currency-Wars)

## macOS 支持 (Apple Silicon + PlayCover)

项目现已支持在 macOS 上通过 PlayCover 运行《崩坏：星穹铁道》并执行自动化：
- 鼠标点击与拖拽：采用 **Karabiner 虚拟 HID 驱动（Karabiner-DriverKit-VirtualHIDDevice）** 模拟真实硬件级输入，支持微移同步 PlayCover 内部游标，避免合成事件失效。
- 画面捕获：通过 macOS 原生 Quartz / CoreGraphics 截取 PlayCover 游戏窗口，自动裁切标题栏并校准至标准 sRGB 色彩空间。
- OCR 与流程：复用 RapidOCR 与项目的货币战争开局策略逻辑，读取 `config.clean.json` 中的词条目标与黑名单。

### macOS 运行前准备

1. **安装 PlayCover**：在 Mac 上通过 PlayCover 启动《崩坏：星穹铁道》。
2. **安装 Karabiner 驱动**：安装并批准 [Karabiner-DriverKit-VirtualHIDDevice v8.7.0](https://github.com/pqrs-org/Karabiner-DriverKit-VirtualHIDDevice/releases/tag/v8.7.0)。
3. **命令行开发工具**：若未安装 Xcode Command Line Tools，请在终端执行 `xcode-select --install`。
4. **授予权限**：首次运行请根据系统提示为终端（Terminal / iTerm）授予「辅助功能」与「屏幕录制」权限。

### macOS 启动方式

双击仓库根目录的 `启动_mac.command`，或在终端执行：
```bash
./启动_mac.command
```
脚本将自动构建虚拟 HID 点击客户端、校验 Karabiner 守护进程、安装 Python 依赖并启动交互式自动化控制终端。

## 说明

当前 Windows 原版使用 C#、WPF 和 .NET 10，目标平台为 `win-x64`。恢复及构建信息见 `RECOVERY.md`。macOS 平台提供 Karabiner 虚拟 HID 服务与原生控制器支持。

本项目仅供学习和交流使用。

