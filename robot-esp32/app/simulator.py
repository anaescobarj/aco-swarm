"""Gemelo digital del robot: expone la MISMA API HTTP del firmware ESP32.

Permite desarrollar y probar la app Streamlit y el chatbot sin hardware,
y validar la lógica autónoma (seguimiento de línea + brújula + evasión de
obstáculos + detección de colores) en las tres pistas de la meta final.

Uso:
    python simulator.py --nivel 1 --port 8000
    # en la app: URL del robot = http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import math
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# ----------------------------------------------------------------------------
#  Parámetros (los mismos de firmware/robot_esp32/config.h)
# ----------------------------------------------------------------------------
LOOP_DT = 0.05
OBSTACLE_CM = 30.0
SAFETY_STOP_CM = 12.0
TEMP_AMBIENT = 25.0     # °C
TEMP_WARN_C = 45.0      # mismos umbrales que config.h
TEMP_CUTOFF_C = 55.0
TEMP_HYST_C = 5.0
TEMP_TAU = 300.0        # s, constante térmica del paquete de baterías
TEMP_GAIN = 8.0         # °C de aumento en equilibrio por unidad de carga (|pwm_l|+|pwm_r|)
AUTO_BASE_SPEED = 0.55
TURN_SPEED = 0.50
RODEO_W = 0.13
KP_HEADING = 0.012
HEADING_TOL = 8.0
SERVO_CENTER, SERVO_LEFT, SERVO_RIGHT = 90, 160, 20
VMAX = 0.50            # m/s a PWM máximo permitido
WHEELBASE = 0.15       # m (ancho de vía)
SONAR_FWD = 0.10       # m, sensor delante del centro
IR_FWD, IR_LAT = 0.07, 0.015
TAPE_HALF = 0.0095     # cinta de 19 mm
COLOR_NAMES = ["negro", "blanco", "rojo", "amarillo", "verde", "azul"]
COLOR_RGB = {"negro": (60, 55, 45, 120), "blanco": (900, 1000, 900, 3000), "rojo": (700, 260, 240, 900),
             "amarillo": (1100, 1000, 420, 2100), "verde": (240, 420, 250, 700), "azul": (180, 290, 430, 650)}

LEVELS = {
    1: {"obstacles": 4, "colors": ["rojo", "verde", "azul"]},
    2: {"obstacles": 6, "colors": ["rojo", "amarillo", "verde", "azul"]},
    3: {"obstacles": 8, "colors": ["rojo", "amarillo", "verde", "azul", "blanco", "negro"]},
}


def wrap360(a: float) -> float:
    return a % 360.0


def wrap180(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def make_track(level: int, n: int = 900) -> list[tuple[float, float]]:
    """Curva cerrada (línea guía central) para cada nivel, en metros."""
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        if level == 1:      # óvalo deformado (pista tipo "frijol")
            r = 1.0 + 0.18 * math.sin(2 * t)
            x, y = 1.5 * r * math.cos(t), 0.9 * r * math.sin(t)
        elif level == 2:    # estrella suave de 5 puntas
            r = 1.0 + 0.16 * math.cos(5 * t)
            x, y = 1.3 * r * math.cos(t), 1.3 * r * math.sin(t)
        else:               # pista irregular con curvas encadenadas
            r = 1.0 + 0.14 * math.sin(3 * t) + 0.08 * math.cos(5 * t + 0.7)
            x, y = 1.5 * r * math.cos(t), 1.2 * r * math.sin(t)
        pts.append((x, y))
    return pts


class World:
    def __init__(self, level: int, seed: int = 1):
        self.level = level
        self.rng = random.Random(seed)
        self.track = make_track(level)
        n = len(self.track)
        self.cum = [0.0]
        for i in range(1, n + 1):
            a, b = self.track[i - 1], self.track[i % n]
            self.cum.append(self.cum[-1] + math.dist(a, b))
        self.length = self.cum[-1]
        cfg = LEVELS[level]
        self.section_colors = cfg["colors"]
        # obstáculos (conos de r = 5 cm) sobre la línea, alejados de los cambios de color
        k = cfg["obstacles"]
        self.obstacles = []
        for j in range(k):
            frac = (j + 0.55) / k
            idx = self.index_at(frac * self.length)
            self.obstacles.append((*self.track[idx], 0.05))

    def index_at(self, s: float) -> int:
        s %= self.length
        lo, hi = 0, len(self.track)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.cum[mid] < s:
                lo = mid + 1
            else:
                hi = mid
        return min(lo, len(self.track) - 1)

    def nearest(self, x: float, y: float) -> tuple[int, float]:
        best, bi = 1e9, 0
        for i in range(0, len(self.track), 3):
            px, py = self.track[i]
            d = (px - x) ** 2 + (py - y) ** 2
            if d < best:
                best, bi = d, i
        for i in range(bi - 3, bi + 4):          # refinamiento local
            px, py = self.track[i % len(self.track)]
            d = (px - x) ** 2 + (py - y) ** 2
            if d < best:
                best, bi = d, i % len(self.track)
        return bi, math.sqrt(best)

    def on_tape(self, x: float, y: float) -> bool:
        return self.nearest(x, y)[1] < TAPE_HALF

    def color_at(self, x: float, y: float) -> str:
        i, _ = self.nearest(x, y)
        frac = self.cum[i] / self.length
        return self.section_colors[int(frac * len(self.section_colors)) % len(self.section_colors)]

    def sonar(self, x: float, y: float, theta: float) -> float:
        """Distancia (cm) al obstáculo más cercano en un cono de ±15°."""
        best = 400.0
        for ox, oy, r in self.obstacles:
            dx, dy = ox - x, oy - y
            d = math.hypot(dx, dy)
            ang = abs(wrap180(math.degrees(math.atan2(dy, dx)) - theta))
            half = 15 + math.degrees(math.asin(min(1.0, r / max(d, 1e-6))))   # haz ±15° + tamaño aparente
            if ang < half and d - r < 2.0:
                best = min(best, max(2.0, (d - r) * 100))
        return best


class SimRobot:
    def __init__(self, level: int = 1, seed: int = 1):
        self.world = World(level, seed)
        self.lock = threading.Lock()
        self.rng = random.Random(seed)
        x0, y0 = self.world.track[0]
        x1, y1 = self.world.track[3]
        self.x, self.y, self.theta = x0, y0, math.atan2(y1 - y0, x1 - x0)
        self.t = 0.0
        self.mode, self.nav, self.state = "MANUAL", "linea", "SEGUIR"
        self.state_since = 0.0
        self.heading = self.compass()
        self.heading_des = self.heading
        self.auto_speed = AUTO_BASE_SPEED
        self.manual_v = self.manual_w = 0.0
        self.manual_until = 0.0
        self.cmd_src, self.last_move = "ninguno", "stop"
        self.pwm_l = self.pwm_r = 0.0
        self.dist = 400.0
        self.servo = SERVO_CENTER
        self.line = [False, False, False]
        self.line_last_seen = 0.0
        self.prev_line_seen = 0.0
        self.color = self.world.color_at(self.x, self.y)
        self.color_candidate, self.color_count, self.color_changes = self.color, 0, 0
        self.h0, self.side, self.dist_left, self.dist_right = 0.0, 1, 0.0, 0.0
        self.obstacles_avoided = 0
        self.last_line_err = 0.0
        self.avoid_end = -100.0
        self.collisions = 0
        self._colliding = False
        self.event, self.event_id = "Simulador iniciado", 0
        self.distance_m = 0.0
        self.batt = 8.2
        self.temp = TEMP_AMBIENT
        self.temp_level = 0
        self.trail: list[tuple[float, float]] = []
        self.calib_since = 0.0

    # ------------------------------------------------------------------ util
    def compass(self) -> float:
        return wrap360(90 - math.degrees(self.theta) + self.rng.gauss(0, 0.8))

    def log(self, msg: str) -> None:
        self.event, self.event_id = msg, self.event_id + 1

    def set_state(self, s: str) -> None:
        self.state, self.state_since = s, self.t

    def set_mode(self, m: str) -> None:
        self.mode = m
        self.manual_v = self.manual_w = 0.0
        self.pwm_l = self.pwm_r = 0.0
        if m == "AUTO":
            if self.nav == "linea":
                self.heading_des = self.heading
            self.set_state("SEGUIR")
        if m == "CALIBRANDO":
            self.calib_since = self.t
        self.log(f"Modo {m}")

    def arcade(self, v: float, w: float) -> None:
        left, right = v + w, v - w
        m = max(abs(left), abs(right))
        if m > 1:
            left, right = left / m, right / m
        self.pwm_l, self.pwm_r = left, right

    def turn_to(self, target: float) -> bool:
        err = wrap180(target - self.heading)
        if abs(err) < HEADING_TOL:
            self.arcade(0, 0)
            return True
        w = max(-TURN_SPEED, min(TURN_SPEED, KP_HEADING * 2 * err))
        if abs(w) < 0.35:
            w = math.copysign(0.35, w)
        self.arcade(0, w)
        return False

    def drive_heading(self, target: float, speed: float) -> None:
        err = wrap180(target - self.heading)
        w = max(-0.5, min(0.5, KP_HEADING * err))
        self.arcade(speed * 0.3 if abs(err) > 45 else speed, w)

    def sonar_at(self, servo: int) -> float:
        fx = self.x + SONAR_FWD * math.cos(self.theta)
        fy = self.y + SONAR_FWD * math.sin(self.theta)
        return self.world.sonar(fx, fy, math.degrees(self.theta) + (servo - SERVO_CENTER))

    # -------------------------------------------------------------- control
    def auto_control(self) -> None:
        dt = self.t - self.state_since
        s = self.state
        if s == "SEGUIR":
            if self.dist < OBSTACLE_CM:
                self.h0 = self.heading if self.nav == "linea" else self.heading_des
                self.arcade(0, 0)
                self.log(f"Obstaculo a {self.dist:.0f} cm: iniciando evasion")
                self.set_state("FRENO")
                return
            if self.nav == "rumbo":
                self.drive_heading(self.heading_des, self.auto_speed)
                return
            if any(self.line) and self.t - self.prev_line_seen > 0.8 and \
                    self.t - self.avoid_end < 6.0 and abs(wrap180(self.heading - self.h0)) > 100:
                # se retomó la línea en sentido contrario: reorientar con la brújula
                self.log("Linea retomada en sentido contrario: reorientando")
                self.set_state("REORIENTAR")
                return
            if any(self.line):
                l, c, r = self.line
                n = l + c + r
                err = ((1 if r else 0) - (1 if l else 0)) / n
                self.arcade(self.auto_speed, 0.45 * err)
                if err:
                    self.last_line_err = err
                self.heading_des = wrap360(self.heading_des + 0.2 * wrap180(self.heading - self.heading_des))
            elif self.t - self.line_last_seen < 0.8:
                self.drive_heading(self.heading_des, self.auto_speed * 0.8)
            elif self.last_line_err:
                # búsqueda: gira hacia el lado donde se vio la línea por última vez
                # espiral que se abre con el tiempo para no quedar girando en círculo
                lost = self.t - self.line_last_seen
                w = 0.35 * max(0.2, 1 - (lost - 0.8) / 6)
                self.arcade(self.auto_speed * 0.5, math.copysign(w, self.last_line_err))
            else:
                self.drive_heading(self.heading_des, self.auto_speed * 0.5)
        elif s == "FRENO":
            if dt > 0.25:
                self.servo = SERVO_LEFT
                self.set_state("ESCANEO_IZQ")
        elif s == "ESCANEO_IZQ":
            if dt > 0.35:
                self.dist_left = self.sonar_at(SERVO_LEFT)
                self.servo = SERVO_RIGHT
                self.set_state("ESCANEO_DER")
        elif s == "ESCANEO_DER":
            if dt > 0.45:
                self.dist_right = self.sonar_at(SERVO_RIGHT)
                self.servo = SERVO_CENTER
                self.side = 1 if self.dist_right >= self.dist_left else -1
                self.log(f"Esquivando por la {'derecha' if self.side > 0 else 'izquierda'} "
                         f"(izq {self.dist_left:.0f} cm, der {self.dist_right:.0f} cm)")
                self.set_state("GIRO_EVASION")
        elif s == "GIRO_EVASION":
            if self.turn_to(self.h0 + self.side * 60) or dt > 2.5:
                self.set_state("AVANCE_LATERAL")
        elif s == "AVANCE_LATERAL":
            self.drive_heading(self.h0 + self.side * 60, self.auto_speed)
            if dt > 0.7:
                self.set_state("RODEO")
        elif s == "RODEO":
            # arco que rodea el obstáculo y regresa hacia el trayecto
            if self.dist < OBSTACLE_CM * 0.6:
                self.arcade(0, 0)
                self.set_state("FRENO")
                return
            self.arcade(self.auto_speed, -self.side * RODEO_W)
            found = self.nav == "linea" and any(self.line) and dt > 0.5
            if found or dt > 5.0 or \
                    (self.nav == "rumbo" and abs(wrap180(self.heading - (self.h0 - self.side * 45))) < 10):
                self.obstacles_avoided += 1
                self.heading_des = self.h0
                self.avoid_end = self.t
                self.log(f"Obstaculo superado (#{self.obstacles_avoided}), retomando trayecto")
                self.set_state("CRUZAR" if found else "SEGUIR")
        elif s == "CRUZAR":
            # avanza hasta dejar el centro del robot sobre la línea
            self.arcade(self.auto_speed * 0.6, 0)
            if dt > 0.3:
                self.set_state("ALINEAR")
        elif s == "ALINEAR":
            # gira en el sitio hacia el lado de la evasión hasta quedar sobre la línea
            # y apuntando en el sentido original de la pista (±90° de h0)
            # pivotando sobre la línea, el primer cruce girando hacia el lado de la evasión
            # corresponde al sentido de avance original de la pista
            if self.line[1] and dt > 0.25:
                self.heading_des = self.heading
                self.last_line_err = 0.0
                self.set_state("SEGUIR")
            elif dt > 4.0:
                self.set_state("SEGUIR")
            else:
                self.arcade(0, self.side * 0.38)
        elif s == "REORIENTAR":
            if self.turn_to(self.h0) or dt > 3.0:
                self.heading_des = self.heading
                self.avoid_end = -100.0      # solo una reorientación por evasión
                self.set_state("SEGUIR")
        elif s == "PAUSA":
            self.arcade(0, 0)

    def manual_control(self) -> None:
        if self.t > self.manual_until:
            self.manual_v = self.manual_w = 0.0
            self.last_move = "stop"
        v, w = self.manual_v, self.manual_w
        if v > 0 and self.dist < SAFETY_STOP_CM:
            v = 0.0
        if self.temp_level == 2:          # en sobretemperatura solo maniobras lentas
            v, w = v * 0.4, w * 0.4
        self.arcade(v, w)

    def thermal_protection(self) -> None:
        t = self.temp
        if self.temp_level < 2 and t >= TEMP_CUTOFF_C:
            self.temp_level = 2
            if self.mode != "MANUAL":
                self.set_mode("MANUAL")
            self.arcade(0, 0)
            self.log(f"SOBRETEMPERATURA {t:.1f} C: motores detenidos")
        elif self.temp_level == 0 and t >= TEMP_WARN_C:
            self.temp_level = 1
            self.log(f"Temperatura alta en baterias: {t:.1f} C")
        elif self.temp_level > 0 and t < TEMP_WARN_C - TEMP_HYST_C:
            self.temp_level = 0
            self.log(f"Temperatura normal: {t:.1f} C")

    def step(self, dt: float = LOOP_DT) -> None:
        with self.lock:
            self.t += dt
            # percepción
            self.heading = self.compass()
            pts = []
            for lat in (IR_LAT, 0.0, -IR_LAT):       # izquierda, centro, derecha
                px = self.x + IR_FWD * math.cos(self.theta) - lat * math.sin(self.theta)
                py = self.y + IR_FWD * math.sin(self.theta) + lat * math.cos(self.theta)
                pts.append(self.world.on_tape(px, py))
            self.line = pts
            self.prev_line_seen = self.line_last_seen
            if any(pts):
                self.line_last_seen = self.t
            if self.state not in ("ESCANEO_IZQ", "ESCANEO_DER"):
                self.dist = self.sonar_at(SERVO_CENTER)
            c = self.world.color_at(self.x, self.y)
            if c == self.color_candidate:
                self.color_count += 1
            else:
                self.color_candidate, self.color_count = c, 1
            if self.color_count >= 3 and c != self.color:
                self.log(f"Cambio de seccion: {self.color} -> {c}")
                self.color, self.color_changes = c, self.color_changes + 1
            # decisión
            self.thermal_protection()
            if self.mode == "MANUAL":
                self.manual_control()
            elif self.mode == "AUTO":
                self.auto_control()
            else:
                self.arcade(0, 0.45)
                if self.t - self.calib_since > 8:
                    self.set_mode("MANUAL")
                    self.log("Brujula calibrada")
            # cinemática diferencial
            vl, vr = VMAX * self.pwm_l, VMAX * self.pwm_r
            v, w = (vl + vr) / 2, (vr - vl) / WHEELBASE
            self.theta += w * dt
            self.x += v * math.cos(self.theta) * dt
            self.y += v * math.sin(self.theta) * dt
            self.distance_m += abs(v) * dt
            self.batt = max(6.6, self.batt - (abs(self.pwm_l) + abs(self.pwm_r)) * 2e-5)
            # termistor NTC: modelo térmico de primer orden calentado por la corriente de motores
            load = abs(self.pwm_l) + abs(self.pwm_r)
            self.temp += (TEMP_AMBIENT + TEMP_GAIN * load - self.temp) * dt / TEMP_TAU
            hit = any(math.hypot(ox - self.x, oy - self.y) < r + 0.08 for ox, oy, r in self.world.obstacles)
            if hit and not self._colliding:
                self.collisions += 1
            self._colliding = hit
            if not self.trail or math.dist(self.trail[-1], (self.x, self.y)) > 0.03:
                self.trail.append((self.x, self.y))
                self.trail = self.trail[-600:]

    # ------------------------------------------------------------------ API
    def state_json(self) -> dict:
        with self.lock:
            r, g, b, c = COLOR_RGB[self.color]
            return {
                "t": int(self.t * 1000), "mode": self.mode, "nav": self.nav, "state": self.state,
                "heading": round(self.heading, 1), "heading_des": round(self.heading_des, 1),
                "heading_err": round(wrap180(self.heading_des - self.heading), 1),
                "mag_raw": [int(3000 * math.cos(self.theta)), int(3000 * math.sin(self.theta)), -1200],
                "compass_ok": True, "dist_cm": round(self.dist, 1), "obstacle": self.dist < OBSTACLE_CM,
                "servo": self.servo, "obstacles_avoided": self.obstacles_avoided,
                "color": self.color, "rgbc": [r, g, b, c], "color_changes": self.color_changes,
                "color_ok": True, "line": [int(v) for v in self.line],
                "pwm_l": round(self.pwm_l, 2), "pwm_r": round(self.pwm_r, 2),
                "auto_speed": self.auto_speed, "batt_v": round(self.batt, 2), "temp_c": round(self.temp, 1), "temp_ok": True,
                "temp_alarm": self.temp_level, "rssi_clients": 1,
                "cmd_src": self.cmd_src, "last_move": self.last_move,
                "event_id": self.event_id, "event": self.event, "uptime_s": int(self.t),
                "sim": {"x": round(self.x, 3), "y": round(self.y, 3), "level": self.world.level,
                        "collisions": self.collisions, "distance_m": round(self.distance_m, 2)},
            }

    def track_json(self) -> dict:
        w = self.world
        with self.lock:
            trail = list(self.trail)
        sections = []
        n = len(w.track)
        for i in range(0, n, 3):
            frac = w.cum[i] / w.length
            sections.append(w.section_colors[int(frac * len(w.section_colors)) % len(w.section_colors)])
        return {"track": w.track[::3], "sections": sections, "obstacles": w.obstacles,
                "trail": trail, "level": w.level}

    def handle(self, path: str, q: dict) -> tuple[int, dict]:
        arg = lambda k, d=None: q.get(k, [d])[0]  # noqa: E731
        with self.lock:
            if path == "/api/cmd":
                m = arg("move", "")
                src = arg("src", "app")
                aliases = {"arriba": "forward", "abajo": "backward", "derecha": "right",
                           "izquierda": "left", "parar": "stop"}
                m = aliases.get(m, m)
                if m not in ("forward", "backward", "left", "right", "stop"):
                    return 400, {"ok": False, "msg": "move invalido"}
                if self.mode != "MANUAL":
                    self.set_mode("MANUAL")
                speed = float(arg("speed", 60)) / 100
                ms = max(100, min(5000, int(float(arg("ms", 500)))))
                self.manual_v = speed if m == "forward" else -speed if m == "backward" else 0.0
                self.manual_w = 0.8 * speed if m == "right" else -0.8 * speed if m == "left" else 0.0
                self.manual_until = self.t + (0.1 if m == "stop" else ms / 1000)
                self.cmd_src, self.last_move = src, m
                return 200, {"ok": True, "msg": m}
            if path == "/api/mode":
                m = arg("m")
                if arg("nav"):
                    self.nav = "rumbo" if arg("nav") == "rumbo" else "linea"
                if m == "auto" and self.temp_level == 2:
                    return 409, {"ok": False, "msg": "sobretemperatura"}
                if m == "auto":
                    self.set_mode("AUTO")
                elif m == "manual":
                    self.set_mode("MANUAL")
                elif m == "pausa" and self.mode == "AUTO":
                    self.set_state("PAUSA")
                elif m == "reanudar" and self.mode == "AUTO":
                    self.set_state("SEGUIR")
                elif not arg("nav"):
                    return 400, {"ok": False, "msg": "modo invalido"}
                return 200, {"ok": True, "msg": self.mode}
            if path == "/api/sim/temp":      # solo simulador: forzar temperatura para probar la alarma
                self.temp = float(arg("c", TEMP_AMBIENT))
                return 200, {"ok": True, "msg": f"temp {self.temp:.1f}"}
            if path == "/api/heading":
                if arg("deg") is not None:
                    self.heading_des = wrap360(float(arg("deg")))
                elif arg("rel") is not None:
                    self.heading_des = wrap360(self.heading + float(arg("rel")))
                else:
                    return 400, {"ok": False, "msg": "use deg o rel"}
                self.log(f"Direccion deseada {self.heading_des:.0f} grados")
                return 200, {"ok": True, "msg": "heading"}
            if path == "/api/speed":
                self.auto_speed = max(0.2, min(1.0, float(arg("v", 55)) / 100))
                return 200, {"ok": True, "msg": "speed"}
            if path == "/api/calibrate":
                if arg("what") == "compass":
                    self.set_mode("CALIBRANDO")
                    return 200, {"ok": True, "msg": "girando 8 s"}
                if arg("what") == "color" and arg("name") in COLOR_NAMES:
                    return 200, {"ok": True, "msg": "color calibrado"}
                return 400, {"ok": False, "msg": "parametros invalidos"}
        return 404, {"ok": False, "msg": "no encontrado"}


def make_handler(robot: SimRobot):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            u = urlparse(self.path)
            if u.path == "/api/state":
                return self._send(200, robot.state_json())
            if u.path == "/api/sim/track":
                return self._send(200, robot.track_json())
            code, body = robot.handle(u.path, parse_qs(u.query))
            self._send(code, body)

        def log_message(self, *args):
            pass

    return Handler


def run(level: int = 1, port: int = 8000, seed: int = 1, speedup: float = 1.0) -> None:
    robot = SimRobot(level, seed)

    def loop():
        while True:
            robot.step(LOOP_DT)
            time.sleep(LOOP_DT / speedup)

    threading.Thread(target=loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(robot))
    print(f"Simulador nivel {level} en http://localhost:{port}  (Ctrl+C para salir)")
    srv.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Gemelo digital del robot ESP32")
    ap.add_argument("--nivel", type=int, default=1, choices=[1, 2, 3])
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--speedup", type=float, default=1.0)
    a = ap.parse_args()
    run(a.nivel, a.port, a.seed, a.speedup)
