"""
NCT Bus Departures plugin for ChuckBuilds LEDMatrix.
Tuned for 128x32 displays.

Data source: the public NCT stop page configured by stop_id.
The parser deliberately has several fallbacks because Passenger/NCT may
change HTML classes while leaving the human-readable departure text intact.
"""

from __future__ import annotations

import re
import urllib.request
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

from src.plugin_system.base_plugin import BasePlugin


BASE_URL = "https://www.nctx.co.uk/stops/{}"
BG = (0, 0, 0)
WHITE = (255, 255, 255)
NCT_GREEN = (0, 220, 120)
LIVE = (0, 255, 0)
SCHEDULED = (255, 180, 0)
DIM = (150, 150, 150)
ERROR = (255, 70, 70)


class NCTBusDeparturesPlugin(BasePlugin):
    def __init__(self, plugin_id, config, display_manager, cache_manager, plugin_manager):
        super().__init__(plugin_id, config, display_manager, cache_manager, plugin_manager)
        self.departures: List[Dict[str, str]] = []
        self.error: Optional[str] = None
        self.last_updated = ""
        self._load_config()

    def _load_config(self):
        self.stop_id = str(self.config.get("stop_id", "YOUR_STOP_ID")).strip()
        self.stop_name = str(self.config.get("stop_name", "Bus Stop")).strip()
        self.route_filter = str(self.config.get("route_filter", "")).strip()
        self.max_departures = max(1, min(3, int(self.config.get("max_departures", 3))))

    def on_config_change(self, new_config):
        super().on_config_change(new_config)
        self._load_config()

    def get_update_interval(self):
        return max(15, int(self.config.get("update_interval", 30)))

    def update(self):
        self._load_config()
        cache_key = f"{self.plugin_id}_{self.stop_id}_{self.route_filter}"
        interval = self.get_update_interval()

        try:
            cached = self.cache_manager.get(cache_key, max_age=interval)
        except Exception:
            cached = None

        if cached:
            self.departures = cached.get("departures", [])
            self.last_updated = cached.get("last_updated", "")
            self.error = None
            return

        try:
            html = self._fetch_page()
            departures, last_updated = self._parse_page(html)
            self.departures = departures[: self.max_departures]
            self.last_updated = last_updated
            self.error = None
            try:
                self.cache_manager.set(cache_key, {
                    "departures": self.departures,
                    "last_updated": self.last_updated,
                })
            except Exception:
                pass
        except Exception as exc:
            self.logger.error("NCT departure fetch failed: %s", exc, exc_info=True)
            self.error = str(exc)[:80]
            # Keep the previous successful departures on screen if we have them.

    def _fetch_page(self) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,32}", self.stop_id):
            raise ValueError("Invalid stop_id")

        req = urllib.request.Request(
            BASE_URL.format(self.stop_id),
            headers={
                "User-Agent": "Mozilla/5.0 LEDMatrix-NCT-Bus/1.0",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode("utf-8", errors="replace")

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    def _parse_page(self, html: str):
        soup = BeautifulSoup(html, "html.parser")
        page_text = self._clean(soup.get_text(" ", strip=True))

        updated = ""
        m = re.search(r"Last updated:\s*([0-2]?\d:[0-5]\d)", page_text, re.I)
        if m:
            updated = m.group(1)

        if "There are no departures available" in page_text:
            return [], updated

        results: List[Dict[str, str]] = []
        seen = set()

        # First choice: inspect repeated blocks that contain the words Live/Scheduled
        # plus a countdown or clock time. This avoids depending on site CSS names.
        candidates = soup.find_all(["li", "article", "tr", "div"])
        for node in candidates:
            text = self._clean(node.get_text(" ", strip=True))
            if len(text) < 4 or len(text) > 220:
                continue
            dep = self._departure_from_text(text)
            if dep:
                key = (dep["route"], dep["destination"], dep["time"])
                if key not in seen:
                    seen.add(key)
                    results.append(dep)

        # Fallback: parse the flattened text around route/countdown patterns.
        if not results:
            results = self._parse_flat_text(page_text)

        if self.route_filter:
            results = [d for d in results if d["route"].lower() == self.route_filter.lower()]

        return results[: self.max_departures], updated

    def _departure_from_text(self, text: str) -> Optional[Dict[str, str]]:
        # Time may be "Due", "11 mins", "11 min", or HH:MM.
        tm = re.search(r"\b(Due|\d{1,3}\s*(?:mins?|minutes?)|\d{1,2}:\d{2})\b", text, re.I)
        if not tm:
            return None

        # Require a live/scheduled marker where available to reduce false matches.
        status_m = re.search(r"\b(Live|Scheduled)\b", text, re.I)
        status = status_m.group(1).title() if status_m else (
            "Live" if re.search(r"\b(?:Due|\d{1,3}\s*(?:mins?|minutes?))\b", tm.group(1), re.I)
            else "Scheduled"
        )

        before = text[:tm.start()].strip(" -–|")
        # Remove common labels.
        before = re.sub(r"\b(?:Live|Scheduled|Next bus|Departure|Departs?)\b", " ", before, flags=re.I)
        before = self._clean(before)

        # Route is normally a short token such as 36 / 36U.
        route_m = re.search(r"(?:^|\s)([A-Za-z]?\d{1,3}[A-Za-z]?)(?:\s|$)", before)
        if not route_m:
            return None
        route = route_m.group(1)

        destination = before[route_m.end():].strip(" -–|")
        if not destination:
            destination = "Destination"

        raw_time = tm.group(1)
        if raw_time.lower() == "due":
            time_text = "DUE"
        elif ":" in raw_time:
            time_text = raw_time
        else:
            n = re.search(r"\d{1,3}", raw_time)
            time_text = f"{n.group(0)}m" if n else raw_time

        return {
            "route": route,
            "destination": destination,
            "time": time_text,
            "status": status,
        }

    def _parse_flat_text(self, text: str) -> List[Dict[str, str]]:
        results = []
        # Conservative fallback aimed at NCT's human-readable departure board.
        pat = re.compile(
            r"\b([A-Za-z]?\d{1,3}[A-Za-z]?)\s+"
            r"(.{1,55}?)\s+"
            r"(Due|\d{1,3}\s*(?:mins?|minutes?)|\d{1,2}:\d{2})"
            r"(?:\s+(Live|Scheduled))?",
            re.I,
        )
        for m in pat.finditer(text):
            route, dest, raw_time, status = m.groups()
            if raw_time.lower() == "due":
                shown = "DUE"
            elif ":" in raw_time:
                shown = raw_time
            else:
                shown = re.search(r"\d+", raw_time).group(0) + "m"
            results.append({
                "route": route,
                "destination": self._clean(dest),
                "time": shown,
                "status": (status or ("Scheduled" if ":" in raw_time else "Live")).title(),
            })
        return results

    @staticmethod
    def _font(size=10, bold=False):
        # PIL's built-in bitmap font is safe in emulator and on the Pi.
        # LEDMatrix scales no fonts here: pixels remain crisp.
        try:
            return ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
                if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                size,
            )
        except Exception:
            return ImageFont.load_default()

    @staticmethod
    def _fit(draw, text, font, max_width):
        text = str(text)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return text
        ell = ".."
        while text and draw.textbbox((0, 0), text + ell, font=font)[2] > max_width:
            text = text[:-1]
        return text + ell

    def display(self, force_clear=False):
        width = self.display_manager.width
        height = self.display_manager.height

        img = Image.new("RGB", (width, height), BG)
        draw = ImageDraw.Draw(img)

        # Tuned for 128x32, but clips gracefully on other widths.
        header_font = self._font(9, True)
        body_font = self._font(9, True)
        small_font = self._font(7, False)

        header = self.stop_name or self.stop_id
        header = self._fit(draw, header, header_font, max(20, width - 46))
        draw.text((1, -1), header, font=header_font, fill=WHITE)

        if self.last_updated:
            upd = self.last_updated
            uw = draw.textbbox((0, 0), upd, font=small_font)[2]
            draw.text((width - uw - 1, 0), upd, font=small_font, fill=DIM)

        draw.line((0, 10, width - 1, 10), fill=NCT_GREEN)

        if not self.departures:
            msg = "NO BUSES" if not self.error else "DATA ERROR"
            colour = SCHEDULED if not self.error else ERROR
            draw.text((2, 15), msg, font=body_font, fill=colour)
        else:
            # Three compact rows fit at y=11,18,25 on a 32px panel.
            row_y = 11
            row_h = 7
            for dep in self.departures[: self.max_departures]:
                route = dep["route"][:4]
                time_text = dep["time"][:6]
                status = dep.get("status", "Scheduled")
                colour = LIVE if status.lower() == "live" else SCHEDULED

                draw.text((1, row_y - 1), route, font=small_font, fill=NCT_GREEN)

                time_w = draw.textbbox((0, 0), time_text, font=body_font)[2]
                time_x = width - time_w - 1
                draw.text((time_x, row_y - 2), time_text, font=body_font, fill=colour)

                dest_x = 24
                dest_max = max(1, time_x - dest_x - 3)
                dest = self._fit(draw, dep["destination"], small_font, dest_max)
                draw.text((dest_x, row_y - 1), dest, font=small_font, fill=WHITE)
                row_y += row_h

        self.display_manager.image = img
        self.display_manager.update_display()
        return True
