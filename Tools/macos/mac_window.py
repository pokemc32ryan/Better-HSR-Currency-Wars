from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

try:
    import Quartz
    from AppKit import (
        NSApplicationActivateIgnoringOtherApps,
        NSRunningApplication,
        NSWorkspace,
    )
except ImportError:
    Quartz = None
    NSWorkspace = None
    NSRunningApplication = None
    NSApplicationActivateIgnoringOtherApps = None


@dataclass
class WindowRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


def _normalize_str(text: str) -> str:
    """簡繁通用與小寫標準化。"""
    s = text.lower()
    # 簡繁互換替換
    s = s.replace("崩壞", "崩坏").replace("鐵道", "铁道")
    s = s.replace("：", ":").replace(" ", "")
    return s


class MacGameWindow:
    """定位与控制 macOS 上 PlayCover 中的《崩坏：星穹铁道》游戏窗口。"""

    COMMON_TARGETS = [
        "崩坏:星穹铁道",
        "崩坏",
        "星穹铁道",
        "honkai:starrail",
        "starrail",
        "playcover",
        "hkrpg",
    ]

    def __init__(
        self,
        title_keyword: str = "崩坏",
        standard_width: int = 1920,
        standard_height: int = 1080,
    ) -> None:
        self.title_keyword: str = title_keyword
        self.standard_width: int = standard_width
        self.standard_height: int = standard_height
        self._window_id: int | None = None
        self._owner_pid: int | None = None
        self._title: str = ""

    @staticmethod
    def is_available() -> bool:
        return Quartz is not None

    @staticmethod
    def list_all_windows() -> list[dict[str, Any]]:
        """列出目前桌面上所有可見視窗的 ID、PID、標題與擁有者名稱。"""
        if Quartz is None:
            return []
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        ) or []

        res = []
        for win in windows:
            pid = win.get(Quartz.kCGWindowOwnerPID)
            wid = win.get(Quartz.kCGWindowNumber)
            title = str(win.get(Quartz.kCGWindowName, "") or "").strip()
            owner = str(win.get(Quartz.kCGWindowOwnerName, "") or "").strip()
            bounds = win.get(Quartz.kCGWindowBounds, {})
            w = int(bounds.get("Width", 0))
            h = int(bounds.get("Height", 0))
            if wid and pid and (w > 100 and h > 100):
                res.append({
                    "window_id": int(wid),
                    "pid": int(pid),
                    "title": title,
                    "owner": owner,
                    "width": w,
                    "height": h,
                })
        return res

    def refresh(self) -> bool:
        self._window_id = None
        self._owner_pid = None
        self._title = ""
        return self.find_window()

    def find_window(self) -> bool:
        if Quartz is None:
            return False

        current_pid = os.getpid()
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        ) or []

        user_keyword_norm = _normalize_str(self.title_keyword.strip()) if self.title_keyword else ""

        best_window = None
        for win in windows:
            owner_pid = win.get(Quartz.kCGWindowOwnerPID)
            window_id = win.get(Quartz.kCGWindowNumber)
            if owner_pid is None or window_id is None:
                continue
            if int(owner_pid) == current_pid:
                continue
            if int(win.get(Quartz.kCGWindowLayer, 0)) != 0:
                continue

            title = str(win.get(Quartz.kCGWindowName, "") or "").strip()
            owner_name = str(win.get(Quartz.kCGWindowOwnerName, "") or "").strip()

            norm_title = _normalize_str(title)
            norm_owner = _normalize_str(owner_name)

            matched = False
            # 1. 優先匹配使用者設定的關鍵字
            if user_keyword_norm:
                if user_keyword_norm in norm_title or user_keyword_norm in norm_owner:
                    matched = True

            # 2. 同時匹配內建的星鐵與 PlayCover 關鍵字（簡繁通配）
            if not matched:
                for target in self.COMMON_TARGETS:
                    if target in norm_title or target in norm_owner:
                        matched = True
                        break

            if matched:
                bounds = win.get(Quartz.kCGWindowBounds, {})
                w = int(bounds.get("Width", 0))
                h = int(bounds.get("Height", 0))
                # 排除過小非遊戲畫面視窗
                if w >= 400 and h >= 300:
                    display_title = title if title else owner_name
                    best_window = (int(window_id), int(owner_pid), display_title)
                    break

        if best_window:
            self._window_id, self._owner_pid, self._title = best_window
            return True

        return False

    @property
    def window_id(self) -> int | None:
        if self._window_id is None:
            self.find_window()
        return self._window_id

    @property
    def title(self) -> str:
        return self._title

    @property
    def is_active(self) -> bool:
        if self._owner_pid is None or NSWorkspace is None:
            return False
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front is not None and front.processIdentifier() == self._owner_pid:
            return True
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(self._owner_pid)
        return app is not None and bool(app.isActive())

    def activate(self) -> bool:
        if self._owner_pid is None:
            if not self.find_window():
                return False
        if self.is_active:
            return True
        if NSRunningApplication is None or self._owner_pid is None:
            return False
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(self._owner_pid)
        if app is None:
            return False
        return bool(app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps))

    def get_game_rect(self) -> WindowRect | None:
        """获取游戏内容区域在桌面的绝对坐标（已裁掉 macOS 窗口标题栏）。"""
        win_id = self.window_id
        if win_id is None or Quartz is None:
            return None

        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        ) or []

        for win in windows:
            if int(win.get(Quartz.kCGWindowNumber, -1)) != win_id:
                continue
            bounds = win.get(Quartz.kCGWindowBounds, {})
            x = int(bounds.get("X", 0))
            y = int(bounds.get("Y", 0))
            width = int(bounds.get("Width", 0))
            height = int(bounds.get("Height", 0))
            if width <= 0 or height <= 0:
                return None

            game_height = min(
                height,
                round(width * self.standard_height / self.standard_width),
            )
            title_bar_height = max(0, height - game_height)
            return WindowRect(
                x=x,
                y=y + title_bar_height,
                width=width,
                height=game_height,
            )

        return None

    def ratio_to_screen(self, rx: float, ry: float) -> tuple[int, int] | None:
        rect = self.get_game_rect()
        if rect is None:
            return None
        sx = rect.x + round(rect.width * rx)
        sy = rect.y + round(rect.height * ry)
        return (sx, sy)

    def game_to_screen(self, gx: float, gy: float) -> tuple[int, int] | None:
        return self.ratio_to_screen(gx / self.standard_width, gy / self.standard_height)
