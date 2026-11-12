#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
USER_HOME="${HOME:?无法确定当前用户的 HOME}"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "此启动脚本仅支持 macOS。"
    read -r -p "按 Enter 键关闭此窗口..."
    exit 1
fi

if [[ "$(id -u)" -eq 0 ]]; then
    echo "请以当前 macOS 登录用户启动，不要使用 sudo。"
    read -r -p "按 Enter 键关闭此窗口..."
    exit 1
fi

echo "=========================================================="
echo " Better HSR - Currency Wars (macOS + Karabiner 虚拟 HID)"
echo "=========================================================="

# 1. 确保构建虚拟 HID 客户端
if [[ ! -x "$PROJECT_DIR/.install/macos-vhid/vhid-click-client" ]]; then
    echo "正在构建 Karabiner 虚拟 HID 点击客户端..."
    if ! "$PROJECT_DIR/Tools/macos/build_vhid_click_client.sh"; then
        echo "虚拟 HID 点击客户端构建失败。"
        read -r -p "按 Enter 键关闭此窗口..." || true
        exit 1
    fi
fi

# 2. 检查 Karabiner-DriverKit-VirtualHIDDevice 驱动与守护进程
echo "需要管理员授权启动 Karabiner 虚拟 HID 客户端；主程序仍以当前登录用户运行。"
if ! sudo -v; then
    echo "未获得虚拟 HID 客户端所需的管理员授权，已取消启动。"
    read -r -p "按 Enter 键关闭此窗口..." || true
    exit 1
fi

VHID_DAEMON_STARTED=0
VHID_DAEMON="/Library/Application Support/org.pqrs/Karabiner-DriverKit-VirtualHIDDevice/Applications/Karabiner-VirtualHIDDevice-Daemon.app/Contents/MacOS/Karabiner-VirtualHIDDevice-Daemon"
if ! pgrep -f "Karabiner-VirtualHIDDevice-Daemon" >/dev/null 2>&1; then
    if [[ -x "$VHID_DAEMON" ]]; then
        echo "Karabiner 虚拟 HID 守护进程未运行，正在后台启动..."
        sudo "$VHID_DAEMON" >/tmp/hsr_vhid_daemon.log 2>&1 &
        VHID_DAEMON_STARTED=1
        for _ in $(seq 1 30); do
            if pgrep -f "Karabiner-VirtualHIDDevice-Daemon" >/dev/null 2>&1; then
                break
            fi
            sleep 0.5
        done
    else
        echo "提示：未在标准路径找到 Karabiner-VirtualHIDDevice-Daemon。"
        echo "若虚拟鼠标无法响应，请确保已安装 Karabiner-DriverKit-VirtualHIDDevice v8.7.0 并启用扩展。"
    fi
fi

cleanup_vhid_daemon() {
    if [[ "$VHID_DAEMON_STARTED" -eq 1 ]]; then
        sudo -n pkill -f "Karabiner-VirtualHIDDevice-Daemon" >/dev/null 2>&1 || true
    fi
}
trap cleanup_vhid_daemon EXIT

# 3. 寻找 Python 环境
PYTHON_BIN=""
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
elif command -v uv >/dev/null 2>&1; then
    if [[ ! -d "$PROJECT_DIR/.venv" ]]; then
        echo "正在通过 uv 创建虚拟环境并安装依赖..."
        uv venv "$PROJECT_DIR/.venv"
        uv pip install --python "$PROJECT_DIR/.venv/bin/python" \
            "rapidocr_onnxruntime>=1.3.8" \
            "numpy" \
            "pillow" \
            "pyobjc-framework-Quartz" \
            "pyobjc-framework-Cocoa" \
            "pyautogui"
    fi
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
    echo "错误：未找到 Python3 或 uv，请先安装 Python 3.10+ 或 uv。"
    read -r -p "按 Enter 键关闭此窗口..."
    exit 1
fi

echo "使用 Python: $PYTHON_BIN"
cd "$PROJECT_DIR"

# 4. 运行主程序（默认启动原生 GUI 介面）
if [[ "${1:-}" == "--cli" ]]; then
    echo "正在启动控制台交互模式..."
    "$PYTHON_BIN" "$PROJECT_DIR/Tools/macos/currency_wars_mac.py"
else
    echo "正在启动 macOS 原生图形介面 (GUI)..."
    "$PYTHON_BIN" "$PROJECT_DIR/Tools/macos/gui_app.py"
fi
EXIT_CODE=$?

read -r -p "按 Enter 键关闭此窗口..." || true
exit "$EXIT_CODE"
