#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Better HSR-Currency Wars - macOS 移植版
支持通过 PlayCover 运行《崩坏：星穹铁道》，使用 Karabiner 虚拟 HID 模拟鼠标点击。
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# 本地模块导入
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from macos_vhid import MacVirtualHIDMouse
from mac_window import MacGameWindow
from mac_capture import MacWindowCapture


def normalize_text(text: str | None) -> str:
    """提取文本中的汉字、字母和数字并转为小写。"""
    if not text:
        return ""
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text).lower()


def similarity_score(s1: str, s2: str) -> int:
    """计算两字符串的编辑距离相似度（百分比 0-100）。"""
    n1, n2 = len(s1), len(s2)
    if n1 == 0 and n2 == 0:
        return 100
    if n1 == 0 or n2 == 0:
        return 0

    dp = [[0] * (n2 + 1) for _ in range(n1 + 1)]
    for i in range(n1 + 1):
        dp[i][0] = i
    for j in range(n2 + 1):
        dp[0][j] = j

    for i in range(1, n1 + 1):
        for j in range(1, n2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)

    dist = dp[n1][n2]
    max_len = max(n1, n2)
    return round((1.0 - dist / max_len) * 100)


def fuzzy_contains(text: str, target: str, min_score: int) -> bool:
    """判断 text 中是否模糊包含 target。"""
    norm_text = normalize_text(text)
    norm_target = normalize_text(target)
    if not norm_text or not norm_target:
        return False
    if norm_target in norm_text:
        return True

    target_len = len(norm_target)
    for i in range(len(norm_text) - target_len + 1):
        window = norm_text[i : i + target_len]
        if similarity_score(norm_target, window) >= min_score:
            return True
    return False


@dataclass
class OcrItem:
    text: str
    confidence: float
    x: float
    y: float
    width: float
    height: float


@dataclass
class FlowStep:
    name: str
    aliases: list[str]
    timeout_seconds: float = 8.0
    search_region: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    fallback_point: tuple[float, float] | None = None
    wait_after_seconds: float = 0.0
    standard_delay_after: float = 0.0


# 局外货币战争流程步骤定义（对应 CurrencyWarsFlow.cs）
CURRENCY_WARS_STEPS = [
    FlowStep(
        name="开始「货币战争」",
        aliases=["开始货币战争", "开始", "货币战争"],
        timeout_seconds=8.0,
        search_region=(0.5, 0.5, 0.5, 0.5),
        fallback_point=(0.82, 0.91),
    ),
    FlowStep(
        name="进入标准博弈",
        aliases=["进入标准博弈", "开始标准博弈", "标准博弈"],
        timeout_seconds=12.0,
        search_region=(0.5, 0.5, 0.5, 0.5),
        fallback_point=(0.82, 0.9),
    ),
    FlowStep(
        name="开始对局",
        aliases=["开始对局", "对局"],
        timeout_seconds=8.0,
        search_region=(0.5, 0.5, 0.5, 0.5),
        fallback_point=(0.82, 0.9),
    ),
    FlowStep(
        name="进入对局",
        aliases=["进入对局", "进入", "对局"],
        timeout_seconds=12.0,
        search_region=(0.5, 0.5, 0.5, 0.5),
        fallback_point=(0.82, 0.9),
        wait_after_seconds=2.0,
    ),
    FlowStep(
        name="下一步（进入词条页）",
        aliases=["下一步"],
        timeout_seconds=15.0,
        search_region=(0.5, 0.5, 0.5, 0.5),
        fallback_point=(0.88, 0.93),
        wait_after_seconds=1.5,
    ),
]


class CurrencyWarsMacController:
    """macOS 自动化主控制器：整合窗口、截屏、OCR与 Karabiner 虚拟 HID 鼠标。"""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or (PROJECT_DIR / "config.clean.json")
        self.config: dict[str, Any] = {}
        self.load_config()

        self.game_win = MacGameWindow(title_keyword=self.config.get("WindowTitle", "崩坏"))
        self.capture = MacWindowCapture(self.game_win)
        self.vhid_mouse: MacVirtualHIDMouse | None = None
        self._ocr = None

    def load_config(self) -> None:
        if self.config_path.is_file():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                print(f"[配置] 成功加载配置文件：{self.config_path}")
            except Exception as e:
                print(f"[配置] 加载配置文件失败 ({e})，使用默认配置。")
                self.config = {}
        else:
            print("[配置] 配置文件不存在，使用内置默认参数。")
            self.config = {}

    def ensure_vhid(self) -> MacVirtualHIDMouse:
        if self.vhid_mouse is None:
            self.vhid_mouse = MacVirtualHIDMouse()
        return self.vhid_mouse

    def get_ocr(self):
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
        return self._ocr

    def send_key_macos(self, key: str) -> None:
        """在 macOS 上发送按键（Esc / V）。"""
        self.game_win.activate()
        time.sleep(0.05)
        # 键码：Esc = 53, V = 9, Return = 36, Option = 58
        key_codes = {
            "esc": 53,
            "escape": 53,
            "v": 9,
            "return": 36,
            "enter": 36,
        }
        code = key_codes.get(key.lower())
        if code is None:
            print(f"[按键] 暂不支持的 macOS 按键：{key}")
            return

        try:
            import Quartz
            event_down = Quartz.CGEventCreateKeyboardEvent(None, code, True)
            event_up = Quartz.CGEventCreateKeyboardEvent(None, code, False)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_down)
            time.sleep(0.05)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_up)
            print(f"[按键] 已发送键盘按键：{key} (keycode {code})")
        except Exception as e:
            print(f"[按键] 发送按键失败: {e}")

    def move_cursor_to(self, screen_x: int, screen_y: int) -> None:
        """移动鼠标指针到绝对屏幕坐标。"""
        try:
            import Quartz
            point = Quartz.CGPoint(screen_x, screen_y)
            Quartz.CGWarpMousePosition(point)
        except Exception:
            try:
                import pyautogui
                pyautogui.moveTo(screen_x, screen_y)
            except Exception as e:
                print(f"[鼠标] 移动指针失败: {e}")

    def click_at(self, screen_x: int, screen_y: int, press_time: float = 0.1, reason: str = "") -> bool:
        """通过 Karabiner 虚拟 HID 执行标准鼠标点击。"""
        self.game_win.activate()
        time.sleep(0.05)

        self.move_cursor_to(screen_x, screen_y)
        mouse = self.ensure_vhid()
        # 必须发送微小位移 (+1,0)/(-1,0) 触发 PlayCover 同步内部坐标
        mouse.nudge_cursor()
        time.sleep(0.05)

        mouse.click(press_time=press_time)
        print(f"[点击] {reason} @ ({screen_x}, {screen_y}) [Karabiner 虚拟 HID]")
        return True

    def click_ratio(self, rx: float, ry: float, press_time: float = 0.1, reason: str = "") -> bool:
        """按照游戏窗口比例坐标点击。"""
        pos = self.game_win.ratio_to_screen(rx, ry)
        if pos is None:
            print(f"[错误] 无法获取游戏窗口屏幕坐标（可能窗口已关闭）: {reason}")
            return False
        return self.click_at(pos[0], pos[1], press_time=press_time, reason=reason)

    def drag(self, start_rx: float, start_ry: float, end_rx: float, end_ry: float, duration: float = 0.5, reason: str = "") -> bool:
        """通过 Karabiner 虚拟 HID 执行拖拽。"""
        start_pos = self.game_win.ratio_to_screen(start_rx, start_ry)
        end_pos = self.game_win.ratio_to_screen(end_rx, end_ry)
        if not start_pos or not end_pos:
            return False

        self.game_win.activate()
        time.sleep(0.05)
        mouse = self.ensure_vhid()

        self.move_cursor_to(start_pos[0], start_pos[1])
        mouse.nudge_cursor()
        time.sleep(0.1)

        mouse.press("left")
        time.sleep(0.15)

        steps = max(5, int(duration / 0.02))
        for i in range(1, steps + 1):
            t = i / steps
            cx = round(start_pos[0] + (end_pos[0] - start_pos[0]) * t)
            cy = round(start_pos[1] + (end_pos[1] - start_pos[1]) * t)
            self.move_cursor_to(cx, cy)
            time.sleep(duration / steps)

        time.sleep(0.1)
        mouse.release("left")
        print(f"[拖拽] {reason} @ {start_pos} -> {end_pos}")
        return True

    def ocr_region(self, region: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)) -> list[OcrItem]:
        """截取指定比例区域并执行 OCR 识别。"""
        img = self.capture.capture_region(*region)
        if img is None:
            return []

        ocr = self.get_ocr()
        # rapidocr_onnxruntime expects BGR or ndarray
        bgr = img[:, :, ::-1].copy()
        result, _ = ocr(bgr)
        items = []
        for row in result or []:
            if len(row) < 3:
                continue
            pts, text, conf = row[0], str(row[1]).strip(), float(row[2])
            if not text:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            min_x, min_y = min(xs), min(ys)
            w = max(0.0, max(xs) - min_x)
            h = max(0.0, max(ys) - min_y)
            items.append(OcrItem(text=text, confidence=conf, x=min_x, y=min_y, width=w, height=h))
        return items

    def find_ocr_click_candidate(
        self,
        aliases: list[str],
        region: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
        min_score: int = 78,
    ) -> tuple[float, float] | None:
        """在指定区域内寻找匹配 alias 的 OCR 文本并返回其中心在游戏窗口内的比例坐标。"""
        items = self.ocr_region(region)
        full_img = self.capture.capture_full()
        if full_img is None:
            return None
        full_h, full_w = full_img.shape[:2]

        rx, ry, rw, rh = region
        region_x_px = full_w * rx
        region_y_px = full_h * ry

        for alias in aliases:
            for item in items:
                if fuzzy_contains(item.text, alias, min_score):
                    center_x_in_region = item.x + item.width / 2.0
                    center_y_in_region = item.y + item.height / 2.0
                    center_x_full = region_x_px + center_x_in_region
                    center_y_full = region_y_px + center_y_in_region
                    return (center_x_full / full_w, center_y_full / full_h)
        return None

    def run_outgame_round(self) -> bool:
        """执行单轮局外开局刷新。返回 True 表示达成词条目标停止，False 表示未达成需继续重试。"""
        print("\n--- [局外流程] 开始新一轮刷开局 ---")

        for step in CURRENCY_WARS_STEPS:
            print(f"[流程] 寻找步骤：{step.name} ...")
            start_time = time.time()
            found = False
            while time.time() - start_time < step.timeout_seconds:
                candidate = self.find_ocr_click_candidate(
                    step.aliases,
                    region=step.search_region,
                    min_score=self.config.get("ButtonFuzzyScore", 78),
                )
                if candidate:
                    self.click_ratio(candidate[0], candidate[1], reason=f"命中 {step.name}")
                    found = True
                    break
                time.sleep(0.4)

            if not found:
                if step.fallback_point:
                    print(f"[流程] OCR 超时，尝试使用兜底坐标点击：{step.name}")
                    self.click_ratio(step.fallback_point[0], step.fallback_point[1], reason=f"兜底 {step.name}")
                else:
                    print(f"[流程] 未能完成步骤：{step.name}")
                    return False

            if step.wait_after_seconds > 0:
                time.sleep(step.wait_after_seconds)

        # 检查词条页
        debuff_delay = self.config.get("DebuffCheckDelaySeconds", 3.0)
        time.sleep(debuff_delay)

        ocr_items = self.ocr_region((0.0, 0.0, 1.0, 1.0))
        page_text = " ".join(item.text for item in ocr_items)
        print(f"[词条页识别结果]：{page_text}")

        # 词条判定
        target_words = self.config.get("TargetWords", ["忍无可忍"])
        blocked_words = self.config.get("BlockedWords", ["能量逃逸"])
        fuzzy_score = self.config.get("FuzzyScore", 85)
        blocked_fuzzy_score = self.config.get("BlockedFuzzyScore", 85)

        # 检查是否命中不想要的词条
        blocked_hit = []
        for word in blocked_words:
            if fuzzy_contains(page_text, word, blocked_fuzzy_score):
                blocked_hit.append(word)

        if blocked_hit:
            print(f"[判定] ❌ 命中不想要词条：{', '.join(blocked_hit)}，放弃并结算！")
            self.abandon_and_settle()
            return False

        # 检查是否命中目标词条
        target_hit = []
        target_missing = []
        for word in target_words:
            if fuzzy_contains(page_text, word, fuzzy_score):
                target_hit.append(word)
            else:
                target_missing.append(word)

        match_any = self.config.get("DebuffMatchAny", True)
        success = (len(target_hit) > 0) if match_any else (len(target_missing) == 0)

        if success:
            print(f"[判定] 🎉 恭喜！达成目标词条：{', '.join(target_hit)}！自动化停止。")
            return True
        else:
            print(f"[判定] ⚠️ 未达成目标词条（缺少：{', '.join(target_missing)}），放弃并重新开始。")
            self.abandon_and_settle()
            return False

    def abandon_and_settle(self) -> None:
        """放弃当前局并结算返回大厅。"""
        print("[结算] 发送 Esc 打开退出菜单...")
        self.send_key_macos("Esc")
        time.sleep(0.8)

        # 寻找“放弃并结算”或兜底点击 (0.39, 0.69)
        settle_cand = self.find_ocr_click_candidate(["放弃并结算", "放弃", "结算"], region=(0.2, 0.4, 0.6, 0.4))
        if settle_cand:
            self.click_ratio(settle_cand[0], settle_cand[1], reason="点击放弃并结算")
        else:
            self.click_ratio(0.39, 0.69, reason="兜底点击放弃并结算")

        time.sleep(1.0)
        # 点击确认结算
        confirm_cand = self.find_ocr_click_candidate(["确认", "确定"], region=(0.4, 0.5, 0.4, 0.3))
        if confirm_cand:
            self.click_ratio(confirm_cand[0], confirm_cand[1], reason="确认放弃")
        else:
            self.click_ratio(0.61, 0.62, reason="兜底确认放弃")

        time.sleep(2.0)
        # 连点屏幕空白处跳过结算动画
        for _ in range(5):
            self.click_ratio(0.5, 0.85, reason="跳过结算动画")
            time.sleep(0.3)
        time.sleep(1.5)

    def close(self) -> None:
        if self.vhid_mouse is not None:
            self.vhid_mouse.close()
            self.vhid_mouse = None


def run_interactive_menu():
    print("=" * 60)
    print("  Better HSR - Currency Wars (macOS + Karabiner 虚拟 HID)")
    print("=" * 60)

    controller = CurrencyWarsMacController()

    if not controller.game_win.find_window():
        print("⚠️ 未发现游戏窗口。请确认 PlayCover 已启动《崩坏：星穹铁道》！")
    else:
        rect = controller.game_win.get_game_rect()
        print(f"✅ 成功找到游戏窗口！桌面区域：{rect.x},{rect.y} {rect.width}x{rect.height}")

    while True:
        print("\n请选择操作：")
        print("1. 运行局外刷词条流程 (Out-game Flow)")
        print("2. 测试 Karabiner 虚拟 HID 鼠标点击")
        print("3. 重新查找游戏窗口并截屏诊断")
        print("4. 识别当前画面全屏 OCR 文字")
        print("0. 退出程序")

        choice = input("\n请输入选项 [0-4]: ").strip()
        if choice == "1":
            rounds = 0
            try:
                while True:
                    rounds += 1
                    print(f"\n===== 开始第 {rounds} 轮刷开局 =====")
                    success = controller.run_outgame_round()
                    if success:
                        print(f"✅ 目标达成，自动化流程结束（共运行 {rounds} 轮）。")
                        break
                    time.sleep(1.0)
            except KeyboardInterrupt:
                print("\n用户手动中止了自动流程。")
        elif choice == "2":
            print("\n正在测试 Karabiner 虚拟 HID 鼠标...")
            try:
                mouse = controller.ensure_vhid()
                print("虚拟 HID 鼠标初始化成功！准备在游戏窗口中心发送一次微移与点击...")
                rect = controller.game_win.get_game_rect()
                if rect:
                    cx = rect.x + rect.width // 2
                    cy = rect.y + rect.height // 2
                    controller.click_at(cx, cy, reason="测试窗口中心点击")
                else:
                    mouse.nudge_cursor()
                    mouse.click(0.1)
                    print("测试点击已发送（无游戏窗口坐标，在当前指针位置）。")
            except Exception as e:
                print(f"❌ 虚拟 HID 鼠标测试失败: {e}")
        elif choice == "3":
            controller.game_win.refresh()
            rect = controller.game_win.get_game_rect()
            if rect:
                print(f"✅ 游戏窗口有效: {rect}")
                img = controller.capture.capture_full()
                if img is not None:
                    print(f"✅ 成功截取游戏画面，尺寸: {img.shape[1]}x{img.shape[0]}")
                else:
                    print("❌ 截屏失败，请检查屏幕录制权限！")
            else:
                print("❌ 未能获取游戏窗口位置。")
        elif choice == "4":
            print("正在截屏并执行 OCR ...")
            items = controller.ocr_region((0.0, 0.0, 1.0, 1.0))
            print(f"识别到 {len(items)} 个文本项：")
            for it in items:
                print(f"  - [{it.confidence:.2f}] {it.text} @ ({it.x:.0f}, {it.y:.0f})")
        elif choice == "0":
            print("退出程序。")
            controller.close()
            break
        else:
            print("无效选项，请重新输入。")


if __name__ == "__main__":
    try:
        run_interactive_menu()
    except KeyboardInterrupt:
        print("\n程序已退出。")
