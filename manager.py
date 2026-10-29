"""
NCT Bus Departures plugin for ChuckBuilds LEDMatrix.
Adaptive for 128x32 and wider 32px-high displays.
"""
from __future__ import annotations
import re
import urllib.request
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from src.plugin_system.base_plugin import BasePlugin

BASE_URL = "https://www.nctx.co.uk/stops/{}"
BG=(0,0,0); WHITE=(255,255,255); ORANGE=(255,140,0); LIVE=(0,255,0); SCHEDULED=(255,180,0); DIM=(210,210,210); ERROR=(255,70,70)

class NCTBusDeparturesPlugin(BasePlugin):
    def __init__(self, plugin_id, config, display_manager, cache_manager, plugin_manager):
        super().__init__(plugin_id, config, display_manager, cache_manager, plugin_manager)
        self.departures=[]; self.error=None; self.last_updated=""; self._load_config()
    def _load_config(self):
        self.stop_id=str(self.config.get("stop_id","YOUR_STOP_ID")).strip()
        self.stop_name=str(self.config.get("stop_name","Field Lane, Burton Drive (opp)")).strip()
        self.route_filter=str(self.config.get("route_filter","36")).strip()
        self.max_departures=max(1,min(2,int(self.config.get("max_departures",2))))
    def on_config_change(self,new_config):
        super().on_config_change(new_config); self._load_config()
    def get_update_interval(self): return max(15,int(self.config.get("update_interval",30)))
    def update(self):
        self._load_config(); key=f"{self.plugin_id}_{self.stop_id}_{self.route_filter}"; interval=self.get_update_interval()
        try: cached=self.cache_manager.get(key,max_age=interval)
        except Exception: cached=None
        if cached:
            self.departures=cached.get("departures",[]); self.last_updated=cached.get("last_updated",""); self.error=None; return
        try:
            deps,updated=self._parse_page(self._fetch_page()); self.departures=deps[:self.max_departures]; self.last_updated=updated; self.error=None
            try: self.cache_manager.set(key,{"departures":self.departures,"last_updated":self.last_updated})
            except Exception: pass
        except Exception as exc:
            self.logger.error("NCT departure fetch failed: %s",exc,exc_info=True); self.error=str(exc)[:80]
    def _fetch_page(self):
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,32}",self.stop_id): raise ValueError("Invalid stop_id")
        req=urllib.request.Request(BASE_URL.format(self.stop_id),headers={"User-Agent":"Mozilla/5.0 LEDMatrix-NCT-Bus/1.4","Accept":"text/html,application/xhtml+xml"})
        with urllib.request.urlopen(req,timeout=10) as r: return r.read().decode("utf-8",errors="replace")
    @staticmethod
    def _clean(text): return re.sub(r"\s+"," ",text or "").strip()
    def _parse_page(self,html):
        soup=BeautifulSoup(html,"html.parser"); page=self._clean(soup.get_text(" ",strip=True)); updated=""
        m=re.search(r"Last updated:\s*([0-2]?\d:[0-5]\d)",page,re.I)
        if m: updated=m.group(1)
        if "There are no departures available" in page: return [],updated
        results=[]; seen=set()
        for node in soup.find_all(["li","article","tr","div"]):
            text=self._clean(node.get_text(" ",strip=True))
            if 4<=len(text)<=220:
                dep=self._departure_from_text(text)
                if dep:
                    k=(dep["route"],dep["destination"],dep["time"])
                    if k not in seen: seen.add(k); results.append(dep)
        if not results: results=self._parse_flat_text(page)
        if self.route_filter: results=[d for d in results if d["route"].lower()==self.route_filter.lower()]
        return results[:self.max_departures],updated
    def _departure_from_text(self,text):
        tm=re.search(r"\b(Due|\d{1,3}\s*(?:mins?|minutes?)|\d{1,2}:\d{2})\b",text,re.I)
        if not tm: return None
        sm=re.search(r"\b(Live|Scheduled)\b",text,re.I)
        status=sm.group(1).title() if sm else ("Live" if re.search(r"\b(?:Due|\d{1,3}\s*(?:mins?|minutes?))\b",tm.group(1),re.I) else "Scheduled")
        before=re.sub(r"\b(?:Live|Scheduled|Next bus|Departure|Departs?)\b"," ",text[:tm.start()].strip(" -–|"),flags=re.I); before=self._clean(before)
        rm=re.search(r"(?:^|\s)([A-Za-z]?\d{1,3}[A-Za-z]?)(?:\s|$)",before)
        if not rm: return None
        route=rm.group(1); dest=before[rm.end():].strip(" -–|") or "Destination"; raw=tm.group(1)
        shown="DUE" if raw.lower()=="due" else raw if ":" in raw else (re.search(r"\d{1,3}",raw).group(0) if re.search(r"\d{1,3}",raw) else raw)
        return {"route":route,"destination":dest,"time":shown,"status":status,"is_minutes": bool(re.search(r"\d{1,3}\s*(?:mins?|minutes?)",raw,re.I))}
    def _parse_flat_text(self,text):
        out=[]; pat=re.compile(r"\b([A-Za-z]?\d{1,3}[A-Za-z]?)\s+(.{1,55}?)\s+(Due|\d{1,3}\s*(?:mins?|minutes?)|\d{1,2}:\d{2})(?:\s+(Live|Scheduled))?",re.I)
        for m in pat.finditer(text):
            route,dest,raw,status=m.groups(); is_minutes=bool(re.search(r"\d{1,3}\s*(?:mins?|minutes?)",raw,re.I)); shown="DUE" if raw.lower()=="due" else raw if ":" in raw else re.search(r"\d+",raw).group(0)
            out.append({"route":route,"destination":self._clean(dest),"time":shown,"status":(status or ("Scheduled" if ":" in raw else "Live")).title(),"is_minutes":is_minutes})
        return out
    @staticmethod
    def _fit(draw,text,font,max_width):
        text=str(text)
        if draw.textbbox((0,0),text,font=font)[2]<=max_width:return text
        while text and draw.textbbox((0,0),text+"..",font=font)[2]>max_width:text=text[:-1]
        return text+".."
    @staticmethod
    def _display_font():
        # Keep Pillow's built-in default typography, but request it one touch
        # smaller where supported by the installed Pillow version.
        try:
            return ImageFont.load_default(size=9)
        except TypeError:
            return ImageFont.load_default()
    def display(self,force_clear=False):
        font=self._display_font()
        # Use the active LEDMatrix dimensions rather than hard-coding 128px.
        # This keeps the same layout on 128x32 and automatically uses the extra
        # horizontal space if the panel is later extended to 256x32.
        width=max(1,int(self.display_manager.width))
        height=max(1,int(self.display_manager.height))
        image=Image.new("RGB",(width,height),BG)
        draw=ImageDraw.Draw(image)
        right=width-1

        clock=self.last_updated or "--:--"
        clock_w=draw.textbbox((0,0),clock,font=font)[2]
        clock_x=max(1,right-clock_w)
        header=self._fit(draw,self.stop_name or self.stop_id,font,max(20,clock_x-3))
        draw.text((1,-1),header,font=font,fill=WHITE)
        draw.text((clock_x,-1),clock,font=font,fill=WHITE)
        # Leave a clean pixel gap below the smaller header text.
        divider_y=min(10,height-1)
        draw.line((0,divider_y,right,divider_y),fill=ORANGE)

        if not self.departures:
            draw.text((2,min(14,height-1)),"NO BUSES" if not self.error else "DATA ERROR",font=font,fill=SCHEDULED if not self.error else ERROR)
        else:
            for i,dep in enumerate(self.departures[:2]):
                y=12+i*10
                if y>=height: break
                route=dep["route"][:4]
                t=dep["time"][:6]
                status=dep.get("status","Scheduled")
                time_colour=LIVE if status.lower()=="live" else SCHEDULED
                draw.text((1,y),route,font=font,fill=ORANGE)
                shown_time=(t+" min") if dep.get("is_minutes") else t
                tw=draw.textbbox((0,0),shown_time,font=font)[2]
                tx=max(1,right-tw)
                draw.text((tx,y),shown_time,font=font,fill=time_colour)
                dx=25
                dest=self._fit(draw,dep["destination"],font,max(1,tx-dx-2))
                draw.text((dx,y),dest,font=font,fill=WHITE)

        self.display_manager.image=image
        self.display_manager.update_display()
        return True
