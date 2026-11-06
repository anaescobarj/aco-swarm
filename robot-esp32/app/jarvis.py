"""J.A.R.V.I.S. – asistente conversacional del robot.

Explica el proyecto y comenta en tiempo real las variables que captura el
robot. Usa la API de Claude (Anthropic) si hay credenciales disponibles
(ANTHROPIC_API_KEY o un perfil de `ant auth login`); si no, responde con un
motor de reglas local para que la demo funcione sin internet.
"""
from __future__ import annotations

import json
from collections.abc import Iterator

MODEL = "claude-opus-5-5"

PROJECT_BRIEF = """\
Proyecto: robot móvil autónomo basado en ESP32 (diseño mecánico y electrónico propio).
- Chasis 4WD de dos niveles (MDF/acrílico 3 mm, corte láser), 4 motorreductores TT 1:48, ruedas de 65 mm.
- Puente H TB6612FNG (2 canales: lado izquierdo / derecho, PWM 20 kHz).
- Brújula digital QMC5883L (I2C, 0x0D) montada en un mástil de 8 cm para alejarla del campo de los motores;
  calibración hard/soft-iron girando 8 s en el sitio; declinación magnética -7.8°.
- Sensor de color TCS34725 (I2C, 0x29) mirando al piso a 5 mm, con LED propio; clasifica 6 colores
  (negro, blanco, rojo, amarillo, verde, azul) por cromaticidad normalizada y brillo, con anti-rebote de 3 lecturas.
- Ultrasonido HC-SR04 sobre servo SG90: detecta obstáculos a < 30 cm y escanea izquierda/derecha para decidir
  por dónde esquivar.
- 3 sensores infrarrojos TCRT5000 para seguir la línea guía central de la pista
  (en la sección negra la polaridad se invierte usando el sensor de color).
- Energía: 2 celdas 18650 en serie (7.4 V) + BMS 2S, regulador step-down a 5 V para lógica, servo y sensores.
- Comunicación: Wi-Fi SoftAP (red ROBOT-ESP32, http://192.168.4.1) con API REST/JSON para la app Streamlit;
  ESP-NOW para el control remoto propio (otro ESP32 con joystick).
- Modos: MANUAL (botones o comandos de voz: arriba, abajo, derecha, izquierda, detente; o control ESP-NOW)
  y AUTO (sigue la pista o un rumbo polar deseado con la brújula; si detecta un obstáculo frena, escanea, rodea
  el obstáculo en arco y vuelve a la línea en el sentido original).
- Meta final: 3 niveles de pista (4 obstáculos/3 colores, 6/4, 8/6).
Variables de telemetría (/api/state): heading (rumbo actual, °), heading_des (dirección deseada, °),
heading_err, dist_cm (distancia al obstáculo), obstacle, color, rgbc, color_changes, line [izq,centro,der],
pwm_l / pwm_r (-1..1), batt_v, mode, nav (linea|rumbo), state (estado de la máquina autónoma),
obstacles_avoided, event (último evento), cmd_src (origen del último comando).
"""

SYSTEM_PROMPT = f"""Eres J.A.R.V.I.S., el asistente del robot móvil del proyecto final, con el tono cortés y \
ligeramente ingenioso del asistente de Tony Stark. Hablas en español, con frases cortas y claras.

Tu trabajo:
1. Explicar el proyecto (arquitectura, módulos, materiales, decisiones de diseño) a profesores y compañeros.
2. Interpretar la telemetría en tiempo real que llega en cada mensaje dentro de <telemetria>: cita valores \
concretos con unidades y explica qué significan (por ejemplo, si el error de rumbo es grande, si hay un obstáculo \
cerca, en qué sección de color está, si la batería está baja: < 7.0 V).
3. Si te piden mover el robot, explica que los comandos se dan con los botones o por voz en la pestaña \
de control; no inventes que lo moviste.

Si un dato no está en la telemetría ni en la descripción, dilo; no inventes cifras.

Descripción del proyecto:
{PROJECT_BRIEF}"""


def _telemetry_block(state: dict | None) -> str:
    if not state:
        return "<telemetria>sin conexión con el robot</telemetria>"
    slim = {k: v for k, v in state.items() if k not in ("mag_raw",)}
    return f"<telemetria>{json.dumps(slim, ensure_ascii=False)}</telemetria>"


def build_messages(history: list[dict], question: str, state: dict | None) -> list[dict]:
    """Historial + pregunta actual con la telemetría adjunta (solo en el último turno)."""
    msgs = [{"role": m["role"], "content": m["content"]} for m in history]
    msgs.append({"role": "user", "content": f"{_telemetry_block(state)}\n\n{question}"})
    return msgs


def llm_available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    import os
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return os.path.isdir(os.path.expanduser("~/.config/anthropic"))


def ask_claude(history: list[dict], question: str, state: dict | None) -> Iterator[str]:
    """Respuesta en streaming desde Claude."""
    import anthropic

    client = anthropic.Anthropic()
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=build_messages(history, question, state),
        output_config={"effort": "low"},           # conversación: respuestas rápidas
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",                       # reintento automático si el modelo declina
    ) as stream:
        yield from stream.text_stream
        final = stream.get_final_message()
    if final.stop_reason == "refusal":
        yield "\n\n(No puedo responder eso, señor.)"


def ask_local(question: str, state: dict | None) -> str:
    """Motor de reglas de respaldo (sin LLM)."""
    from commands import normalize
    q = normalize(question)
    if not state:
        return "No tengo conexión con el robot, señor. Verifique que está conectado a la red ROBOT-ESP32."
    s = state
    parts = []
    if any(w in q for w in ("rumbo", "direccion", "brujula", "orient")):
        parts.append(f"El rumbo actual es {s['heading']:.0f}° y la dirección deseada {s['heading_des']:.0f}°; "
                     f"el error es de {s['heading_err']:+.0f}°.")
    if any(w in q for w in ("obstac", "distancia", "ultrason")):
        parts.append(f"El ultrasonido mide {s['dist_cm']:.0f} cm al frente; he esquivado "
                     f"{s['obstacles_avoided']} obstáculos." + (" ¡Hay un obstáculo cerca!" if s["obstacle"] else ""))
    if "color" in q or "seccion" in q:
        parts.append(f"Estoy sobre la sección {s['color']} (RGBC {s['rgbc']}); llevo {s['color_changes']} "
                     "cambios de sección.")
    if "bater" in q:
        parts.append(f"La batería está en {s['batt_v']:.2f} V" + (" — conviene recargarla." if s["batt_v"] < 7.0 else "."))
    if "modo" in q or "estado" in q:
        parts.append(f"Modo {s['mode']} (navegación por {s['nav']}), estado {s['state']}.")
    if any(w in q for w in ("proyecto", "explica", "que eres", "funciona")):
        parts.append("Soy un robot 4WD con ESP32: sigo la pista con sensores infrarrojos, mantengo el rumbo con una "
                     "brújula QMC5883L, detecto colores con un TCS34725 y esquivo obstáculos con un HC-SR04 sobre "
                     "un servo. Me controlan por Wi-Fi desde esta app, por voz o con un control ESP-NOW.")
    if not parts:
        parts.append(f"Resumen: modo {s['mode']}, estado {s['state']}, rumbo {s['heading']:.0f}° "
                     f"(deseado {s['heading_des']:.0f}°), obstáculo a {s['dist_cm']:.0f} cm, color {s['color']}, "
                     f"batería {s['batt_v']:.2f} V. Último evento: {s['event']}.")
    return " ".join(parts)
