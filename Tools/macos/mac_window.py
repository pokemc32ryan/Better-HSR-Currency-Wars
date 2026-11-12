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


class MacGameWindow:
    """定位与控制 macOS 上 PlayCover 中的《崩坏：星穹铁道》游戏窗口。"""

    GAME_TITLE_ALIASES: dict[str, set[str]] = {
        '崩坏': {'崩坏：星穹铁道', '崩坏:星穹铁道', '星穹铁道', 'Honkai: Star Rail', 'StarRail', 'PlayCover'},
        '崩坏：星穹铁道': {'崩坏：星穹铁道', '崩坏:星穹铁道', '星穹铁道', 'Honkai: Star Rail', 'StarRail'},
        'Honkai: Star Rail': {'崩坏：星穹铁道', '崩坏:星穹铁道', '星穹铁道', 'Honkai: Star Rail', 'StarRail'},
    }

    def __init__(
        self,
        title_keyword: str = '崩坏',
        standard_width: int = 1920,
        standard_height: int = 1080,
    ) -> None:
        self.title_keyword: str = title_keyword
        self.standard_width: int = standard_width
        self.standard_height: int = standard_height
        self._window_id: int | None = None
        self._owner_pid: int | None = None
        self._title: str = ''

    @staticmethod
    def is_available() -> bool:
        return Quartz is not None

    def refresh(self) -> bool:
        self._window_id = None
        self._owner_pid = None
        self._title = ''
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

        aliases = self.GAME_TITLE_ALIASES.get(self.title_keyword, {self.title_keyword})

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

            title = str(win.get(Quartz.kCGWindowName, '') or '').strip()
            owner_name = str(win.get(Quartz.kCGWindowOwnerName, '') or '').strip()

            matched = False
            for alias in aliases:
                if alias.lower() in title.lower() or alias.lower() in owner_name.lower():
                    matched = True
                    break

            if matched:
                bounds = win.get(Quartz.kCGWindowBounds, {})
                w = int(bounds.get('Width', 0))
                h = int(bounds.get('Height', 0))
                if w >= 400 and h >= 300:
                    best_window = (int(window_id), int(owner_pid), title or owner_name)
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
            x = int(bounds.get('X', 0))
            y = int(bounds.get('Y', 0))
            width = int(bounds.get('Width', 0))
            height = int(bounds.get('Height', 0))
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
