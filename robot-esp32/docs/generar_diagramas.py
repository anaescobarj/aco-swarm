"""Genera los diagramas del informe en docs/img/.

    python docs/generar_diagramas.py

Requiere: graphviz (binario `dot`), python-graphviz, schemdraw, matplotlib.
"""
from __future__ import annotations

import math
import os
import sys

import graphviz
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import schemdraw  # noqa: E402
import schemdraw.elements as elm  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "img")
sys.path.insert(0, os.path.join(HERE, "..", "app"))
os.makedirs(OUT, exist_ok=True)

FONT = "Helvetica"
C = {"pot": "#fde2e4", "proc": "#dbeafe", "sens": "#dcfce7", "act": "#fef3c7", "com": "#ede9fe", "sw": "#f1f5f9"}


def g(name: str, rankdir: str = "LR") -> graphviz.Digraph:
    d = graphviz.Digraph(name, format="png")
    d.attr(rankdir=rankdir, dpi="200", fontname=FONT, bgcolor="white", nodesep="0.35", ranksep="0.45")
    d.attr("node", shape="box", style="rounded,filled", fontname=FONT, fontsize="11", fillcolor="white")
    d.attr("edge", fontname=FONT, fontsize="9", color="#334155")
    return d


def save(d: graphviz.Digraph, name: str) -> None:
    d.render(os.path.join(OUT, name), cleanup=True)


# ---------------------------------------------------------------------------- arquitectura general
def arquitectura():
    d = g("arquitectura")
    with d.subgraph(name="cluster_robot") as r:
        r.attr(label="ROBOT MÓVIL (ESP32 DevKit V1)", style="rounded,dashed", color="#64748b", fontsize="13")
        r.node("bat", "Batería 2S 18650\n7.4 V · BMS 2S", fillcolor=C["pot"])
        r.node("buck", "Regulador step-down\nMP1584 → 5 V", fillcolor=C["pot"])
        r.node("esp", "ESP32\n(control 20 Hz,\nmáquina de estados,\nAPI REST, ESP-NOW)", fillcolor=C["proc"], shape="box3d")
        r.node("mag", "Brújula QMC5883L\n(I2C 0x0D)", fillcolor=C["sens"])
        r.node("col", "Color TCS34725\n(I2C 0x29)", fillcolor=C["sens"])
        r.node("us", "Ultrasonido HC-SR04", fillcolor=C["sens"])
        r.node("ir", "3× TCRT5000\n(línea guía)", fillcolor=C["sens"])
        r.node("vb", "Divisor de batería\n(ADC)", fillcolor=C["sens"])
        r.node("srv", "Servo SG90\n(orienta el sonar)", fillcolor=C["act"])
        r.node("drv", "Puente H TB6612FNG", fillcolor=C["act"])
        r.node("mot", "4× motorreductor TT\n(tracción diferencial)", fillcolor=C["act"])
        r.edge("bat", "buck"); r.edge("bat", "drv", label="VM 7.4 V"); r.edge("buck", "esp", label="5 V")
        for s in ("mag", "col"):
            r.edge(s, "esp", label="I2C")
        r.edge("us", "esp", label="TRIG/ECHO"); r.edge("ir", "esp", label="GPIO"); r.edge("vb", "esp", label="ADC")
        r.edge("esp", "srv", label="PWM 50 Hz"); r.edge("esp", "drv", label="PWM 20 kHz"); r.edge("drv", "mot")
    d.node("rc", "Control remoto ESP32\n(joystick + botones)", fillcolor=C["com"])
    d.node("app", "App Streamlit\n(dashboard, voz)", fillcolor=C["com"])
    d.node("jar", "Chatbot J.A.R.V.I.S.\n(Claude API / reglas)", fillcolor=C["com"])
    d.node("user", "Usuario", shape="ellipse", fillcolor=C["sw"])
    d.edge("rc", "esp", label="ESP-NOW\n20 Hz", dir="forward", color="#7c3aed")
    d.edge("app", "esp", label="Wi-Fi SoftAP\nHTTP/JSON", dir="both", color="#7c3aed")
    d.edge("jar", "app", dir="both"); d.edge("user", "app", label="voz / clic"); d.edge("user", "rc")
    save(d, "arquitectura_general")


# ---------------------------------------------------------------------------- bloques por módulo
MODULOS = {
    "bloque_potencia": ("Módulo de potencia", [
        ("Cargador 2S\n(USB-C)", "pot"), ("2× 18650\n3.7 V 2600 mAh", "pot"), ("BMS 2S\n(protección)", "pot"),
        ("Fusible 3 A +\ninterruptor", "pot"), ("Bus 7.4 V", "pot")],
        [("Bus 7.4 V", "TB6612 VM\n(motores)"), ("Bus 7.4 V", "MP1584\n7.4→5 V 3 A"),
         ("MP1584\n7.4→5 V 3 A", "ESP32 VIN\n(LDO 3.3 V)"), ("MP1584\n7.4→5 V 3 A", "Servo, HC-SR04,\nTCRT5000"),
         ("ESP32 VIN\n(LDO 3.3 V)", "3.3 V: I2C,\nTB6612 VCC"), ("Bus 7.4 V", "Divisor 100k/33k\n→ GPIO36")]),
    "bloque_locomocion": ("Módulo de locomoción", [
        ("Referencia\n(manual / autónomo)", "sw"), ("Mezcla diferencial\nv ± w", "proc"), ("LEDC PWM\n20 kHz, 10 bit", "proc"),
        ("TB6612FNG\n(2 canales)", "act"), ("Motores TT\nizq. / der.", "act"), ("Movimiento\ndel robot", "sw")],
        [("Movimiento\ndel robot", "Brújula\n(realimentación de rumbo)"),
         ("Brújula\n(realimentación de rumbo)", "Mezcla diferencial\nv ± w")]),
    "bloque_brujula": ("Módulo de brújula digital", [
        ("Campo magnético\nterrestre", "sw"), ("QMC5883L\nOSR 512, 50 Hz", "sens"), ("I2C 400 kHz", "com"),
        ("Corrección hard/soft-iron\n(offsets en NVS)", "proc"), ("Filtro vectorial\npaso-bajo", "proc"),
        ("atan2 + declinación\n−7.8°", "proc"), ("Rumbo 0–360°", "sw")],
        [("Rumbo 0–360°", "Control P de rumbo\n(error vs deseado)"), ("Rumbo 0–360°", "Telemetría\n/api/state")]),
    "bloque_color": ("Módulo de detección de color", [
        ("Superficie\nde la pista", "sw"), ("LED blanco\n+ faldón", "act"), ("TCS34725\n50 ms, ganancia 4×", "sens"),
        ("Cromaticidad r,g,b\n+ log(brillo)", "proc"), ("Vecino más cercano\n(6 referencias)", "proc"),
        ("Anti-rebote\n3 lecturas", "proc"), ("Color / cambio\nde sección", "sw")],
        [("Color / cambio\nde sección", "Polaridad línea\n(sección negra)"), ("Color / cambio\nde sección", "Evento a la app\ny J.A.R.V.I.S.")]),
    "bloque_obstaculos": ("Módulo de detección y evasión de obstáculos", [
        ("Obstáculo", "sw"), ("HC-SR04\n(divisor ECHO 5→3.3 V)", "sens"), ("pulseIn + mediana\nde 3 muestras", "proc"),
        ("d < 30 cm", "proc"), ("Servo SG90 escanea\nizq. 160° / der. 20°", "act"),
        ("Elige lado libre\ny rodea en arco", "proc"), ("Retoma la línea\nen el sentido original", "sw")],
        []),
    "bloque_linea": ("Módulo de seguimiento de pista", [
        ("Línea guía\n19 mm", "sw"), ("3× TCRT5000\n(comparador LM393)", "sens"), ("Error lateral\n−1 … +1", "proc"),
        ("Control P\nw = 0.45·e", "proc"), ("Brújula mantiene\nrumbo en huecos", "proc"), ("Búsqueda en\nespiral", "proc")],
        []),
    "bloque_comunicaciones": ("Módulo de comunicaciones", [
        ("ESP32 Wi-Fi\nAP+STA canal 1", "com"), ("SoftAP ROBOT-ESP32\n192.168.4.1", "com"),
        ("WebServer :80\nAPI REST/JSON", "proc"), ("App Streamlit\n(polling 2–4 Hz)", "sw")],
        [("ESP32 Wi-Fi\nAP+STA canal 1", "ESP-NOW\n(paquete 6 B, 20 Hz)"), ("ESP-NOW\n(paquete 6 B, 20 Hz)", "Control remoto\nESP32")]),
    "bloque_app": ("App Streamlit + chatbot", [
        ("Micrófono\n(st.audio_input)", "sw"), ("Reconocimiento\nde voz es-CO", "proc"), ("Intérprete de\ncomandos", "proc"),
        ("RobotClient\nHTTP", "com"), ("ESP32", "proc")],
        [("ESP32", "Dashboard en vivo\n(brújula polar, sensores)"), ("Dashboard en vivo\n(brújula polar, sensores)", "J.A.R.V.I.S.\n(Claude + telemetría)"),
         ("Botones\nArriba/Abajo/Der/Izq", "RobotClient\nHTTP")]),
    "bloque_control_remoto": ("Control remoto propio (ESP32)", [
        ("Joystick KY-023\n+ 2 pulsadores", "sens"), ("ADC 12 bit +\nzona muerta", "proc"), ("Paquete ESP-NOW\nx, y, botones", "com"),
        ("Robot: mezcla\ndiferencial", "proc"), ("Motores", "act")], []),
}


def bloques():
    for name, (title, chain, extra) in MODULOS.items():
        d = g(name)
        d.attr(label=title, labelloc="t", fontsize="14")
        ids = {}
        for i, (label, kind) in enumerate(chain):
            ids[label] = f"n{i}"
            d.node(f"n{i}", label, fillcolor=C[kind])
            if i:
                d.edge(f"n{i-1}", f"n{i}")
        k = len(chain)
        for a, b in extra:
            for lab in (a, b):
                if lab not in ids:
                    ids[lab] = f"n{k}"; k += 1
                    d.node(ids[lab], lab, fillcolor=C["sw"])
            d.edge(ids[a], ids[b], style="dashed")
        save(d, name)


# ---------------------------------------------------------------------------- máquina de estados
def maquina_estados():
    d = g("estados", "TB")
    d.attr("node", fillcolor=C["proc"])
    for n in ["MANUAL", "SEGUIR", "FRENO", "ESCANEO_IZQ", "ESCANEO_DER", "GIRO_EVASION", "AVANCE_LATERAL",
              "RODEO", "CRUZAR", "ALINEAR", "REORIENTAR", "PAUSA", "CALIBRANDO"]:
        d.node(n, fillcolor=C["sens"] if n == "SEGUIR" else C["act"] if n in ("MANUAL", "CALIBRANDO") else C["proc"])
    e = d.edge
    e("MANUAL", "SEGUIR", "/api/mode?m=auto\no botón del control"); e("SEGUIR", "MANUAL", "comando manual / stop")
    e("SEGUIR", "FRENO", "d < 30 cm"); e("FRENO", "ESCANEO_IZQ", "250 ms"); e("ESCANEO_IZQ", "ESCANEO_DER", "mide izq.")
    e("ESCANEO_DER", "GIRO_EVASION", "lado = más libre"); e("GIRO_EVASION", "AVANCE_LATERAL", "rumbo h0 ± 60°")
    e("AVANCE_LATERAL", "RODEO", "700 ms"); e("RODEO", "FRENO", "otro obstáculo")
    e("RODEO", "CRUZAR", "detecta línea"); e("RODEO", "SEGUIR", "timeout 5 s /\nnav = rumbo")
    e("CRUZAR", "ALINEAR", "300 ms"); e("ALINEAR", "SEGUIR", "sensor central\nsobre la línea")
    e("SEGUIR", "REORIENTAR", "línea en sentido\ncontrario"); e("REORIENTAR", "SEGUIR", "rumbo = h0")
    e("SEGUIR", "PAUSA", "pausa"); e("PAUSA", "SEGUIR", "reanudar")
    e("MANUAL", "CALIBRANDO", "calibrar brújula"); e("CALIBRANDO", "MANUAL", "8 s")
    save(d, "maquina_estados")


# ---------------------------------------------------------------------------- esquemático
def esquematico():
    # ----------------------------------------------------------- etapa de potencia (schemdraw)
    with schemdraw.Drawing(file=os.path.join(OUT, "esquematico.png"), dpi=170, show=False) as dw:
        dw.config(fontsize=11, unit=2.5)
        dw.add(elm.Ground())
        dw.add(elm.BatteryCell().up().reverse().label("BT1  2S 18650\n7.4 V nominal", loc="top", ofst=0.3))
        dw.add(elm.Line().up().length(0.8))
        dw.add(elm.Switch().right().label("SW1", ofst=0.3))
        dw.add(elm.Fuse().right().label("F1 3 A", ofst=0.3))
        a = dw.add(elm.Dot().label("+7.4 V", loc="top"))
        dw.add(elm.Line().right().length(3.5))
        b = dw.add(elm.Dot())
        dw.add(elm.Line().right().length(1.5))
        buck = dw.add(elm.Ic(pins=[elm.IcPin("VIN", side="left"), elm.IcPin("GND", side="bot"),
                                   elm.IcPin("VOUT", side="right")], size=(3, 2)).anchor("VIN"))
        dw.add(elm.Label().at((buck.VIN[0] + 1.5, buck.VIN[1] + 1.6)).label("U2 MP1584 (buck 5 V, 3 A)"))
        dw.add(elm.Ground().at(buck.GND))
        dw.add(elm.Line().at(buck.VOUT).right().length(1.5))
        v5 = dw.add(elm.Dot().label("+5 V → ESP32 VIN,\nservo, HC-SR04", loc="right"))
        dw.add(elm.Capacitor().at(v5.center).down().label("C2 470 µF", loc="bot"))
        dw.add(elm.Ground())
        dw.add(elm.Capacitor().at(a.center).down().label("C1 470 µF", loc="bot"))
        dw.add(elm.Ground())
        dw.add(elm.Line().at(b.center).down().length(2.0))
        dw.add(elm.Tag().down().label("VM", loc="center", fontsize=9))
        dw.add(elm.Label().at((b.center[0] + 0.3, b.center[1] - 3.6)).label("→ TB6612 VM", halign="left"))
        # divisores (fila inferior)
        t = dw.add(elm.Tag().left().at((0, -6.5)).label("+7.4 V", fontsize=10))
        dw.add(elm.Resistor().at((0, -6.5)).right().label("R1 100 kΩ", ofst=0.3))
        n1 = dw.add(elm.Dot().label("VBAT → GPIO36 (≤2.1 V)", loc="right"))
        dw.add(elm.Resistor().down().label("R2 33 kΩ", loc="bot"))
        dw.add(elm.Ground())
        dw.add(elm.Tag().left().at((11, -6.5)).label("ECHO 5 V", fontsize=10))
        dw.add(elm.Resistor().at((11, -6.5)).right().label("R3 1 kΩ", ofst=0.3))
        n2 = dw.add(elm.Dot().label("→ GPIO19 (3.3 V)", loc="right"))
        dw.add(elm.Resistor().down().label("R4 2 kΩ", loc="bot"))
        dw.add(elm.Ground())

    # ----------------------------------------------------------- conexiones por nets (matplotlib)
    NET_COL = {"+5V": "#dc2626", "+7.4V": "#9f1239", "+3V3": "#ea580c", "GND": "#111827", "SDA": "#2563eb",
               "SCL": "#7c3aed"}

    def block(ax, x, y, title, pins, side="left", w=2.6, color="#f8fafc"):
        h = 0.55 * len(pins) + 0.5
        ax.add_patch(Rectangle((x, y - h), w, h, fc=color, ec="k", lw=1.4))
        ax.text(x + w / 2, y + 0.18, title, ha="center", va="bottom", fontsize=10, weight="bold")
        for i, (pin, net) in enumerate(pins):
            py = y - 0.5 - 0.55 * i
            col = NET_COL.get(net, "#0f766e")
            if not pin:
                continue
            if side == "left":
                ax.plot([x - 0.9, x], [py, py], color="k", lw=1)
                ax.text(x + 0.12, py, pin, va="center", ha="left", fontsize=8)
                ax.text(x - 0.95, py, net, va="center", ha="right", fontsize=8, color=col, weight="bold",
                        bbox=dict(boxstyle="larrow,pad=0.2", fc="white", ec=col, lw=0.8))
            else:
                ax.plot([x + w, x + w + 0.9], [py, py], color="k", lw=1)
                ax.text(x + w - 0.12, py, pin, va="center", ha="right", fontsize=8)
                ax.text(x + w + 0.95, py, net, va="center", ha="left", fontsize=8, color=col, weight="bold",
                        bbox=dict(boxstyle="rarrow,pad=0.2", fc="white", ec=col, lw=0.8))

    fig, ax = plt.subplots(figsize=(16, 11))
    left = [("GPIO25", "PWMA"), ("GPIO26", "AIN1"), ("GPIO27", "AIN2"), ("GPIO14", "PWMB"), ("GPIO33", "BIN1"),
            ("GPIO32", "BIN2"), ("GPIO13", "STBY"), ("GPIO36 (VP)", "VBAT"), ("GPIO34", "IR_L"),
            ("GPIO35", "IR_C"), ("GPIO39 (VN)", "IR_R")]
    right = [("GPIO21", "SDA"), ("GPIO22", "SCL"), ("GPIO4", "LED_COLOR"), ("GPIO18", "TRIG"), ("GPIO19", "ECHO_3V3"),
             ("GPIO23", "SERVO"), ("GPIO2", "LED_ESTADO"), ("VIN", "+5V"), ("3V3", "+3V3"), ("GND", "GND")]
    block(ax, 7, 10, "", right + [("", "")], "right", w=3.2, color="#dbeafe")
    block(ax, 7, 10, "U1 · ESP32 DevKit V1", left, "left", w=3.2, color="#dbeafe")
    block(ax, 1.5, 10, "U3 · TB6612FNG", [("PWMA", "PWMA"), ("AIN1", "AIN1"), ("AIN2", "AIN2"), ("PWMB", "PWMB"),
          ("BIN1", "BIN1"), ("BIN2", "BIN2"), ("STBY", "STBY"), ("VCC", "+3V3"), ("VM", "+7.4V"), ("GND", "GND")],
          "left", color="#fef3c7")
    ax.text(1.5, 3.35, "AO1/AO2 → M1+M3 (izq.)\nBO1/BO2 → M2+M4 (der.)\n100 nF en cada motor", fontsize=8)
    block(ax, 15.5, 10, "U4 · GY-271 QMC5883L", [("VCC", "+3V3"), ("GND", "GND"), ("SDA", "SDA"), ("SCL", "SCL")],
          "left", color="#dcfce7")
    block(ax, 15.5, 6.8, "U5 · TCS34725", [("VIN", "+3V3"), ("GND", "GND"), ("SDA", "SDA"), ("SCL", "SCL"),
          ("LED", "LED_COLOR")], "left", color="#dcfce7")
    block(ax, 15.5, 3.0, "U6 · HC-SR04", [("VCC", "+5V"), ("TRIG", "TRIG"), ("ECHO", "ECHO (R3/R4)"), ("GND", "GND")],
          "left", color="#dcfce7")
    block(ax, 8.5, 2.5, "U7 · 3× TCRT5000", [("VCC", "+3V3"), ("GND", "GND"), ("D0 izq.", "IR_L"), ("D0 centro", "IR_C"),
          ("D0 der.", "IR_R")], "left", color="#dcfce7")
    block(ax, 1.5, 2.5, "M5 · Servo SG90", [("SIG", "SERVO"), ("+", "+5V"), ("−", "GND")], "left", color="#fef3c7")
    ax.text(15.5, 10.9, "I2C 400 kHz · pull-ups 4.7 kΩ en los módulos", fontsize=8, color="#2563eb")
    ax.text(0, -1.4, "Nets con el mismo nombre están conectadas. ECHO del HC-SR04 (5 V) pasa por el divisor R3/R4 "
            "antes de GPIO19. GPIO34-39 son solo entrada. Se evitan GPIO0/12/15 (pines de arranque).", fontsize=9)
    ax.set_xlim(-1.5, 20); ax.set_ylim(-1.8, 11.5); ax.axis("off")
    ax.set_title("Esquema de conexiones del sistema electrónico (nets)", fontsize=14, weight="bold")
    fig.savefig(os.path.join(OUT, "esquematico_esp32.png"), dpi=170, bbox_inches="tight"); plt.close(fig)


# ---------------------------------------------------------------------------- planos acotados
def dim(ax, p1, p2, off, text, vertical=False):
    (x1, y1), (x2, y2) = p1, p2
    if vertical:
        xo = x1 + off
        ax.annotate("", (xo, y1), (xo, y2), arrowprops=dict(arrowstyle="<->", lw=0.8))
        ax.plot([x1, xo], [y1, y1], lw=0.4, color="k"); ax.plot([x2, xo], [y2, y2], lw=0.4, color="k")
        ax.text(xo + 2, (y1 + y2) / 2, text, rotation=90, va="center", ha="left", fontsize=8)
    else:
        yo = y1 + off
        ax.annotate("", (x1, yo), (x2, yo), arrowprops=dict(arrowstyle="<->", lw=0.8))
        ax.plot([x1, x1], [y1, yo], lw=0.4, color="k"); ax.plot([x2, x2], [y2, yo], lw=0.4, color="k")
        ax.text((x1 + x2) / 2, yo + 2, text, ha="center", va="bottom", fontsize=8)


def placa(ax, sup: bool):
    L, W, R = 200, 140, 12
    ax.add_patch(FancyBboxPatch((-L / 2 + R, -W / 2 + R), L - 2 * R, W - 2 * R, boxstyle=f"round,pad={R}",
                                fc="#f5e6c8" if not sup else "#dbeafe", ec="k", lw=1.2))
    holes = [(x, y, 3.4) for x in (-85, 0, 85) for y in (-58, 58)]
    if not sup:
        for sx in (-1, 1):
            for sy in (-1, 1):
                holes += [(sx * 60 - sx * 18, sy * 52, 3.4), (sx * 60 - sx * 36, sy * 52, 3.4)]
        holes += [(80, -15, 3.4), (80, 15, 3.4)]
        for sx in (-1, 1):
            ax.add_patch(FancyBboxPatch((sx * 30 - 4, -15), 8, 30, boxstyle="round,pad=3", fc="white", ec="k"))
        ax.add_patch(FancyBboxPatch((83, -20), 10, 40, boxstyle="round,pad=2", fc="white", ec="k"))
        for sx in (-1, 1):
            for sy in (-1, 1):
                ax.add_patch(Rectangle((sx * 60 - 32, sy * 52 - 9.5), 64, 19, fc="none", ec="#b45309", ls="--", lw=0.8))
        ax.text(0, 0, "Batería 2S\n77×41", ha="center", va="center", fontsize=7, color="#1d4ed8")
        ax.add_patch(Rectangle((-38.5, -20.5), 77, 41, fc="none", ec="#1d4ed8", ls=":", lw=0.8))
        ax.text(60, 40, "TT (línea punteada)", fontsize=6, color="#b45309", ha="center")
    else:
        for x in (-23.5, 23.5):
            for y in (-11.5, 11.5):
                holes.append((-10 + x, y, 2.8))
        holes += [(80, -14, 2.2), (80, 14, 2.2), (-80, -8, 3.4), (-80, 8, 3.4), (-92, 40, 8)]
        ax.add_patch(Rectangle((80 - 6.3, -11.6), 12.6, 23.2, fc="white", ec="k"))
        ax.add_patch(FancyBboxPatch((35, -17), 10, 34, boxstyle="round,pad=3", fc="white", ec="k"))
        ax.add_patch(Rectangle((-98.5, -44.25), 13, 8.5, fc="white", ec="k"))
        ax.add_patch(Rectangle((-37.5, -14), 55, 28, fc="none", ec="#1d4ed8", ls=":", lw=0.8))
        ax.text(-10, 0, "ESP32", ha="center", va="center", fontsize=7, color="#1d4ed8")
        ax.text(80, -20, "SG90", ha="center", fontsize=6)
        ax.text(-80, 14, "mástil\nbrújula", ha="center", fontsize=6)
    for x, y, d in holes:
        ax.add_patch(Circle((x, y), d / 2, fc="white", ec="k", lw=0.8))
    dim(ax, (-100, 70), (100, 70), 12, "200")
    dim(ax, (100, -70), (100, 70), 12, "140", vertical=True)
    dim(ax, (-85, -70), (85, -70), -14, "170 (separadores M3)")
    dim(ax, (-100, -58), (-100, 58), -14, "116", vertical=True)
    ax.text(-95, 62, "R12", fontsize=7)
    ax.set_xlim(-125, 130); ax.set_ylim(-100, 100); ax.set_aspect("equal"); ax.axis("off")


def planos():
    for sup, name, title in ((False, "plano_placa_base", "PLACA BASE – MDF 3 mm (corte láser)"),
                             (True, "plano_placa_superior", "PLACA SUPERIOR – acrílico 3 mm (corte láser)")):
        fig, ax = plt.subplots(figsize=(9, 7.2))
        placa(ax, sup)
        ax.set_title(title, fontsize=12, weight="bold")
        fig.text(0.98, 0.02, "Cotas en mm · Escala 1:2 (A4) · Tolerancia ±0.2 · Agujeros Ø3.4 = M3",
                 ha="right", fontsize=8)
        fig.savefig(os.path.join(OUT, f"{name}.png"), dpi=200, bbox_inches="tight"); plt.close(fig)

    # vista lateral con alturas
    fig, ax = plt.subplots(figsize=(10, 5))
    zb, T, sep = 32.5 + 11, 3, 45
    zs = zb + T + sep
    for x in (-60, 60):
        ax.add_patch(Circle((x, 32.5), 32.5, fc="#222", ec="k")); ax.add_patch(Circle((x, 32.5), 20, fc="#facc15"))
        ax.add_patch(Rectangle((x - 32, zb - 22.5), 64, 22.5, fc="#fbbf24", ec="k", alpha=0.6))
    ax.add_patch(Rectangle((-100, zb), 200, T, fc="#d6b98c", ec="k"))
    ax.add_patch(Rectangle((-100, zs), 200, T, fc="#93c5fd", ec="k"))
    for x in (-85, 0, 85):
        ax.add_patch(Rectangle((x - 2.5, zb + T), 5, sep, fc="#cbd5e1", ec="k"))
    ax.add_patch(Rectangle((-38.5, zb + T), 77, 20, fc="#3b82f6", ec="k", alpha=0.7)); ax.text(0, zb + 13, "Batería", ha="center", fontsize=7, color="w")
    ax.add_patch(Rectangle((-86, zs + T), 12, 80, fc="#f97316", ec="k")); ax.add_patch(Rectangle((-87, zs + T + 80), 14, 3, fc="#7e22ce"))
    ax.text(-70, zs + 60, "Mástil PLA 80 mm\nGY-271 a 125 mm\nde los motores", fontsize=7)
    ax.add_patch(Rectangle((-37.5, zs + T), 55, 8, fc="#111"))
    ax.add_patch(Rectangle((74, zs + T - 15), 12, 29, fc="#1d4ed8", ec="k"))
    ax.add_patch(Rectangle((84, zs + T + 14), 4, 20, fc="#0ea5e9", ec="k"))
    ax.add_patch(Rectangle((88, zs + T + 17), 12, 14, fc="#d1d5db", ec="k")); ax.text(102, zs + 20, "HC-SR04", fontsize=7)
    ax.add_patch(Rectangle((74, 8), 20, 3, fc="#f97316", ec="k")); ax.text(102, 14, "TCRT5000 a 8 mm", fontsize=7)
    ax.add_patch(Rectangle((58, 5), 16, 3, fc="#f97316", ec="k")); ax.text(102, 2, "TCS34725 a 5 mm", fontsize=7)
    ax.plot([-130, 140], [0, 0], color="k", lw=1.5)
    dim(ax, (-60, 0), (60, 0), -18, "Distancia entre ejes 120")
    dim(ax, (-100, 0), (-100, zb), -20, f"{zb:.1f}", vertical=True)
    dim(ax, (-100, 0), (-100, zs + T), -34, f"{zs + T:.1f}", vertical=True)
    ax.text(-60, 72, "Ruedas Ø65", ha="center", fontsize=7)
    ax.set_xlim(-150, 160); ax.set_ylim(-35, 225); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("VISTA LATERAL – alturas de montaje (mm)", fontsize=12, weight="bold")
    fig.savefig(os.path.join(OUT, "plano_lateral.png"), dpi=200, bbox_inches="tight"); plt.close(fig)


# ---------------------------------------------------------------------------- pistas y simulación
def pistas_y_simulacion():
    from simulator import LEVELS, SimRobot
    hexc = {"negro": "#111", "blanco": "#e5e5e5", "rojo": "#d62828", "amarillo": "#f6c90e", "verde": "#2a9d3f",
            "azul": "#1d4ed8"}
    fig, axs = plt.subplots(1, 3, figsize=(15, 5.2))
    results = []
    for lvl, ax in zip((1, 2, 3), axs):
        r = SimRobot(lvl)
        r.handle("/api/mode", {"m": ["auto"]})
        trail = []
        n = len(r.world.track); last = 0; prog = 0
        for k in range(int(90 / 0.05)):
            r.step()
            i, _ = r.world.nearest(r.x, r.y)
            prog += (i - last + n // 2) % n - n // 2; last = i
            if k % 2 == 0:
                trail.append((r.x, r.y))
            if prog >= n:          # una vuelta completa
                break
        w = r.world
        for i in range(0, n, 2):
            a, b = w.track[i], w.track[(i + 2) % n]
            frac = w.cum[i] / w.length
            cname = w.section_colors[int(frac * len(w.section_colors)) % len(w.section_colors)]
            ax.plot([a[0], b[0]], [a[1], b[1]], color=hexc[cname], lw=9, solid_capstyle="butt")
        ax.plot(*zip(*w.track), color="w", lw=0.6, ls="--")
        for ox, oy, rad in w.obstacles:
            ax.add_patch(Circle((ox, oy), rad, color="#ea580c", zorder=5))
        ax.plot(*zip(*trail), color="#a855f7", lw=1.4, zorder=6, label="trayectoria")
        ax.set_aspect("equal"); ax.set_facecolor("#cfcfcf"); ax.set_xticks([]); ax.set_yticks([])
        cfg = LEVELS[lvl]
        ax.set_title(f"Nivel {lvl}: {cfg['obstacles']} obstáculos · {len(cfg['colors'])} colores\n"
                     f"1 vuelta en {r.t:.0f} s · evitados {r.obstacles_avoided} · colisiones {r.collisions}",
                     fontsize=10)
        results.append((lvl, r.t, r.obstacles_avoided, r.collisions, r.color_changes, r.distance_m))
    axs[0].legend(loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.subplots_adjust(top=0.86)
    fig.savefig(os.path.join(OUT, "simulacion_niveles.png"), dpi=170); plt.close(fig)
    return results


if __name__ == "__main__":
    arquitectura(); print("arquitectura")
    bloques(); print("bloques")
    maquina_estados(); print("estados")
    esquematico(); print("esquemático")
    planos(); print("planos")
    for row in pistas_y_simulacion():
        print("nivel %d: t=%.0f s evitados=%d colisiones=%d cambios_color=%d dist=%.1f m" % row)
