"""Cliente HTTP de la API del robot (ESP32 real o simulador)."""
from __future__ import annotations

import requests

from commands import Action

DEFAULT_URL = "http://192.168.4.1"   # SoftAP del ESP32


class RobotClient:
    def __init__(self, base_url: str = DEFAULT_URL, timeout: float = 1.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, **params) -> dict:
        r = requests.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ---- lectura ----
    def state(self) -> dict:
        return self._get("/api/state")

    def track(self) -> dict | None:
        """Solo disponible en el simulador (mapa de la pista)."""
        try:
            return self._get("/api/sim/track")
        except requests.RequestException:
            return None

    # ---- comandos ----
    def move(self, move: str, speed: int = 60, ms: int = 600, src: str = "app") -> dict:
        return self._get("/api/cmd", move=move, speed=speed, ms=ms, src=src)

    def stop(self, src: str = "app") -> dict:
        return self._get("/api/cmd", move="stop", src=src)

    def mode(self, m: str, nav: str | None = None) -> dict:
        params = {"m": m}
        if nav:
            params["nav"] = nav
        return self._get("/api/mode", **params)

    def heading(self, deg: float | None = None, rel: float | None = None) -> dict:
        return self._get("/api/heading", **({"deg": deg} if deg is not None else {"rel": rel}))

    def speed(self, v: float) -> dict:
        return self._get("/api/speed", v=v)

    def calibrate(self, what: str, name: str | None = None) -> dict:
        params = {"what": what}
        if name:
            params["name"] = name
        return self._get("/api/calibrate", **params)

    def execute(self, action: Action, speed: int = 60, src: str = "voz") -> dict:
        p = action.params
        if action.kind == "move":
            return self.move(p["move"], speed=speed, ms=p.get("ms", 600), src=src)
        if action.kind == "stop":
            return self.stop(src=src)
        if action.kind == "mode":
            return self.mode(p["m"], p.get("nav"))
        if action.kind == "heading":
            return self.heading(deg=p["deg"])
        if action.kind == "heading_rel":
            return self.heading(rel=p["rel"])
        if action.kind == "speed":
            return self.speed(p["v"])
        if action.kind == "calibrate":
            return self.calibrate(p["what"])
        raise ValueError(f"Acción desconocida: {action.kind}")
