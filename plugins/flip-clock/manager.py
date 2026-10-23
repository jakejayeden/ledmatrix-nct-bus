"""Animated flip-clock plugin for ChuckBuilds LEDMatrix.

Designed for 128x32 displays, while still reading the active display size
dynamically so it degrades sensibly on nearby panel sizes.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from src.plugin_system.base_plugin import BasePlugin


BG = (0, 0, 0)
WHITE = (255, 255, 255)
DIM = (120, 120, 120)
MID = (180, 180, 180)
SEPARATOR = (65, 65, 65)


class FlipClockPlugin(BasePlugin):
    """Minimal animated flip clock with a date rail."""

    def __init__(self, plugin_id, config, display_manager, cache_manager, plugin_manager):
        super().__init__(plugin_id, config, display_manager, cache_manager, plugin_manager)
        self._last_dt: Optional[datetime] = None
        self._last_minute_key: Optional[str] = None
        self._load_config()

    def _load_config(self):
        self.use_24_hour = bool(self.config.get("use_24_hour", True))
        self.show_weekday = bool(self.config.get("show_weekday", True))
        self.animation_ms = max(120, min(900, int(self.config.get("animation_ms", 420))))
        self.animation_frames = max(3, min(10, int(self.config.get("animation_frames", 7))))
        self.date_uppercase = bool(self.config.get("date_uppercase", True))

    def on_config_change(self, new_config):
        super().on_config_change(new_config)
        self._load_config()

    def get_update_interval(self):
        return 1

    def update(self):
        return None

    @staticmethod
    def _font(size: int, bold: bool = False):
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    def _time_text(self, dt: datetime) -> str:
        if self.use_24_hour:
            return dt.strftime("%H:%M")
        text = dt.strftime("%I:%M")
        return text[1:] if text.startswith("0") else text

    def _date_lines(self, dt: datetime):
        weekday = dt.strftime("%a")
        day_month = dt.strftime("%d %b")
        year = dt.strftime("%Y")
        if self.date_uppercase:
            weekday = weekday.upper()
            day_month = day_month.upper()
        return weekday, day_month, year

    @staticmethod
    def _center_text(draw, box, text, font, fill):
        left, top, right, bottom = box
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = left + max(0, (right - left - tw) // 2)
        y = top + max(0, (bottom - top - th) // 2) - bbox[1]
        draw.text((x, y), text, font=font, fill=fill)

    def _layout(self):
        width = int(getattr(self.display_manager, "width", 128))
        height = int(getattr(self.display_manager, "height", 32))
        date_width = 46 if width >= 120 else max(36, width // 3)
        gutter = 3
        divider_x = max(1, width - date_width - gutter)
        time_box = (0, 0, divider_x - 1, height)
        date_box = (divider_x + gutter, 0, width, height)
        return width, height, divider_x, time_box, date_box

    def _time_font(self, draw, time_box, sample="88:88"):
        left, top, right, bottom = time_box
        max_w = max(1, right - left - 2)
        max_h = max(1, bottom - top - 2)
        for size in range(max_h, 8, -1):
            font = self._font(size, bold=True)
            bbox = draw.textbbox((0, 0), sample, font=font)
            if bbox[2] - bbox[0] <= max_w and bbox[3] - bbox[1] <= max_h:
                return font
        return self._font(9, bold=True)

    def _draw_date(self, draw, date_box, dt):
        left, top, right, bottom = date_box
        height = bottom - top
        weekday, day_month, year = self._date_lines(dt)
        small = self._font(7, bold=False)
        strong = self._font(8, bold=True)
        year_font = self._font(7, bold=False)

        if self.show_weekday:
            rows = [
                (top - 1, top + height // 3, weekday, small, MID),
                (top + height // 3 - 1, top + (2 * height) // 3 + 1, day_month, strong, WHITE),
                (top + (2 * height) // 3, bottom, year, year_font, DIM),
            ]
        else:
            rows = [
                (top + 3, top + height // 2 + 2, day_month, strong, WHITE),
                (top + height // 2, bottom - 1, year, year_font, DIM),
            ]

        for row_top, row_bottom, text, font, fill in rows:
            self._center_text(draw, (left, row_top, right, row_bottom), text, font, fill)

    def _render_static(self, dt: datetime) -> Image.Image:
        width, height, divider_x, time_box, date_box = self._layout()
        image = Image.new("RGB", (width, height), BG)
        draw = ImageDraw.Draw(image)
        font = self._time_font(draw, time_box)
        self._center_text(draw, time_box, self._time_text(dt), font, WHITE)
        draw.line((divider_x + 1, 3, divider_x + 1, height - 4), fill=SEPARATOR)
        self._draw_date(draw, date_box, dt)
        return image

    def _render_flip_frame(self, old_dt: datetime, new_dt: datetime, progress: float) -> Image.Image:
        """Render a two-phase split-flap animation for only changed characters."""
        width, height, divider_x, time_box, date_box = self._layout()
        image = Image.new("RGB", (width, height), BG)
        draw = ImageDraw.Draw(image)
        font = self._time_font(draw, time_box)

        old_text = self._time_text(old_dt)
        new_text = self._time_text(new_dt)
        sample_bbox = draw.textbbox((0, 0), "88:88", font=font)
        text_w = sample_bbox[2] - sample_bbox[0]
        left, top, right, bottom = time_box
        origin_x = left + max(0, (right - left - text_w) // 2)
        origin_y = top + max(0, (bottom - top - (sample_bbox[3] - sample_bbox[1])) // 2) - sample_bbox[1]

        char_positions = []
        cursor = origin_x
        for ch in "88:88":
            cb = draw.textbbox((0, 0), ch, font=font)
            cw = cb[2] - cb[0]
            char_positions.append((cursor, cw))
            cursor += cw

        if len(new_text) < 5:
            old_text = old_text.rjust(5)
            new_text = new_text.rjust(5)

        mid_y = height // 2

        for idx, (x, cw) in enumerate(char_positions[:5]):
            old_ch = old_text[idx] if idx < len(old_text) else " "
            new_ch = new_text[idx] if idx < len(new_text) else " "
            changed = old_ch != new_ch

            if not changed or new_ch == ":":
                draw.text((x, origin_y), new_ch, font=font, fill=WHITE)
                continue

            glyph_w = max(cw + 2, 4)
            glyph_h = height
            old_glyph = Image.new("RGB", (glyph_w, glyph_h), BG)
            new_glyph = Image.new("RGB", (glyph_w, glyph_h), BG)
            ImageDraw.Draw(old_glyph).text((1, origin_y), old_ch, font=font, fill=WHITE)
            ImageDraw.Draw(new_glyph).text((1, origin_y), new_ch, font=font, fill=WHITE)

            if progress < 0.5:
                phase = progress / 0.5
                image.paste(old_glyph.crop((0, mid_y, glyph_w, glyph_h)), (x - 1, mid_y))
                upper = old_glyph.crop((0, 0, glyph_w, mid_y))
                scaled_h = max(1, int(mid_y * (1.0 - phase)))
                upper = upper.resize((glyph_w, scaled_h))
                image.paste(upper, (x - 1, mid_y - scaled_h))
            else:
                phase = (progress - 0.5) / 0.5
                image.paste(new_glyph.crop((0, 0, glyph_w, mid_y)), (x - 1, 0))
                lower = new_glyph.crop((0, mid_y, glyph_w, glyph_h))
                scaled_h = max(1, int((glyph_h - mid_y) * phase))
                lower = lower.resize((glyph_w, scaled_h))
                image.paste(lower, (x - 1, mid_y))

            draw.line((x, mid_y, x + cw - 1, mid_y), fill=SEPARATOR)

        draw.line((divider_x + 1, 3, divider_x + 1, height - 4), fill=SEPARATOR)
        self._draw_date(draw, date_box, new_dt)
        return image

    def _push(self, image: Image.Image):
        self.display_manager.image = image
        self.display_manager.update_display()

    def _animate_flip(self, old_dt: datetime, new_dt: datetime):
        frame_delay = (self.animation_ms / 1000.0) / self.animation_frames
        for frame in range(1, self.animation_frames + 1):
            progress = frame / self.animation_frames
            self._push(self._render_flip_frame(old_dt, new_dt, progress))
            if frame < self.animation_frames:
                time.sleep(frame_delay)

    def display(self, force_clear=False):
        now = datetime.now()
        minute_key = now.strftime("%Y%m%d%H%M")

        if force_clear:
            try:
                self.display_manager.clear()
            except Exception:
                pass

        if (
            self._last_dt is not None
            and self._last_minute_key is not None
            and minute_key != self._last_minute_key
        ):
            self._animate_flip(self._last_dt, now)
        else:
            self._push(self._render_static(now))

        self._last_dt = now
        self._last_minute_key = minute_key
        return True
