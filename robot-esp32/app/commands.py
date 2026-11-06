"""Intérprete de comandos de voz / texto en español para el robot.

Convierte frases como "arriba", "gira a la derecha", "rumbo 90",
"modo automático" o "detente" en acciones de la API del ESP32.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

SYNONYMS = {
    "forward": ["arriba", "adelante", "avanza", "avanzar", "sigue", "recto", "derecho al frente", "frente"],
    "backward": ["abajo", "atras", "retrocede", "retroceder", "reversa", "devuelvete"],
    "right": ["derecha"],
    "left": ["izquierda"],
    "stop": ["detente", "detener", "alto", "para", "parar", "stop", "frena", "frenar", "quieto"],
}

NUM_WORDS = {
    "cero": 0, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "quince": 15, "veinte": 20, "treinta": 30,
    "cuarenta": 40, "cuarenta y cinco": 45, "sesenta": 60, "noventa": 90, "cien": 100,
    "ciento ochenta": 180, "doscientos setenta": 270,
}


@dataclass
class Action:
    kind: str                      # move | stop | mode | heading | heading_rel | speed | calibrate
    params: dict = field(default_factory=dict)
    text: str = ""                 # descripción para mostrar al usuario

    def __str__(self) -> str:
        return self.text or f"{self.kind} {self.params}"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s\.\-]", " ", text)
    for words, value in sorted(NUM_WORDS.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"\b{words}\b", str(value), text)
    return re.sub(r"\s+", " ", text).strip()


def _has(text: str, words: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def _number(text: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


def parse(text: str) -> Action | None:
    """Devuelve la acción correspondiente a la frase, o None si no se entiende."""
    t = normalize(text)
    if not t:
        return None

    if _has(t, SYNONYMS["stop"]):
        return Action("stop", {}, "Detener el robot")

    if "calibra" in t and ("brujula" in t or "compas" in t):
        return Action("calibrate", {"what": "compass"}, "Calibrar la brújula (gira 8 s)")

    if "modo" in t or "automatico" in t or "manual" in t or "autonomo" in t:
        if _has(t, ["automatico", "autonomo", "auto"]):
            nav = "rumbo" if "rumbo" in t or "brujula" in t else "linea"
            return Action("mode", {"m": "auto", "nav": nav}, f"Modo automático ({nav})")
        if "manual" in t:
            return Action("mode", {"m": "manual"}, "Modo manual")

    if "velocidad" in t:
        n = _number(t)
        if n is not None:
            return Action("speed", {"v": max(20, min(100, n))}, f"Velocidad autónoma {n:.0f}%")

    # Dirección polar deseada: "rumbo 90", "orientate a 180 grados", "norte"
    cardinal = {"norte": 0, "noreste": 45, "este": 90, "oriente": 90, "sureste": 135, "sur": 180,
                "suroeste": 225, "oeste": 270, "occidente": 270, "noroeste": 315}
    if _has(t, ["rumbo", "orientate", "orientar", "direccion", "apunta"]) or (
            _has(t, [c for c in cardinal if c != "este"]) and not _has(t, ["derecha", "izquierda"])):
        for name, deg in cardinal.items():
            if re.search(rf"\b{name}\b", t):
                return Action("heading", {"deg": deg}, f"Dirección deseada {deg}° ({name})")
        n = _number(t)
        if n is not None:
            return Action("heading", {"deg": n % 360}, f"Dirección deseada {n % 360:.0f}°")

    # Giros relativos: "gira 45 grados a la derecha"
    n = _number(t)
    if n is not None and "grado" in t and _has(t, ["derecha", "izquierda"]):
        sign = 1 if "derecha" in t else -1
        return Action("heading_rel", {"rel": sign * n},
                      f"Girar {n:.0f}° a la {'derecha' if sign > 0 else 'izquierda'}")

    for move in ("forward", "backward", "right", "left"):
        if _has(t, SYNONYMS[move]):
            ms = 600 if move in ("forward", "backward") else 350
            if n is not None and _has(t, ["segundo", "segundos", "s"]):
                ms = int(max(0.1, min(5.0, n)) * 1000)
            label = {"forward": "Arriba", "backward": "Abajo", "right": "Derecha", "left": "Izquierda"}[move]
            return Action("move", {"move": move, "ms": ms}, f"{label} ({ms} ms)")
    return None
