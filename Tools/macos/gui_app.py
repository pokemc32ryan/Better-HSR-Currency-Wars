#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Better HSR - Currency Wars macOS 原生圖形介面 (GUI)
支援透過 Karabiner 虛擬 HID 驅動進行前台真實點擊與全自動刷開局。
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from currency_wars_mac import CurrencyWarsMacController
from mac_window import MacGameWindow


class HsrCurrencyWarsMacGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Better HSR - Currency Wars (macOS + Karabiner 虛擬 HID)")
        self.root.geometry("960x720")
        self.root.minsize(850, 600)

        # 控制器與狀態
        self.controller = CurrencyWarsMacController()
        self.is_running = False
        self.worker_thread: threading.Thread | None = None

        # 主體樣式
        self._setup_styles()
        self._build_ui()

        # 初始檢測視窗
        self.root.after(500, self.refresh_window_status)

    def _setup_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("aqua")
        except Exception:
            pass

    def _build_ui(self) -> None:
        # 主容器
        main_frame = ttk.Frame(self.root, padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. 頂部視窗狀態欄
        top_frame = ttk.LabelFrame(main_frame, text="遊戲視窗狀態 (PlayCover)", padding="10")
        top_frame.pack(fill=tk.X, pady=(0, 10))

        self.win_status_var = tk.StringVar(value="🔍 正在搜尋遊戲視窗...")
        self.status_label = ttk.Label(top_frame, textvariable=self.win_status_var, font=("", 13, "bold"))
        self.status_label.pack(side=tk.LEFT, padx=5)

        ttk.Button(top_frame, text="🔄 重新搜尋視窗", command=self.refresh_window_status).pack(side=tk.RIGHT, padx=5)

        # 視窗自選下拉清單
        self.win_dropdown_var = tk.StringVar()
        self.win_combobox = ttk.Combobox(top_frame, textvariable=self.win_dropdown_var, state="readonly", width=35)
        self.win_combobox.pack(side=tk.RIGHT, padx=5)
        self.win_combobox.bind("<<ComboboxSelected>>", self._on_window_selected)

        # 2. 中間左右分欄 (左邊配置與控制，右邊日誌)
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 左側控制台
        left_panel = ttk.Frame(paned, padding="5")
        paned.add(left_panel, weight=1)

        # 控制按鈕區
        action_frame = ttk.LabelFrame(left_panel, text="自動化執行", padding="10")
        action_frame.pack(fill=tk.X, pady=(0, 10))

        self.btn_start_outgame = tk.Button(
            action_frame,
            text="🚀 開始「局外刷開局」",
            bg="#5FAFE6",
            fg="black",
            font=("", 13, "bold"),
            command=self.start_outgame_flow,
            height=2,
        )
        self.btn_start_outgame.pack(fill=tk.X, pady=4)

        self.btn_stop = tk.Button(
            action_frame,
            text="⏹️ 停止自動化",
            bg="#FFBABA",
            fg="black",
            font=("", 12, "bold"),
            state=tk.DISABLED,
            command=self.stop_flow,
            height=1,
        )
        self.btn_stop.pack(fill=tk.X, pady=4)

        btn_grid = ttk.Frame(action_frame)
        btn_grid.pack(fill=tk.X, pady=4)

        ttk.Button(btn_grid, text="🎯 測試虛擬 HID 點擊", command=self.test_vhid_click).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(btn_grid, text="📸 截圖與 OCR 診斷", command=self.test_screenshot_ocr).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=2)

        # 策略設定區
        cfg_frame = ttk.LabelFrame(left_panel, text="詞條與策略設定 (config.clean.json)", padding="10")
        cfg_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(cfg_frame, text="主詞條目標 (用逗號隔開)：").pack(anchor=tk.W)
        self.target_words_entry = ttk.Entry(cfg_frame)
        self.target_words_entry.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(cfg_frame, text="不想要詞條 (命中即放棄結算)：").pack(anchor=tk.W)
        self.blocked_words_entry = ttk.Entry(cfg_frame)
        self.blocked_words_entry.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(cfg_frame, text="投資目標 (用逗號隔開)：").pack(anchor=tk.W)
        self.investment_entry = ttk.Entry(cfg_frame)
        self.investment_entry.pack(fill=tk.X, pady=(0, 8))

        self.match_any_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(cfg_frame, text="主詞條命中任意一個即可 (DebuffMatchAny)", variable=self.match_any_var).pack(anchor=tk.W, pady=4)

        row_settings = ttk.Frame(cfg_frame)
        row_settings.pack(fill=tk.X, pady=4)
        ttk.Label(row_settings, text="詞條頁等待秒數：").pack(side=tk.LEFT)
        self.debuff_delay_spin = ttk.Spinbox(row_settings, from_=1.0, to=10.0, increment=0.5, width=6)
        self.debuff_delay_spin.pack(side=tk.LEFT, padx=5)

        ttk.Button(cfg_frame, text="💾 保存設定到 config.clean.json", command=self.save_config).pack(fill=tk.X, pady=8)

        # 右側日誌區
        right_panel = ttk.LabelFrame(paned, text="即時執行日誌", padding="10")
        paned.add(right_panel, weight=2)

        self.log_text = scrolledtext.ScrolledText(right_panel, wrap=tk.WORD, font=("Menlo", 11))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        log_actions = ttk.Frame(right_panel)
        log_actions.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(log_actions, text="🧹 清空日誌", command=self.clear_log).pack(side=tk.RIGHT)

        # 填入配置內容
        self._load_config_to_ui()

    def _load_config_to_ui(self) -> None:
        cfg = self.controller.config
        tw = cfg.get("TargetWords", ["忍无可忍", "第一位面强化", "第二位面强化", "第三位面强化"])
        self.target_words_entry.delete(0, tk.END)
        self.target_words_entry.insert(0, ", ".join(tw))

        bw = cfg.get("BlockedWords", ["能量逃逸"])
        self.blocked_words_entry.delete(0, tk.END)
        self.blocked_words_entry.insert(0, ", ".join(bw))

        inv = cfg.get("InvestmentTargets", ["彩虹时代"])
        self.investment_entry.delete(0, tk.END)
        self.investment_entry.insert(0, ", ".join(inv))

        self.match_any_var.set(cfg.get("DebuffMatchAny", True))
        self.debuff_delay_spin.set(cfg.get("DebuffCheckDelaySeconds", 3.0))

    def save_config(self) -> None:
        tw = [x.strip() for x in self.target_words_entry.get().split(",") if x.strip()]
        bw = [x.strip() for x in self.blocked_words_entry.get().split(",") if x.strip()]
        inv = [x.strip() for x in self.investment_entry.get().split(",") if x.strip()]

        self.controller.config["TargetWords"] = tw
        self.controller.config["BlockedWords"] = bw
        self.controller.config["InvestmentTargets"] = inv
        self.controller.config["DebuffMatchAny"] = self.match_any_var.get()
        try:
            self.controller.config["DebuffCheckDelaySeconds"] = float(self.debuff_delay_spin.get())
        except Exception:
            pass

        try:
            with open(self.controller.config_path, "w", encoding="utf-8") as f:
                json.dump(self.controller.config, f, ensure_ascii=False, indent=2)
            self.log("✅ 設定已成功儲存至 config.clean.json！")
            messagebox.showinfo("成功", "設定已保存！")
        except Exception as e:
            self.log(f"❌ 儲存設定失敗: {e}")
            messagebox.showerror("錯誤", f"儲存失敗: {e}")

    def refresh_window_status(self) -> None:
        self.controller.game_win.refresh()
        all_wins = MacGameWindow.list_all_windows()

        combobox_items = []
        selected_index = -1
        for i, w in enumerate(all_wins):
            title = w["title"] or w["owner"]
            item_str = f"[{w['window_id']}] {title} ({w['width']}x{w['height']})"
            combobox_items.append(item_str)
            if self.controller.game_win.window_id == w["window_id"]:
                selected_index = i

        self.win_combobox["values"] = combobox_items

        if self.controller.game_win.find_window():
            rect = self.controller.game_win.get_game_rect()
            title = self.controller.game_win.title
            status_text = f"🟢 遊戲視窗：{title} ({rect.width}x{rect.height})"
            self.win_status_var.set(status_text)
            self.status_label.configure(foreground="#15803D")
            self.log(f"✅ 成功找到遊戲視窗：{title}，解析度={rect.width}x{rect.height}，座標=({rect.x}, {rect.y})")
            if selected_index >= 0:
                self.win_combobox.current(selected_index)
        else:
            self.win_status_var.set("🔴 未發現遊戲視窗（請在右側下拉選單手動選擇）")
            self.status_label.configure(foreground="#B91C1C")
            self.log("⚠️ 未自動匹配到遊戲視窗。可從下拉選單選擇或確認 PlayCover 是否在前台執行。")

    def _on_window_selected(self, _event=None) -> None:
        sel = self.win_dropdown_var.get()
        if not sel or "[" not in sel or "]" not in sel:
            return
        wid_str = sel.split("[")[1].split("]")[0]
        try:
            wid = int(wid_str)
            self.controller.game_win._window_id = wid
            rect = self.controller.game_win.get_game_rect()
            if rect:
                self.win_status_var.set(f"🟢 手動選定視窗：ID {wid} ({rect.width}x{rect.height})")
                self.status_label.configure(foreground="#15803D")
                self.log(f"✅ 已手動選定視窗 ID {wid}，區域={rect.width}x{rect.height}")
        except Exception as e:
            self.log(f"❌ 選擇視窗失敗: {e}")

    def log(self, message: str) -> None:
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {message}\n"
        self.root.after(0, self._append_log_text, entry)

    def _append_log_text(self, text: str) -> None:
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)

    def clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)

    def test_vhid_click(self) -> None:
        threading.Thread(target=self._test_vhid_worker, daemon=True).start()

    def _test_vhid_worker(self) -> None:
        self.log("🎯 正在測試 Karabiner 虛擬 HID 點擊...")
        try:
            mouse = self.controller.ensure_vhid()
            rect = self.controller.game_win.get_game_rect()
            if rect:
                cx = rect.x + rect.width // 2
                cy = rect.y + rect.height // 2
                self.controller.click_at(cx, cy, reason="測試窗口中心點擊")
                self.log(f"✅ 成功透過 Karabiner 虛擬 HID 在視窗中心 ({cx}, {cy}) 發送微移與點擊！")
            else:
                mouse.nudge_cursor()
                mouse.click(0.1)
                self.log("✅ 成功在目前游標位置發送虛擬 HID 點擊！")
        except Exception as e:
            self.log(f"❌ 虛擬 HID 點擊測試失敗: {e}")

    def test_screenshot_ocr(self) -> None:
        threading.Thread(target=self._test_ocr_worker, daemon=True).start()

    def _test_ocr_worker(self) -> None:
        self.log("📸 正在擷取遊戲畫面並進行 OCR 辨識...")
        try:
            img = self.controller.capture.capture_full()
            if img is None:
                self.log("❌ 截圖失敗！請檢查系統設定「隱私權與安全性 ➔ 螢幕錄製」是否已授予終端或 Python 權限。")
                return

            self.log(f"✅ 截圖成功，尺寸: {img.shape[1]}x{img.shape[0]} (標準 sRGB)")
            items = self.controller.ocr_region((0.0, 0.0, 1.0, 1.0))
            self.log(f"📝 全畫面 OCR 辨識到 {len(items)} 個文本項目：")
            for it in items[:15]:
                self.log(f"   - [{it.confidence:.2f}] {it.text} @ ({it.x:.0f}, {it.y:.0f})")
            if len(items) > 15:
                self.log(f"   ...以及其他 {len(items) - 15} 個文本項目。")
        except Exception as e:
            self.log(f"❌ 診斷失敗: {e}")

    def start_outgame_flow(self) -> None:
        if self.is_running:
            return
        if not self.controller.game_win.find_window():
            messagebox.showwarning("警告", "尚未找到《崩壞：星穹鐵道》遊戲視窗！請先確認遊戲已啟動。")
            return

        self.is_running = True
        self.btn_start_outgame.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self.log("🚀 開始執行「局外刷開局」自動化流程...")

        self.worker_thread = threading.Thread(target=self._outgame_worker, daemon=True)
        self.worker_thread.start()

    def _outgame_worker(self) -> None:
        rounds = 0
        try:
            while self.is_running:
                rounds += 1
                self.log(f"\n===== [自動流程] 第 {rounds} 輪開始 =====")
                success = self.controller.run_outgame_round()
                if success:
                    self.log(f"🎉 達成目標詞條！自動化順利完成（共執行 {rounds} 輪）。")
                    break
                time.sleep(1.2)
        except Exception as e:
            self.log(f"❌ 自動流程中斷出錯: {e}")
        finally:
            self.is_running = False
            self.root.after(0, self._on_flow_stopped)

    def stop_flow(self) -> None:
        if not self.is_running:
            return
        self.is_running = False
        self.log("⏹️ 收到停止指令，正在停止自動化流程...")

    def _on_flow_stopped(self) -> None:
        self.btn_start_outgame.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)
        self.log("自動化流程已停止。")


def main() -> None:
    root = tk.Tk()
    _app = HsrCurrencyWarsMacGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
