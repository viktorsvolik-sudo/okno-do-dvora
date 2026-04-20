#!/usr/bin/env python3
"""
Okno do dvora — Pygame weather visualization
Raspberry Pi 4B · Debian · Fullscreen
"""

import pygame
import requests
import math
import random
import time
import threading
from datetime import datetime

# ─────────────────────────────────────────────
# KONFIGURACE
# ─────────────────────────────────────────────
LAT         = 50.1071
LON         = 14.4473
SUNRISE     = 6
SUNSET      = 20
TWILIGHT    = 2
UPDATE_SEC  = 60        # jak často fetchovat data (sekundy)
FPS         = 30
NUM_DROPS   = 400
NUM_CLOUDS  = 7
NUM_FOG     = 50
NUM_STARS   = 90

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def clamp(v, a, b):
    return max(a, min(b, v))

def lerp(a, b, t):
    return a + (b - a) * t

def lerp_color(c1, c2, t):
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))

def get_daylight(hour):
    ss = SUNRISE - TWILIGHT
    se = SUNRISE + TWILIGHT
    ds = SUNSET  - TWILIGHT
    de = SUNSET  + TWILIGHT
    if hour < ss or hour >= de:
        return 0.0
    if se <= hour < ds:
        return 1.0
    if hour < se:
        return clamp((hour - ss) / (se - ss), 0, 1)
    return clamp(1 - (hour - ds) / (de - ds), 0, 1)

def get_bg_color(temp, cloud):
    if   temp >= 30: base = (250, 153,  35)
    elif temp >= 20: base = (255, 210, 120)
    elif temp >= 10: base = (180, 210, 255)
    elif temp >   0: base = (160, 190, 255)
    else:            base = (200, 220, 255)
    m = (cloud / 100) * 0.6
    return tuple(int(base[i] + (255 - base[i]) * m) for i in range(3))

def apply_light(rgb, dl):
    f = lerp(0.10, 1.0, dl)
    return tuple(int(c * f) for c in rgb)

def guess_name(temp, rain, cloud):
    if temp <= 0 and rain > 0:   return "SNÍH"
    if rain > 3  and cloud > 90: return "BOUŘE"
    if rain > 0.1:               return "DÉŠŤ"
    if cloud >= 95:              return "MLHA"
    if cloud >  70:              return "OBLAČNO"
    if cloud >  30:              return "POLOJASNO"
    if temp  >= 30:              return "VEDRO"
    return "JASNO"

def is_snow(w):
    return w.get("temp", 10) <= 0 or w.get("name", "") == "SNÍH"

def is_fog(w):
    return w.get("cloud", 0) >= 95 or w.get("name", "") == "MLHA"

# ─────────────────────────────────────────────
# FETCH POČASÍ (vlákno na pozadí)
# ─────────────────────────────────────────────
class WeatherFetcher:
    def __init__(self):
        self.data = None
        self.error = False
        self.last_fetch = 0
        self._lock = threading.Lock()
        self._fetch()                   # první fetch hned

    def _fetch(self):
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={LAT}&longitude={LON}"
                f"&current=temperature_2m,precipitation,cloudcover"
                f",wind_speed_10m,wind_direction_10m"
            )
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            c = r.json()["current"]

            wind_sign = math.sin(math.radians(c["wind_direction_10m"]))
            now = datetime.now()
            hour = now.hour + now.minute / 60

            temp  = c["temperature_2m"]
            rain  = c["precipitation"]
            cloud = c["cloudcover"]

            with self._lock:
                self.data = {
                    "name":      guess_name(temp, rain, cloud),
                    "temp":      temp,
                    "rain":      rain,
                    "cloud":     cloud,
                    "wind":      wind_sign,
                    "wind_kmh":  c["wind_speed_10m"],
                    "hour":      hour,
                }
                self.error = False
                self.last_fetch = time.time()

        except Exception as e:
            print(f"[weather] fetch error: {e}")
            with self._lock:
                self.error = True

        # naplánuj další fetch
        t = threading.Timer(UPDATE_SEC, self._fetch)
        t.daemon = True
        t.start()

    def get(self):
        with self._lock:
            return self.data

# ─────────────────────────────────────────────
# PARTICLE SYSTEMS
# ─────────────────────────────────────────────
class Drop:
    def __init__(self, W, H, snow=False):
        self.W, self.H = W, H
        self.snow = snow
        self.reset(initial=True)

    def reset(self, initial=False):
        self.x = random.uniform(-120, self.W + 120)
        if initial:
            self.y = random.uniform(-self.H, self.H)
        else:
            self.y = random.uniform(-120, -2)

        if self.snow:
            self.length = 0
            self.speed  = random.uniform(0.5, 1.7)
            self.radius = random.uniform(1.2, 3.4)
            self.drift  = random.uniform(0.2, 0.8)
        else:
            self.length = random.uniform(20, 60)
            self.speed  = random.uniform(4, 12)
            self.radius = 0
            self.drift  = 0

    def update(self, wind):
        if self.snow:
            self.y += self.speed
            self.x += wind * self.drift
        else:
            self.y += self.speed
            self.x += wind * 2

        pad = 140
        if self.y > self.H + pad or self.x < -pad * 2 or self.x > self.W + pad * 2:
            self.reset()

    def draw(self, surf, wind, rain_intensity):
        if self.snow:
            alpha = 220
            color = (235, 240, 245, alpha)
            r = int(self.radius)
            s = pygame.Surface((r*2+1, r*2+1), pygame.SRCALPHA)
            pygame.draw.circle(s, color, (r, r), r)
            surf.blit(s, (int(self.x) - r, int(self.y) - r))
        else:
            angle = wind * 8
            ex = int(self.x + angle)
            ey = int(self.y + self.length)
            alpha = 220 if rain_intensity > 2 else 180
            color = (180, 200, 220, alpha) if rain_intensity > 2 else (120, 140, 160, alpha)
            s = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            pygame.draw.line(s, color, (int(self.x), int(self.y)), (ex, ey), 1)
            surf.blit(s, (0, 0))


class CloudBand:
    def __init__(self, W, H, index=0):
        self.W, self.H = W, H
        self.layer = index % 3
        self.reset_pos(random_x=True)
        self.speed  = random.uniform(0.03, 0.09)
        self.wobble = random.uniform(0, math.pi * 2)
        self.drift_y = random.uniform(-0.015, 0.015)

    def reset_pos(self, random_x=False):
        self.w = random.uniform(900, 1400)
        self.h = random.uniform(140, 260)
        base_y = self.H * (0.08 + self.layer * 0.14) + random.uniform(0, self.H * 0.08)
        self.y = base_y
        if random_x:
            self.x = random.uniform(-300, self.W + 300)
        else:
            self.x = -self.w - random.uniform(0, 260)

    def update(self, wind, t):
        wp = wind * 0.12
        self.x += self.speed + wp * (1 + self.layer * 0.18)
        self.y += self.drift_y + math.sin(t * 0.08 + self.wobble) * 0.015

        if self.x - self.w > self.W + 300:
            self.x = -self.w - random.uniform(0, 260)
            self.y = self.H * (0.08 + self.layer * 0.14) + random.uniform(0, self.H * 0.08)
        if self.x + self.w < -320:
            self.x = self.W + self.w + random.uniform(0, 260)
            self.y = self.H * (0.08 + self.layer * 0.14) + random.uniform(0, self.H * 0.08)

    def draw(self, surf, density, storm, daylight, t):
        if density <= 0.02:
            return

        pulse = 0.95 + math.sin(t * (0.06 + self.layer * 0.015) + self.wobble) * 0.04
        ba    = density * 0.1
        alpha = int(ba * (0.78 + self.layer * 0.08) * pulse * 255)
        alpha = clamp(alpha, 0, 255)

        sh    = int(lerp(244, 196, storm) * lerp(0.68, 1.0, daylight))
        shade = clamp(sh, 0, 255)
        color = (shade, min(shade + 3, 255), min(shade + 6, 255))

        # nakresli elipsu přes SRCALPHA surface
        ew = int(self.w * 0.52)
        eh = int(self.h * 0.52)
        if ew < 2 or eh < 2:
            return

        pad = 60
        bw  = ew * 2 + pad * 2
        bh  = eh * 2 + pad * 2
        s   = pygame.Surface((bw, bh), pygame.SRCALPHA)

        cx, cy = bw // 2, bh // 2
        for step, a_mult in [(1, 0.34), (2, 0.18)]:
            aw = ew if step == 1 else int(self.w * 0.42)
            ah = eh if step == 1 else int(self.h * 0.78)
            a  = clamp(int(alpha * a_mult), 0, 255)
            pygame.draw.ellipse(s, (*color, a),
                                (cx - aw, cy - ah, aw * 2, ah * 2))

        surf.blit(s, (int(self.x) - bw // 2, int(self.y) - bh // 2))


class FogPuff:
    def __init__(self, W, H, index=0):
        self.W, self.H = W, H
        self.layer = index % 3
        scale = 1.25 if self.layer == 0 else (1.0 if self.layer == 1 else 0.82)
        self.r          = int((random.uniform(140, 320)) * scale)
        self.base_alpha = random.uniform(0.03, 0.07)
        self.speed      = random.uniform(0.08, 0.28)
        self.wobble     = random.uniform(0, math.pi * 2)
        self.drift_y    = random.uniform(-0.12, 0.12)
        self.x          = random.uniform(0, W)
        self.y          = random.uniform(0, H)

    def update(self, wind, t):
        wp = wind * 0.42
        self.x += self.speed * 1.35 + wp * (1 + self.layer * 0.45)
        self.y += self.drift_y * 1.4 + math.sin(t * 0.42 + self.wobble) * 0.08

        if self.x - self.r > self.W + 80:
            self.x = -self.r - random.uniform(0, 120)
            self.y = random.uniform(0, self.H)
        if self.x + self.r < -120:
            self.x = self.W + self.r + random.uniform(0, 120)
            self.y = random.uniform(0, self.H)
        if self.y < -self.r:   self.y = self.H + self.r
        if self.y > self.H + self.r: self.y = -self.r

    def draw(self, surf, density, t):
        if density <= 0.01:
            return
        bo    = density * 0.5
        pulse = 0.8 + math.sin(t * (0.42 + self.layer * 0.1) + self.wobble) * 0.24
        alpha = int(self.base_alpha * bo * pulse * 255)
        alpha = clamp(alpha, 0, 255)
        if alpha < 2:
            return

        size = self.r * 2
        s    = pygame.Surface((size, size), pygame.SRCALPHA)
        cx   = self.r
        # radial gradient simulace — víc kroků
        steps = 8
        for i in range(steps, 0, -1):
            frac  = i / steps
            r_cur = int(self.r * frac)
            if frac < 0.55:
                a_cur = int(alpha * 0.68 * (frac / 0.55))
            else:
                a_cur = int(alpha * (1 - (frac - 0.55) / 0.45))
            a_cur = clamp(a_cur, 0, 255)
            pygame.draw.circle(s, (245, 248, 250, a_cur), (cx, cx), r_cur)

        surf.blit(s, (int(self.x) - self.r, int(self.y) - self.r))

# ─────────────────────────────────────────────
# BLESK
# ─────────────────────────────────────────────
class Lightning:
    def __init__(self):
        self.active  = False
        self.alpha   = 0
        self.timer   = 0
        self.phase   = 0

    def trigger(self):
        if not self.active:
            self.active = True
            self.alpha  = 230
            self.timer  = pygame.time.get_ticks()
            self.phase  = 0

    def update(self):
        if not self.active:
            return
        now = pygame.time.get_ticks()
        elapsed = now - self.timer

        if self.phase == 0 and elapsed > 120:
            self.alpha = 0
            self.phase = 1
            self.timer = now
        elif self.phase == 1 and elapsed > 60:
            # možný druhý záblesk
            if random.random() > 0.5:
                self.alpha = 150
                self.phase = 2
                self.timer = now
            else:
                self.active = False
        elif self.phase == 2 and elapsed > 80:
            self.alpha  = 0
            self.active = False

    def draw(self, surf):
        if self.active and self.alpha > 0:
            W, H = surf.get_size()
            s = pygame.Surface((W, H), pygame.SRCALPHA)
            s.fill((255, 255, 255, self.alpha))
            surf.blit(s, (0, 0))

# ─────────────────────────────────────────────
# HVĚZDY
# ─────────────────────────────────────────────
class Stars:
    def __init__(self, W, H, n=NUM_STARS):
        self.stars = [
            (random.uniform(0, W),
             random.uniform(0, H * 0.72),
             random.uniform(0.3, 1.8),
             random.uniform(0, math.pi * 2))
            for _ in range(n)
        ]

    def draw(self, surf, night_t, cloud, t):
        if night_t < 0.02:
            return
        for (sx, sy, sr, sp) in self.stars:
            twinkle = 0.5 + math.sin(t * 1.3 + sp) * 0.5
            vis     = max(0.0, 1.0 - cloud / 100 * 2.2)
            alpha   = int(night_t * (0.25 + 0.55 * twinkle) * vis * 255)
            alpha   = clamp(alpha, 0, 255)
            if alpha < 3:
                continue
            r = max(1, int(sr))
            s = pygame.Surface((r*2+1, r*2+1), pygame.SRCALPHA)
            pygame.draw.circle(s, (255, 255, 255, alpha), (r, r), r)
            surf.blit(s, (int(sx) - r, int(sy) - r))

# ─────────────────────────────────────────────
# HLAVNÍ TŘÍDA APLIKACE
# ─────────────────────────────────────────────
class WeatherApp:
    def __init__(self):
        pygame.init()
        pygame.mouse.set_visible(False)

        info = pygame.display.Info()
        self.W = info.current_w
        self.H = info.current_h

        self.screen = pygame.display.set_mode(
            (self.W, self.H),
            pygame.FULLSCREEN | pygame.NOFRAME
        )
        pygame.display.set_caption("Okno do dvora")

        self.clock   = pygame.time.Clock()
        self.fetcher = WeatherFetcher()

        # vrstvy (offscreen surfaces)
        def surf():
            s = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            return s

        self.s_bg       = pygame.Surface((self.W, self.H))
        self.s_sun      = surf()
        self.s_clouds   = surf()
        self.s_rain     = surf()
        self.s_fog      = surf()
        self.s_lightning = surf()
        self.s_hud      = surf()

        # particles
        self.clouds   = [CloudBand(self.W, self.H, i) for i in range(NUM_CLOUDS)]
        self.fog      = [FogPuff(self.W, self.H, i)   for i in range(NUM_FOG)]
        self.drops    = []
        self.stars    = Stars(self.W, self.H)
        self.lightning = Lightning()

        # stav
        self.weather      = None
        self.raining      = False
        self.precip_type  = None

        # cloud/fog state
        self.cloud_density = 0.0
        self.cloud_wind    = 0.0
        self.cloud_storm   = 0.0
        self.cloud_dl      = 1.0
        self.fog_density   = 0.0
        self.fog_wind      = 0.0

        # fonty
        self.font_big   = pygame.font.SysFont("monospace", 36, bold=True)
        self.font_med   = pygame.font.SysFont("monospace", 22)
        self.font_small = pygame.font.SysFont("monospace", 16)
        self.font_tiny  = pygame.font.SysFont("monospace", 13)

        self.t0     = time.time()
        self.blink  = True
        self.blink_t = time.time()

    # ── WEATHER STATE ──────────────────────────
    def apply_weather(self, w):
        self.weather = w
        snow = is_snow(w)
        new_p = "snow" if snow else ("rain" if w["rain"] > 0.1 else "none")
        self.raining = w["rain"] > 0.1

        if new_p != self.precip_type:
            self.precip_type = new_p
            if self.raining:
                self._init_drops(snow)
            else:
                self.drops = []
        elif self.raining and not self.drops:
            self._init_drops(snow)

        # cloud state
        self.cloud_density = clamp((w["cloud"] - 8) / 92, 0, 1)
        self.cloud_wind    = w["wind"]
        self.cloud_storm   = 1.0 if w["name"] == "BOUŘE" else clamp(w["rain"] / 6, 0, 0.65)
        self.cloud_dl      = get_daylight(w["hour"])

        # fog state
        self.fog_density = 1.35 if is_fog(w) else clamp((w["cloud"] - 52) / 32, 0, 0.85)
        self.fog_wind    = w["wind"]

    def _init_drops(self, snow):
        self.drops = [Drop(self.W, self.H, snow) for _ in range(NUM_DROPS)]

    # ── BACKGROUND ─────────────────────────────
    def draw_bg(self, w):
        dl   = get_daylight(w["hour"])
        snow = is_snow(w)
        bc   = get_bg_color(w["temp"], w["cloud"])
        if snow:
            bc = (int(bc[0]*0.72), int(bc[1]*0.76), int(bc[2]*0.84))
        fc = apply_light(bc, dl)
        self.s_bg.fill(fc)

    # ── SUN / MOON / STARS ──────────────────────
    def draw_sky(self, w, t):
        self.s_sun.fill((0, 0, 0, 0))
        hour  = w["hour"]
        dl    = get_daylight(hour)
        cloud = w["cloud"] / 100

        # SLUNCE
        sun_t = clamp((hour - 6) / 14, 0, 1)
        sun_x = int(self.W * 0.1 + self.W * 0.8 * sun_t)
        sun_y = int(self.H * 0.55 - math.sin(sun_t * math.pi) * self.H * 0.48)

        if dl > 0.05 and cloud < 0.88:
            op = (1 - cloud) * dl * 0.92
            # glow
            for r, a_mul in [(70, 0.18), (40, 0.35), (22, 0.55)]:
                a = int(op * a_mul * 255)
                a = clamp(a, 0, 255)
                s = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
                pygame.draw.circle(s, (255, 230, 120, a), (r, r), r)
                self.s_sun.blit(s, (sun_x - r, sun_y - r))
            # disk
            a = int(op * 255)
            a = clamp(a, 0, 255)
            s = pygame.Surface((38, 38), pygame.SRCALPHA)
            pygame.draw.circle(s, (255, 242, 165, a), (19, 19), 18)
            self.s_sun.blit(s, (sun_x - 19, sun_y - 19))

        # NOC: hvězdy + měsíc
        if dl < 0.15:
            night_t = 1.0 - dl / 0.15
            self.stars.draw(self.s_sun, night_t, w["cloud"], t)

            moon_raw = hour + 24 if hour < 6 else hour
            moon_t   = clamp((moon_raw - 20) / 14, 0, 1)
            moon_x   = int(self.W * 0.08 + self.W * 0.84 * moon_t)
            moon_y   = int(self.H * 0.58 - math.sin(moon_t * math.pi) * self.H * 0.45)
            moon_op  = night_t * max(0.0, 1.0 - cloud * 1.6) * 0.9

            if moon_op > 0.02:
                for r, a_mul in [(30, 0.25), (14, 0.45), (11, 1.0)]:
                    a = int(moon_op * a_mul * 255)
                    a = clamp(a, 0, 255)
                    s = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
                    color = (230, 240, 255) if r == 11 else (220, 235, 255)
                    pygame.draw.circle(s, (*color, a), (r, r), r)
                    self.s_sun.blit(s, (moon_x - r, moon_y - r))

    # ── MRAKY ───────────────────────────────────
    def draw_clouds(self, t):
        self.s_clouds.fill((0, 0, 0, 0))
        for band in self.clouds:
            band.update(self.cloud_wind, t)
            band.draw(self.s_clouds, self.cloud_density,
                      self.cloud_storm, self.cloud_dl, t)

        # globální overlay
        if self.cloud_density > 0.02:
            sh    = int(lerp(244, 196, self.cloud_storm) * lerp(0.68, 1.0, self.cloud_dl))
            shade = clamp(sh, 0, 255)
            ba    = self.cloud_density * 0.1
            a     = int(ba * 0.26 * 255)
            a     = clamp(a, 0, 255)
            ov = pygame.Surface((self.W, int(self.H * 0.78)), pygame.SRCALPHA)
            ov.fill((shade, shade, shade, a))
            self.s_clouds.blit(ov, (0, 0))

    # ── MLHA ────────────────────────────────────
    def draw_fog(self, t):
        self.s_fog.fill((0, 0, 0, 0))
        for puff in self.fog:
            puff.update(self.fog_wind, t)
            puff.draw(self.s_fog, self.fog_density, t)

        if self.fog_density > 0.01:
            bo = self.fog_density * 0.5
            a  = int(bo * 0.18 * 255)
            ov = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            ov.fill((245, 248, 250, a))
            self.s_fog.blit(ov, (0, 0))

    # ── SRÁŽKY ──────────────────────────────────
    def draw_rain(self, w):
        self.s_rain.fill((0, 0, 0, 0))
        if not self.raining or not self.drops:
            return

        wind = w["wind"]
        snow = is_snow(w)

        for d in self.drops:
            d.update(wind)

        # dešťové kapky kreslíme najednou do jedné surface
        if not snow:
            angle = wind * 8
            rain_i = w["rain"]
            color = (180, 200, 220, 200) if rain_i > 2 else (120, 140, 160, 190)
            for d in self.drops:
                ex = int(d.x + angle)
                ey = int(d.y + d.length)
                pygame.draw.line(self.s_rain, color,
                                 (int(d.x), int(d.y)), (ex, ey), 1)
        else:
            for d in self.drops:
                r = max(1, int(d.radius))
                pygame.draw.circle(self.s_rain, (235, 240, 245, 215),
                                   (int(d.x), int(d.y)), r)

        # blesk při bouři
        if not snow and w["rain"] > 2 and w["cloud"] > 90:
            if random.random() < 0.005:
                self.lightning.trigger()

    # ── BLUR EFEKT (přes tmavší overlay místo blur) ──
    def apply_blur_overlay(self, w):
        fog   = w["cloud"] / 100
        snow  = is_snow(w)
        dl    = get_daylight(w["hour"])

        blur_strength = 0
        if w["rain"] > 0 and not is_fog(w): blur_strength = 0.6
        if w["name"] == "BOUŘE":            blur_strength = 1.0
        if snow:                            blur_strength = max(blur_strength, 0.8)

        if blur_strength > 0:
            dark_a = int(blur_strength * fog * 30)
            if dark_a > 2:
                ov = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
                ov.fill((0, 0, 0, dark_a))
                self.screen.blit(ov, (0, 0))

    # ── HUD ─────────────────────────────────────
    def draw_hud(self, w):
        self.s_hud.fill((0, 0, 0, 0))

        now = datetime.now()
        hr  = now.hour
        mn  = now.minute
        dl  = get_daylight(w["hour"])
        tod = ""
        if dl < 0.05:
            tod = "noc"
        elif dl < 0.35:
            tod = "soumrak"

        # blikající dot (live indikátor)
        if time.time() - self.blink_t > 0.7:
            self.blink   = not self.blink
            self.blink_t = time.time()

        name_txt = w["name"]
        col_name = (255, 255, 255, 220)

        # název počasí
        if self.blink:
            dot_s = self.font_big.render("⬤", True, (255, 85, 85))
            self.s_hud.blit(dot_s, (16, 14))
            ox = dot_s.get_width() + 24
        else:
            ox = 16

        name_s = self.font_big.render(name_txt, True, (255, 255, 255))
        self.s_hud.blit(name_s, (ox, 14))

        # řádek 2: teplota + čas
        sub = f"{w['temp']:.1f}°C  ·  {hr:02d}:{mn:02d}"
        if tod:
            sub += f"  ·  {tod}"
        sub_s = self.font_med.render(sub, True, (220, 220, 220))
        self.s_hud.blit(sub_s, (16, 56))

        # tag vpravo nahoře
        tag = f"Praha · 50°N 14°E"
        tag_s = self.font_tiny.render(tag, True, (180, 180, 180))
        self.s_hud.blit(tag_s, (self.W - tag_s.get_width() - 14, 14))

        # stats dolní lišta
        stats = [
            ("SRÁŽKY",    f"{w['rain']:.1f} mm"),
            ("OBLAČNOST", f"{w['cloud']}%"),
            ("VÍTR",      f"{w['wind_kmh']:.0f} km/h"),
        ]
        bx = 16
        for lbl, val in stats:
            l_s = self.font_tiny.render(lbl, True, (120, 120, 120))
            v_s = self.font_small.render(val, True, (200, 200, 200))
            self.s_hud.blit(l_s, (bx, self.H - 54))
            self.s_hud.blit(v_s, (bx, self.H - 36))
            bx += max(l_s.get_width(), v_s.get_width()) + 28

    # ── CHYBOVÁ OBRAZOVKA ───────────────────────
    def draw_error(self):
        self.screen.fill((10, 10, 10))
        msg  = self.font_med.render("Načítám data...", True, (80, 80, 80))
        msg2 = self.font_small.render("Připojuji se k Open-Meteo API", True, (50, 50, 50))
        self.screen.blit(msg,  (self.W//2 - msg.get_width()//2,  self.H//2 - 20))
        self.screen.blit(msg2, (self.W//2 - msg2.get_width()//2, self.H//2 + 20))

    # ── HLAVNÍ SMYČKA ───────────────────────────
    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_q, pygame.K_ESCAPE):
                        running = False

            # zkus načíst nová data
            new_w = self.fetcher.get()
            if new_w and new_w != self.weather:
                self.apply_weather(new_w)

            if not self.weather:
                self.draw_error()
                pygame.display.flip()
                self.clock.tick(FPS)
                continue

            w = self.weather
            t = time.time() - self.t0

            # kresli vrstvy
            self.draw_bg(w)
            self.draw_sky(w, t)
            self.draw_clouds(t)
            self.draw_fog(t)
            self.draw_rain(w)
            self.lightning.update()
            self.lightning.draw(self.s_lightning)

            # složit na obrazovku
            self.screen.blit(self.s_bg,       (0, 0))
            self.screen.blit(self.s_sun,      (0, 0))
            self.screen.blit(self.s_clouds,   (0, 0))
            self.screen.blit(self.s_rain,     (0, 0))
            self.screen.blit(self.s_fog,      (0, 0))
            self.screen.blit(self.s_lightning,(0, 0))

            self.apply_blur_overlay(w)

            self.draw_hud(w)
            self.screen.blit(self.s_hud, (0, 0))

            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()


# ─────────────────────────────────────────────
# SPUŠTĚNÍ
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = WeatherApp()
    app.run()
