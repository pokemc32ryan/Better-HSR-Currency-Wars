from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import numpy as np
    from PIL import Image
except ImportError:
    np = None
    Image = None

try:
    import Quartz
except ImportError:
    Quartz = None

if TYPE_CHECKING:
    from tools.macos.mac_window import MacGameWindow


class MacWindowCapture:
    """按窗口 ID 截取 PlayCover 游戏画面，转换为 sRGB 并自动裁剪标题栏。"""

    def __init__(self, game_win: MacGameWindow) -> None:
        self.game_win = game_win

    def capture_full(self) -> np.ndarray | None:
        """截取完整游戏客户区（裁除标题栏，转换至 sRGB）。返回 numpy RGB 图像 (H, W, 3)。"""
        if Quartz is None or np is None:
            return None

        window_id = self.game_win.window_id
        if window_id is None:
            return None

        image_ref = Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull,
            Quartz.kCGWindowListOptionIncludingWindow,
            window_id,
            Quartz.kCGWindowImageBoundsIgnoreFraming,
        )
        if image_ref is None:
            return None

        width = int(Quartz.CGImageGetWidth(image_ref))
        height = int(Quartz.CGImageGetHeight(image_ref))
        if width <= 0 or height <= 0:
            return None

        game_height = min(
            height,
            round(width * self.game_win.standard_height / self.game_win.standard_width),
        )
        title_height = max(0, height - game_height)
        if title_height > 0:
            cropped_ref = Quartz.CGImageCreateWithImageInRect(
                image_ref,
                Quartz.CGRectMake(0, title_height, width, game_height),
            )
            if cropped_ref is not None:
                image_ref = cropped_ref
                height = game_height

        srgb_space = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)
        buffer = bytearray(height * width * 4)
        context = Quartz.CGBitmapContextCreate(
            buffer,
            width,
            height,
            8,
            width * 4,
            srgb_space,
            Quartz.kCGImageAlphaPremultipliedLast | Quartz.kCGBitmapByteOrder32Big,
        )
        if context is None:
            return None

        Quartz.CGContextDrawImage(
            context,
            Quartz.CGRectMake(0, 0, width, height),
            image_ref,
        )

        screenshot = np.frombuffer(buffer, dtype=np.uint8).reshape(
            (height, width, 4)
        )[:, :, :3].copy()
        return screenshot

    def capture_region(
        self, rx: float, ry: float, rw: float, rh: float
    ) -> np.ndarray | None:
        """根据比例区域 (rx, ry, rw, rh) 截取游戏局部画面。"""
        full_img = self.capture_full()
        if full_img is None:
            return None

        img_h, img_w = full_img.shape[:2]
        x1 = max(0, min(img_w - 1, round(img_w * rx)))
        y1 = max(0, min(img_h - 1, round(img_h * ry)))
        x2 = max(x1 + 1, min(img_w, round(img_w * (rx + rw))))
        y2 = max(y1 + 1, min(img_h, round(img_h * (ry + rh))))

        return full_img[y1:y2, x1:x2].copy()
