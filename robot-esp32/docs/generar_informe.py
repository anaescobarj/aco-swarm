"""Genera el informe del Primer Entregable en PDF.

    python docs/generar_diagramas.py   # primero las figuras
    python docs/generar_informe.py     # -> docs/Informe_Primer_Entregable.pdf
"""
from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
CAD = os.path.join(HERE, "..", "hardware", "cad")
OUT = os.path.join(HERE, "Informe_Primer_Entregable.pdf")
REPO = "https://github.com/anaescobarj/aco-swarm/tree/claude/hagamos-esto-buyx1l/robot-esp32"
AUTORA = "Ana Sofía Escobar Jaramillo"

# ------------------------------------------------------------------------------- fuentes y estilos
FD = "/usr/share/fonts/truetype/dejavu/"
if os.path.exists(FD + "DejaVuSans.ttf"):
    pdfmetrics.registerFont(TTFont("DV", FD + "DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DVB", FD + "DejaVuSans-Bold.ttf"))
    _it = next((FD + f for f in ("DejaVuSans-Oblique.ttf", "DejaVuSerif-Italic.ttf", "DejaVuSans.ttf")
                if os.path.exists(FD + f)))
    pdfmetrics.registerFont(TTFont("DVI", _it))
    pdfmetrics.registerFont(TTFont("DVM", FD + "DejaVuSansMono.ttf"))
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("DV", normal="DV", bold="DVB", italic="DVI", boldItalic="DVB")
    F, FB, FM = "DV", "DVB", "DVM"
else:
    F, FB, FM = "Helvetica", "Helvetica-Bold", "Courier"

ss = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=ss["Normal"], fontName=F, fontSize=9.6, leading=13.6, alignment=TA_JUSTIFY,
                      spaceAfter=5)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10.5, alignment=0)
CAP = ParagraphStyle("cap", parent=BODY, fontName="DVI" if F == "DV" else F, fontSize=8, alignment=TA_CENTER,
                     textColor=colors.HexColor("#475569"), spaceBefore=2, spaceAfter=10)
H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName=FB, fontSize=15, textColor=colors.HexColor("#0f3d6e"), keepWithNext=1,
                    spaceBefore=6, spaceAfter=8)
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName=FB, fontSize=11.5, textColor=colors.HexColor("#1d4ed8"), keepWithNext=1,
                    spaceBefore=8, spaceAfter=4)
CODE = ParagraphStyle("code", parent=BODY, fontName=FM, fontSize=7.6, leading=9.6, alignment=0,
                      backColor=colors.HexColor("#f1f5f9"), borderPadding=4, spaceBefore=4, spaceAfter=8)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=7.8, leading=9.8, alignment=0, spaceAfter=0)
CELLB = ParagraphStyle("cellb", parent=CELL, fontName=FB, textColor=colors.white)

fig_n = [0]
tab_n = [0]


class Doc(SimpleDocTemplate):
    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and f.style.name in ("h1", "h2"):
            lvl = 0 if f.style.name == "h1" else 1
            key = f"h{id(f)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(f.getPlainText(), key, level=lvl)
            self.notify("TOCEntry", (lvl, f.getPlainText(), self.page, key))


def p(t, st=BODY):
    return Paragraph(t, st)


def h1(t):
    return p(t, H1)


def h2(t):
    return p(t, H2)


def bullets(items):
    return ListFlowable([ListItem(p(i), leftIndent=12, value="•") for i in items], bulletType="bullet",
                        start="•", leftIndent=12, bulletFontSize=8)


def fig(path, caption, w=16):
    from reportlab.lib.utils import ImageReader
    if not os.path.exists(path):
        return p(f"[figura no encontrada: {os.path.basename(path)}]")
    iw, ih = ImageReader(path).getSize()
    width = w * cm
    height = width * ih / iw
    if height > 21 * cm:
        height = 21 * cm
        width = height * iw / ih
    fig_n[0] += 1
    return KeepTogether([Image(path, width=width, height=height),
                         p(f"Figura {fig_n[0]}. {caption}", CAP)])


def table(rows, widths, caption=None, header=True):
    data = [[p(str(c), CELLB if (header and i == 0) else CELL) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f3d6e")))
    t.setStyle(TableStyle(style))
    out = []
    if caption:
        tab_n[0] += 1
        out.append(p(f"<b>Tabla {tab_n[0]}.</b> {caption}", ParagraphStyle("tc", parent=CAP, alignment=0,
                                                                         spaceAfter=3)))
    out.append(t)
    out.append(Spacer(1, 8))
    return [KeepTogether(out)] if len(rows) < 18 else out


def on_page(c, d):
    c.saveState()
    c.setFont(F, 7.5)
    c.setFillColor(colors.HexColor("#64748b"))
    if d.page > 1:
        c.drawString(2 * cm, 1.2 * cm, "Primer Entregable · Proyecto Final · Robot móvil ESP32")
        c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Página {d.page}")
    c.restoreState()


# ------------------------------------------------------------------------------- contenido
def portada():
    t = ParagraphStyle("t", parent=H1, fontSize=24, leading=30, alignment=TA_CENTER)
    s = ParagraphStyle("s", parent=BODY, fontSize=12.5, leading=17, alignment=TA_CENTER)
    out = [Spacer(1, 2.2 * cm), p("PRIMER ENTREGABLE · PROYECTO FINAL", ParagraphStyle(
        "k", parent=s, textColor=colors.HexColor("#1d4ed8"), fontName=FB)),
        Spacer(1, 0.4 * cm),
        p("Robot móvil autónomo basado en ESP32 con brújula digital, detección de colores y de obstáculos, "
          "app Streamlit y chatbot J.A.R.V.I.S.", t), Spacer(1, 0.6 * cm),
        p("Objetivos específicos – Entrega Corte 2", s), Spacer(1, 0.6 * cm)]
    if os.path.exists(os.path.join(CAD, "render_iso.png")):
        out.append(Image(os.path.join(CAD, "render_iso.png"), width=11 * cm, height=8.25 * cm))
    out += [Spacer(1, 0.8 * cm), p(f"<b>{AUTORA}</b>", s), p("Noviembre de 2026", s), Spacer(1, 0.5 * cm),
            p(f"Repositorio: <link href='{REPO}' color='blue'>github.com/anaescobarj/aco-swarm → robot-esp32/</link>",
              ParagraphStyle("r", parent=s, fontSize=9.5)), PageBreak()]
    return out


def indice():
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("t0", fontName=FB, fontSize=10, leading=15, leftIndent=0),
                       ParagraphStyle("t1", fontName=F, fontSize=9, leading=12.5, leftIndent=14)]
    return [p("Contenido", ParagraphStyle("toch", parent=H1)), toc, PageBreak()]


def introduccion():
    return [
        h1("1. Breve introducción"),
        p("Este documento presenta el primer entregable del proyecto final: el diseño de un <b>sistema robótico "
          "móvil basado en ESP32</b> cuya estructura mecánica y electrónica es desarrollada por la estudiante. "
          "El robot opera en dos modos: <b>manual</b>, comandado por voz (arriba, abajo, derecha, izquierda) desde "
          "una aplicación web Streamlit o con un control remoto propio construido con un segundo ESP32; y "
          "<b>autónomo</b>, en el que recorre una pista seccionada por colores, se orienta con una brújula digital, "
          "detecta en tiempo real los cambios de color de la superficie (negro, blanco, rojo, amarillo, verde y "
          "azul) y esquiva obstáculos para luego retomar su trayecto."),
        p("La aplicación Streamlit se comunica de forma inalámbrica con el ESP32 (Wi-Fi) y muestra en tiempo real "
          "la <b>dirección polar actual y la deseada</b>, además de toda la telemetría. Un chatbot estilo "
          "<b>J.A.R.V.I.S.</b> explica el proyecto e interpreta las variables capturadas en tiempo real."),
        p("El informe sigue el orden de los objetivos específicos de la entrega del corte 2: (1) arquitectura, "
          "requerimientos, diagramas de bloques y selección de materiales; (2) diseño mecánico (CAD y planos) y "
          "electrónico (esquemas); (3) construcción de los módulos electrónicos/firmware; y (4) la aplicación "
          "Streamlit con comunicación inalámbrica. Todo el material (firmware, app, simulador, CAD, planos, "
          "generadores de figuras y de este informe) está en el repositorio."),
        h2("1.1 Alcance de esta entrega"),
        p("Se entrega el diseño completo y el software funcional. Como el hardware aún está en ensamble, la lógica "
          "de control se validó con un <b>gemelo digital</b> (simulador) que expone exactamente la misma API HTTP "
          "del firmware y ejecuta la misma máquina de estados sobre las tres pistas de la meta final. El firmware "
          "se verificó sintácticamente; su prueba en la placa física es la primera actividad del siguiente corte "
          "(sección 10)."),
    ]


def objetivos():
    return [
        h1("2. Objetivos"),
        h2("2.1 Objetivo general"),
        p("Diseñar e implementar un sistema robótico móvil basado en ESP32, con estructura mecánica y electrónica "
          "desarrolladas por la estudiante, capaz de operar en modos manual (comandos de voz y control desarrollado "
          "con ESP32) y autónomo, orientarse mediante una brújula digital, comunicarse de forma inalámbrica con una "
          "aplicación móvil/web (Streamlit) que visualiza en tiempo real la dirección polar actual y deseada, "
          "detectar en tiempo real cambios de color de la superficie (negro, blanco, rojo, amarillo, verde y azul) "
          "y obstáculos (esquivándolos y siguiendo con el trayecto), e incorporar un chatbot tipo J.A.R.V.I.S. que "
          "explique el proyecto e indique las variables capturadas en tiempo real."),
        h2("2.2 Objetivos específicos (Corte 2) y dónde se cumplen"),
        table([["#", "Objetivo específico", "Sección / evidencia"],
               ["1", "Crear la arquitectura del robot, analizando requerimientos funcionales y no funcionales, con "
                     "diagramas de bloques por módulo y selección/justificación de materiales.",
                "Sec. 3 y 4 · Fig. arquitectura y 9 diagramas de bloques · Tablas de requerimientos y materiales"],
               ["2", "Diseñar la estructura mecánica y el sistema electrónico (modelos CAD, planos mecánicos y "
                     "esquemas eléctricos).",
                "Sec. 5 y 6 · hardware/cad/chasis.scad, DXF, STL · planos acotados · esquemas"],
               ["3", "Construir los módulos electrónicos que capturan datos, manejan la brújula, detectan obstáculos "
                     "y colores y se conectan con el chatbot en tiempo real.",
                "Sec. 7 · firmware/robot_esp32 (módulos .h) · API /api/state · validación Sec. 9"],
               ["4", "Desarrollar una app Streamlit inalámbrica (Wi-Fi) para control manual y visualización en "
                     "tiempo real de la dirección polar actual y deseada.",
                "Sec. 8 · app/app.py · capturas del dashboard, control por voz y J.A.R.V.I.S."]],
              [0.6, 9.4, 6.0], "Trazabilidad entre objetivos específicos y entregables."),
        h2("2.3 Meta final del proyecto"),
        table([["Nivel", "Obstáculos mínimos", "Colores de la pista", "Pista"],
               ["1", "4", "3", "Curva cerrada tipo «frijol»"],
               ["2", "6", "4", "Estrella de 5 puntas"],
               ["3", "8", "6", "Pista irregular con curvas encadenadas"]],
              [2, 4, 4, 6], "Niveles de dificultad de la meta final (modelados en el simulador)."),
    ]


def requerimientos():
    rf = [["ID", "Requerimiento funcional", "Verificación"],
          ["RF-01", "Moverse adelante, atrás, girar a derecha e izquierda con velocidad regulable.", "Prueba manual"],
          ["RF-02", "Recibir comandos de voz en español (arriba, abajo, derecha, izquierda, detente, modo, rumbo).",
           "Pruebas unitarias del intérprete (15 frases)"],
          ["RF-03", "Recibir comandos de un control remoto propio basado en ESP32 (ESP-NOW).", "Prueba de enlace"],
          ["RF-04", "Medir el rumbo magnético (0–360°) con brújula digital calibrable.", "Comparación con brújula"],
          ["RF-05", "Mantener o alcanzar una dirección polar deseada enviada desde la app.", "Error < 8°"],
          ["RF-06", "Seguir el trayecto de la pista de forma autónoma.", "Simulación niveles 1–3"],
          ["RF-07", "Detectar 6 colores (negro, blanco, rojo, amarillo, verde, azul) y los cambios de sección.",
           "Matriz de confusión en pista"],
          ["RF-08", "Detectar obstáculos frontales (< 30 cm), esquivarlos y retomar el trayecto en el sentido "
                    "original.", "Simulación: 0 colisiones"],
          ["RF-09", "Publicar telemetría en tiempo real (rumbo actual/deseado, distancia, color, línea, motores, "
                    "batería, estado, eventos).", "/api/state"],
          ["RF-10", "Visualizar en la app la dirección polar actual y deseada en tiempo real.", "Dashboard"],
          ["RF-11", "Chatbot J.A.R.V.I.S. que explique el proyecto y las variables en tiempo real.", "Pestaña chat"],
          ["RF-12", "Cambiar entre modo manual y autónomo; pausa y parada de emergencia.", "App / control"],
          ["RF-13", "Calibrar la brújula y las referencias de color desde la app.", "Pestaña calibración"]]
    rnf = [["ID", "Requerimiento no funcional", "Criterio"],
           ["RNF-01", "Latencia de control", "Lazo de control a 20 Hz; comando app→motor < 150 ms"],
           ["RNF-02", "Refresco de la visualización", "2–4 Hz en el dashboard"],
           ["RNF-03", "Seguridad", "Detención automática si no llegan comandos (600 ms app / 300 ms ESP-NOW); "
                                   "bloqueo de avance a < 12 cm en manual; fusible 3 A; BMS"],
           ["RNF-04", "Autonomía energética", "≥ 45 min de operación continua (estimado 1.5 h)"],
           ["RNF-05", "Alcance inalámbrico", "≥ 15 m en interiores (Wi-Fi y ESP-NOW)"],
           ["RNF-06", "Dimensiones y peso", "≤ 22 × 20 × 18 cm; ≤ 1 kg"],
           ["RNF-07", "Mantenibilidad", "Firmware modular (un archivo por módulo), parámetros en config.h, "
                                        "piezas paramétricas en CAD"],
           ["RNF-08", "Usabilidad", "Interfaz en español; comandos por voz; funciona en celular y PC"],
           ["RNF-09", "Costo", "≤ 450.000 COP en componentes"],
           ["RNF-10", "Robustez del magnetómetro", "Montaje a > 10 cm de motores y batería; calibración en NVS"]]
    return [h1("3. Requerimientos del sistema"),
            p("Los requerimientos se derivan del objetivo general y de la meta final (tres niveles de pista). "
              "Cada uno tiene un criterio de verificación que se reutiliza en el plan de pruebas."),
            *table(rf, [1.5, 10.5, 4], "Requerimientos funcionales."),
            table(rnf, [1.6, 4.4, 10], "Requerimientos no funcionales.")]


def arquitectura():
    blocks = [("bloque_potencia", "Módulo de potencia: batería 2S protegida, fusible, bus de 7.4 V para motores y "
                                  "regulación a 5 V / 3.3 V para la lógica."),
              ("bloque_locomocion", "Módulo de locomoción: mezcla diferencial, PWM de 20 kHz y realimentación de "
                                    "rumbo con la brújula."),
              ("bloque_brujula", "Módulo de brújula digital: lectura, calibración hard/soft-iron, filtrado y cálculo "
                                 "del rumbo."),
              ("bloque_color", "Módulo de detección de color de la superficie."),
              ("bloque_obstaculos", "Módulo de detección y evasión de obstáculos."),
              ("bloque_linea", "Módulo de seguimiento de la pista."),
              ("bloque_comunicaciones", "Módulo de comunicaciones inalámbricas (Wi-Fi SoftAP + ESP-NOW)."),
              ("bloque_app", "Aplicación Streamlit: voz, control y visualización; chatbot."),
              ("bloque_control_remoto", "Control remoto propio basado en ESP32.")]
    out = [h1("4. Arquitectura del robot"),
           p("La arquitectura es <b>centralizada en un ESP32</b> que ejecuta un lazo de control a 20 Hz "
             "(percepción → decisión → actuación) y, en paralelo, atiende la red: un servidor HTTP con API REST/JSON "
             "para la app y un receptor ESP-NOW para el control remoto. Los sensores se agrupan por bus: I2C "
             "(brújula y color), digital (línea y ultrasonido) y analógico (batería). La potencia se separa en dos "
             "dominios — motores a 7.4 V y lógica a 5 V/3.3 V — para que el ruido de los motores no reinicie el "
             "microcontrolador."),
           fig(os.path.join(IMG, "arquitectura_general.png"), "Arquitectura general del sistema.", 16.5),
           h2("4.1 Diagramas de bloques por módulo")]
    for name, cap in blocks:
        out.append(fig(os.path.join(IMG, f"{name}.png"), cap, 16))
    out += materiales()
    return out


def materiales():
    rows = [["Módulo", "Componente (cant.)", "Alternativas evaluadas", "Justificación de la selección", "COP aprox."],
            ["Control", "ESP32 DevKit V1 (1)", "Arduino UNO + HC-05; ESP8266",
             "Wi-Fi y Bluetooth integrados, ESP-NOW, 2 núcleos a 240 MHz, PWM por hardware (LEDC) en cualquier pin, "
             "2 buses I2C. Exigido por el curso y elimina módulos de radio externos.", "28.000"],
            ["Locomoción", "Puente H TB6612FNG (1)", "L298N; DRV8833",
             "MOSFET: caída de ~0.2 V frente a ~2 V del L298N (más torque y menos calor), 1.2 A continuos / 3.2 A "
             "pico por canal, lógica de 3.3 V, PWM hasta 100 kHz. Más pequeño.", "15.000"],
            ["Locomoción", "Motorreductor TT 1:48 + rueda 65 mm (4)", "N20 con encoder; motores 25GA",
             "Bajo costo, torque suficiente para ~0.9 kg, montaje simple; 4WD da tracción en curvas de la pista. "
             "Velocidad ~0.5 m/s a 6 V.", "40.000"],
            ["Brújula", "GY-271 QMC5883L (1)", "HMC5883L (descontinuado); MPU-9250; BNO055",
             "Magnetómetro 3 ejes de 16 bits, ±8 G, I2C, 3.3 V, barato y disponible. El BNO055 fusiona sensores "
             "pero cuesta 4×; con calibración y montaje en mástil el QMC5883L logra ±2–3°.", "15.000"],
            ["Color", "TCS34725 con LED (1)", "TCS3200 (frecuencia); LDR + LED RGB",
             "Salida digital I2C de 16 bits por canal R,G,B y Clear, filtro IR integrado y LED propio: lecturas "
             "estables bajo distinta iluminación. El TCS3200 requiere medir frecuencias y es más sensible a la luz "
             "ambiente.", "30.000"],
            ["Obstáculos", "HC-SR04 (1) + servo SG90 (1)", "VL53L0X (ToF); IR Sharp GP2Y0A21",
             "Rango 2–400 cm, haz de ~30° adecuado para conos; independiente del color del obstáculo. El servo "
             "permite escanear izquierda/derecha con un solo sensor para elegir el lado libre.", "17.000"],
            ["Pista", "TCRT5000 con comparador (3)", "QTR-8RC; un solo sensor",
             "Tres sensores dan error lateral (−1…+1) para un control proporcional; salida digital ajustable por "
             "potenciómetro.", "12.000"],
            ["Potencia", "2× 18650 2600 mAh + BMS 2S + portapilas", "4× AA; LiPo 2S",
             "7.4 V nominales sin regulador para motores, alta capacidad, recargables y con protección (BMS). "
             "Más seguras y fáciles de conseguir que LiPo.", "45.000"],
            ["Potencia", "Regulador MP1584 (1), fusible 3 A, interruptor, C 470 µF", "LM2596; 7805",
             "Conmutado (~92 % eficiencia) y 3 A: soporta picos de servo + Wi-Fi; el 7805 disiparía ~3 W.", "12.000"],
            ["Estructura", "MDF/acrílico 3 mm corte láser; piezas PLA; separadores M3", "Chasis comercial",
             "Diseño propio (requisito del curso); corte láser preciso y económico; PLA para soportes de sensores "
             "a la altura exacta y mástil no magnético.", "50.000"],
            ["Control remoto", "ESP32 + joystick KY-023 + 2 pulsadores + 18650 + TP4056", "Control RF 2.4 GHz",
             "Reutiliza el ESP32: ESP-NOW tiene latencia < 10 ms y no requiere router.", "50.000"],
            ["Varios", "Resistencias, PCB perforada, cables, borneras", "—", "Divisores de tensión y montaje.", "20.000"],
            ["", "<b>Total estimado</b>", "", "Precios de referencia Colombia 2026 (pueden variar).", "<b>334.000</b>"]]
    power = [["Carga", "Tensión", "Corriente típica", "Pico"],
             ["4 motores TT (2 por canal)", "7.4 V (PWM ≤ 80 %)", "0.8–1.2 A", "≈ 3 A (arranque)"],
             ["ESP32 con Wi-Fi activo", "5 V → 3.3 V", "120 mA", "350 mA (TX)"],
             ["Servo SG90", "5 V", "10 mA (reposo)", "650 mA (bloqueo)"],
             ["HC-SR04 / TCRT5000 ×3 / TCS34725+LED / QMC5883L", "5 V / 3.3 V", "15 / 60 / 22 / 1 mA", "—"],
             ["Total desde la batería (≈)", "7.4 V", "≈ 1.3 A", "≈ 4 A (fusible 3 A lento)"]]
    return [h2("4.2 Selección y justificación de materiales"),
            *table(rows, [1.8, 3.2, 2.9, 6.8, 1.6], "Lista de materiales con alternativas y justificación."),
            h2("4.3 Presupuesto de potencia y autonomía"),
            table(power, [6.5, 3, 3.3, 3.2], "Consumo estimado por carga."),
            p("Autonomía estimada: 2.6 Ah × 0.8 (profundidad de descarga útil) / 1.3 A ≈ <b>1.6 h</b>, por encima "
              "del requerimiento RNF-04. El regulador MP1584 (3 A) cubre con margen el pico de la lógica "
              "(≈ 1.1 A), y el TB6612FNG soporta 1.2 A continuos por canal (≈ 0.5 A por canal en operación).")]


def mecanico():
    return [h1("5. Diseño mecánico"),
            p("El chasis es de <b>diseño propio</b>, modelado paramétricamente en OpenSCAD "
              "(<i>hardware/cad/chasis.scad</i>): todas las cotas son variables, de modo que se regeneran los "
              "planos DXF de corte láser y los STL de impresión 3D con un comando. Tiene dos niveles de 200 × 140 mm "
              "unidos por 6 separadores M3 de 45 mm: el inferior (MDF) aloja motores, batería, puente H y regulador "
              "(centro de gravedad bajo); el superior (acrílico) aloja el ESP32, el servo con el ultrasonido y el "
              "mástil de la brújula."),
            fig(os.path.join(CAD, "render_iso.png"), "Modelo CAD del ensamble (vista isométrica).", 12.5),
            h2("5.1 Decisiones de diseño"),
            bullets([
                "<b>Mástil de brújula de 80 mm en PLA</b>, en la parte trasera: el magnetómetro queda a ~125 mm de los "
                "imanes de los motores y lejos de la batería, reduciendo la distorsión del campo (sin tornillería "
                "metálica cerca).",
                "<b>Sensor de color a 5 mm del piso</b> con faldón que bloquea la luz ambiente y LED propio; "
                "<b>TCRT5000 a 8 mm</b>, distancia óptima del fotodiodo. Ambos en un soporte impreso atornillado "
                "a la ventana frontal de la placa base.",
                "<b>HC-SR04 sobre servo SG90</b> a 110 mm de altura, por encima de las ruedas, para que el haz "
                "no detecte el piso y pueda girar ±70° al escanear.",
                "<b>Distancia entre ejes 120 mm y vía de 172 mm</b>: base ancha estable con giro en el sitio "
                "(tracción diferencial / skid-steer).",
                "<b>Ventanas pasacables</b> en ambas placas y agujeros de fijación para cada módulo.",
            ]),
            fig(os.path.join(IMG, "plano_placa_base.png"), "Plano acotado de la placa base (corte láser).", 13),
            fig(os.path.join(IMG, "plano_placa_superior.png"), "Plano acotado de la placa superior (corte láser).", 13),
            fig(os.path.join(IMG, "plano_lateral.png"), "Vista lateral con alturas de montaje de los sensores.", 14),
            fig(os.path.join(CAD, "render_inferior.png"), "Vista inferior del CAD: motores TT y soporte de sensores "
                                                         "de piso.", 9),
            table([["Pieza", "Material / proceso", "Archivo"],
                   ["Placa base", "MDF 3 mm, corte láser", "hardware/cad/placa_base.dxf"],
                   ["Placa superior", "Acrílico 3 mm, corte láser", "hardware/cad/placa_superior.dxf"],
                   ["Soporte de sensores de piso", "PLA, impresión 3D (0.2 mm, 30 %)", "hardware/cad/soporte_sensores.stl"],
                   ["Mástil de la brújula", "PLA, impresión 3D", "hardware/cad/mastil.stl"],
                   ["Escuadra del ultrasonido", "PLA, impresión 3D", "hardware/cad/soporte_sonar.stl"]],
                  [5, 5.5, 5.5], "Piezas fabricadas.")]


def electronico():
    pins = [["Señal", "GPIO", "Módulo", "Nota"],
            ["PWMA / AIN1 / AIN2", "25 / 26 / 27", "TB6612 canal A (izq.)", "LEDC 20 kHz, 10 bit"],
            ["PWMB / BIN1 / BIN2", "14 / 33 / 32", "TB6612 canal B (der.)", "GPIO12 evitado (arranque)"],
            ["STBY", "13", "TB6612", "Habilita el puente"],
            ["SDA / SCL", "21 / 22", "QMC5883L + TCS34725", "I2C 400 kHz"],
            ["LED color", "4", "TCS34725", "Iluminación constante"],
            ["TRIG / ECHO", "18 / 19", "HC-SR04", "ECHO con divisor 1k/2k"],
            ["SERVO", "23", "SG90", "50 Hz, 14 bit"],
            ["IR izq. / centro / der.", "34 / 35 / 39", "TCRT5000", "Pines solo entrada"],
            ["VBAT", "36", "Divisor 100k/33k", "8.4 V → 2.08 V"],
            ["LED estado", "2", "LED de la placa", "Parpadea en AUTO"]]
    return [h1("6. Diseño electrónico"),
            p("El circuito se divide en la etapa de potencia (Figura siguiente) y las conexiones de señal entre el "
              "ESP32 y cada módulo, representadas con etiquetas de red (nets): pines con el mismo nombre están "
              "conectados. Se evitaron los pines de arranque (GPIO0, 12, 15) y se usaron los pines solo-entrada "
              "34–39 para sensores."),
            fig(os.path.join(IMG, "esquematico.png"), "Esquema eléctrico de la etapa de potencia y divisores de "
                                                     "tensión.", 15),
            fig(os.path.join(IMG, "esquematico_esp32.png"), "Esquema de conexiones del ESP32 con los módulos.", 16.5),
            table(pins, [4, 2.6, 4.4, 5], "Asignación de pines del ESP32."),
            h2("6.1 Cálculos de diseño"),
            bullets([
                "<b>Divisor de batería:</b> V<sub>ADC</sub> = 8.4 V · 33k / (100k + 33k) = 2.08 V (dentro del rango del "
                "ADC con atenuación 11 dB). Corriente de fuga: 8.4 V / 133 kΩ = 63 µA.",
                "<b>Divisor de ECHO:</b> 5 V · 2k / (1k + 2k) = 3.33 V, compatible con la entrada de 3.3 V del ESP32.",
                "<b>PWM de motores:</b> 20 kHz (inaudible) con 10 bits; duty máximo limitado al 80 % "
                "(7.4 V × 0.8 ≈ 5.9 V efectivos) para no exceder los 6 V nominales del motor TT.",
                "<b>Desacople:</b> 470 µF en el bus de motores y en 5 V, más 100 nF en bornes de cada motor para "
                "reducir ruido que afecta al magnetómetro y al ADC.",
                "<b>Servo:</b> periodo 20 ms, pulso 500–2400 µs ↔ 0–180°.",
            ])]


def firmware():
    api = [["Endpoint (GET)", "Parámetros", "Acción"],
           ["/api/state", "—", "Telemetría JSON (rumbo actual y deseado, error, distancia, color, RGBC, línea, "
                               "PWM, batería, modo, estado, eventos)"],
           ["/api/cmd", "move=forward|backward|left|right|stop, speed=0–100, ms", "Movimiento manual por pulsos "
                                                                                  "(se detiene solo al expirar)"],
           ["/api/mode", "m=auto|manual|pausa|reanudar, nav=linea|rumbo", "Cambio de modo"],
           ["/api/heading", "deg=0–359 o rel=±grados", "Dirección polar deseada"],
           ["/api/speed", "v=20–100", "Velocidad del modo autónomo"],
           ["/api/calibrate", "what=compass | what=color&name=…", "Calibración de brújula (giro 8 s) o color"]]
    return [h1("7. Construcción de los módulos (firmware ESP32)"),
            p("El firmware (<i>firmware/robot_esp32/</i>, Arduino-ESP32 core ≥ 3.0) está organizado en un archivo "
              "por módulo, con todos los parámetros en <i>config.h</i>:"),
            table([["Archivo", "Responsabilidad"],
                   ["config.h", "Pines, umbrales, ganancias, red Wi-Fi y ESP-NOW"],
                   ["motors.h", "TB6612FNG: PWM LEDC, mezcla diferencial (arcade), freno activo"],
                   ["compass.h", "QMC5883L: lectura de registros, calibración min/max persistida en NVS, filtro "
                                 "vectorial, declinación"],
                   ["color_sensor.h", "TCS34725: integración 50 ms, clasificación por vecino más cercano en "
                                      "cromaticidad + brillo, anti-rebote, calibración en pista"],
                   ["sensors.h", "HC-SR04 con mediana de 3, servo, TCRT5000 (con inversión de polaridad), batería"],
                   ["robot_esp32.ino", "Lazo de control 20 Hz, máquina de estados, API HTTP, ESP-NOW, eventos"],
                   ["control_remoto.ino", "Control propio: joystick + botones → paquete ESP-NOW a 20 Hz"]],
                  [4, 12], "Estructura del firmware."),
            h2("7.1 Brújula digital"),
            p("El rumbo se calcula como atan2(y, x) del campo corregido (offset hard-iron y escala soft-iron "
              "obtenidos girando el robot 8 s) más la declinación magnética local (−7.8°). Para evitar el salto "
              "359°→0° el filtro paso-bajo se aplica sobre el vector unitario y no sobre el ángulo. El error de "
              "rumbo se normaliza a [−180°, 180°] y alimenta un control proporcional que mantiene la dirección "
              "deseada."),
            h2("7.2 Detección de colores"),
            p("Cada lectura RGBC se normaliza (r, g, b suman 1) para independizar el tono del brillo; el brillo "
              "(log<sub>10</sub> C) separa negro de blanco. El color es el de la referencia más cercana; se "
              "requieren 3 lecturas iguales (~150 ms) para aceptar un <b>cambio de sección</b>, que se cuenta y se "
              "publica como evento a la app y al chatbot. En la sección negra la línea guía es blanca, así que el "
              "color detectado invierte la polaridad de los TCRT5000."),
            h2("7.3 Obstáculos y máquina de estados"),
            p("En modo autónomo, si el ultrasonido mide menos de 30 cm el robot frena, gira el servo para medir a "
              "izquierda y derecha, elige el lado más libre, gira 60° con la brújula, avanza, rodea el obstáculo en "
              "arco y, al encontrar la línea, se alinea pivotando hacia el lado de la evasión, lo que garantiza "
              "retomar la pista <b>en el sentido original</b>. Si se pierde la línea, la brújula mantiene el rumbo y "
              "luego se busca en espiral."),
            fig(os.path.join(IMG, "maquina_estados.png"), "Máquina de estados del firmware.", 12.5),
            h2("7.4 Comunicación y conexión con el chatbot"),
            p("El ESP32 crea la red <b>ROBOT-ESP32</b> (SoftAP, 192.168.4.1) y simultáneamente escucha ESP-NOW en el "
              "mismo canal. La API REST entrega toda la telemetría en un JSON que la app consulta 2–4 veces por "
              "segundo y que se adjunta a cada pregunta hecha a J.A.R.V.I.S.; así el chatbot responde con los "
              "valores en tiempo real."),
            table(api, [3, 6, 7], "API HTTP del robot (idéntica en el ESP32 y en el simulador)."),
            p('Ejemplo de telemetría: <font face="%s" size="7.5">{"mode":"AUTO","state":"SEGUIR","heading":275.0,'
              '"heading_des":274.0,"heading_err":-1.0,"dist_cm":400,"color":"amarillo","rgbc":[1100,1000,420,2100],'
              '"line":[0,1,0],"pwm_l":0.55,"pwm_r":0.55,"batt_v":8.19,"obstacles_avoided":2,'
              '"event":"Obstaculo superado (#2)"}</font>' % FM, SMALL),
            h2("7.5 Seguridad"),
            bullets(["Los comandos manuales son pulsos con duración: si la conexión se cae, el robot se detiene.",
                     "Bloqueo de avance si hay un obstáculo a menos de 12 cm en modo manual.",
                     "Botón STOP en la app y en el control remoto (pasa a manual y frena).",
                     "Fusible de 3 A y BMS 2S contra cortocircuito, sobrecarga y sobredescarga."])]


def app():
    return [h1("8. Aplicación Streamlit y chatbot"),
            p("La app (<i>app/app.py</i>) se conecta por Wi-Fi a la red del robot y usa la API REST. Funciona en el "
              "navegador del computador o del celular. Tiene cuatro pestañas:"),
            bullets(["<b>Dashboard:</b> brújula polar con la dirección actual (azul) y deseada (naranja), métricas de "
                     "rumbo, error, obstáculo, color y batería; historial de rumbo y distancia; sensores de línea, "
                     "motores y registro de eventos. Se actualiza con un fragmento de Streamlit cada 0.5 s.",
                     "<b>Control y voz:</b> botones Arriba/Abajo/Derecha/Izquierda/Detener, selección de modo y de "
                     "navegación, envío de la dirección polar deseada, y comandos de voz grabados con el micrófono, "
                     "reconocidos en español (es-CO) e interpretados por <i>commands.py</i>.",
                     "<b>J.A.R.V.I.S.:</b> chatbot que recibe la telemetría actual en cada pregunta. Usa la API de "
                     "Claude (Anthropic) con respuesta en streaming; sin credenciales o sin internet responde con un "
                     "motor de reglas local, de modo que la demo nunca queda sin chatbot.",
                     "<b>Calibración:</b> calibración de brújula y captura de referencias de color en la pista."]),
            fig(os.path.join(IMG, "app_dashboard.png"), "Dashboard en tiempo real conectado al gemelo digital "
                                                       "(pista del nivel 2).", 16.5),
            fig(os.path.join(IMG, "app_control.png"), "Pestaña de control manual y comandos de voz.", 15),
            fig(os.path.join(IMG, "app_jarvis.png"), "J.A.R.V.I.S. respondiendo con variables en tiempo real.", 15),
            table([["Frase dicha", "Acción enviada al ESP32"],
                   ["«arriba», «adelante», «avanza 2 segundos»", "/api/cmd?move=forward (600 ms o la duración dicha)"],
                   ["«abajo», «atrás», «retrocede»", "/api/cmd?move=backward"],
                   ["«derecha» / «izquierda»", "/api/cmd?move=right | left"],
                   ["«detente», «alto», «para»", "/api/cmd?move=stop"],
                   ["«modo automático», «modo manual»", "/api/mode?m=auto | manual"],
                   ["«rumbo 90», «oriéntate al sur»", "/api/heading?deg=90 | 180"],
                   ["«gira 45 grados a la derecha»", "/api/heading?rel=45"]],
                  [7, 9], "Gramática de comandos de voz.")]


def validacion():
    return [h1("9. Validación"),
            h2("9.1 Gemelo digital"),
            p("<i>app/simulator.py</i> implementa la misma API y la misma máquina de estados del firmware con un "
              "modelo cinemático de tracción diferencial, brújula con ruido, ultrasonido con haz de ±15°, tres "
              "sensores de línea, sensor de color por sección y obstáculos (conos de 5 cm) sobre la línea. Sirvió "
              "para ajustar la estrategia de evasión: las primeras versiones perdían la pista o la retomaban en "
              "sentido contrario en las curvas de la estrella; la versión final (rodeo en arco + cruce + alineación "
              "hacia el lado de la evasión) completa las tres pistas."),
            fig(os.path.join(IMG, "simulacion_niveles.png"), "Una vuelta autónoma en cada nivel de la meta final; "
                                                            "en morado la trayectoria del robot.", 17),
            table([["Nivel", "Obstáculos", "Colores", "Tiempo de vuelta", "Esquivados", "Colisiones", "Recorrido"],
                   ["1", "4", "3", "45 s", "4", "0", "10.0 m"],
                   ["2", "6", "4", "58 s", "6", "0", "12.3 m"],
                   ["3", "8", "6", "64 s", "8", "0", "13.0 m"]],
                  [1.4, 2, 1.8, 2.8, 2.4, 2.2, 2.4], "Resultados en simulación (se reproducen con "
                                                     "docs/generar_diagramas.py)."),
            h2("9.2 Pruebas automáticas"),
            p("<i>app/tests/</i> contiene 22 pruebas (pytest): 17 del intérprete de voz y 5 del simulador "
              "(una vuelta sin colisiones por nivel, parada automática del modo manual y recorrido completo por la "
              "API HTTP con el mismo cliente que usa la app). Todas pasan. El firmware se compila en verificación de "
              "sintaxis con cabeceras simuladas de Arduino."),
            h2("9.3 Plan de pruebas físicas (siguiente corte)"),
            table([["Prueba", "Procedimiento", "Criterio de aceptación"],
                   ["Brújula", "Calibrar; comparar con brújula del celular en 8 rumbos", "Error ≤ 5°"],
                   ["Rumbo deseado", "Enviar 0°, 90°, 180°, 270° desde la app en modo rumbo", "Error estable ≤ 8°"],
                   ["Color", "20 lecturas por color en la pista real tras calibrar", "≥ 95 % de aciertos"],
                   ["Obstáculos", "Cono a 50 cm en recta y en curva, 10 repeticiones", "0 colisiones, retoma la pista"],
                   ["Voz", "10 comandos por palabra, 2 personas", "≥ 90 % reconocidos"],
                   ["Latencia", "Cronometrar app → movimiento (video 240 fps)", "< 150 ms"],
                   ["Niveles 1–3", "Recorrido completo de cada pista", "Completa sin intervención"]],
                  [3, 7.5, 5.5], "Plan de pruebas sobre el robot físico.")]


def cierre():
    return [h1("10. Estado y próximos pasos"),
            table([["Actividad", "Estado"],
                   ["Requerimientos, arquitectura, diagramas de bloques, materiales", "Completo"],
                   ["CAD paramétrico, planos, DXF/STL", "Completo"],
                   ["Esquemas eléctricos y asignación de pines", "Completo"],
                   ["Firmware de todos los módulos + control remoto", "Completo (verificado en simulación; falta "
                                                                       "carga en la placa)"],
                   ["App Streamlit + voz + J.A.R.V.I.S.", "Completo (probado con el gemelo digital)"],
                   ["Compra de componentes, corte láser e impresión 3D", "Siguiente corte"],
                   ["Ensamble, carga del firmware y calibración en pista", "Siguiente corte"],
                   ["Pruebas físicas por nivel (Tabla del plan de pruebas)", "Siguiente corte"]],
                  [10, 6], "Avance del proyecto."),
            h1("11. Conclusiones"),
            bullets([
                "Separar los dominios de potencia (7.4 V motores / 5 V–3.3 V lógica) y ubicar el magnetómetro en un "
                "mástil no metálico son las dos decisiones de diseño que más impactan la confiabilidad de la "
                "brújula y del ESP32.",
                "Normalizar la cromaticidad del TCS34725 y usar su LED propio permite distinguir los seis colores con "
                "un clasificador simple y calibrable en la pista.",
                "Un gemelo digital con la misma API del firmware permitió desarrollar la app, el chatbot y la lógica "
                "autónoma antes de tener el hardware, y detectar fallas (pérdida de la pista y retorno en sentido "
                "contrario tras esquivar) que habrían costado mucho tiempo en la pista real.",
                "La API REST única sirve tanto a la app como al chatbot, de modo que J.A.R.V.I.S. siempre responde "
                "con las mismas variables que se ven en el dashboard.",
            ]),
            h1("12. Referencias"),
            bullets(["Espressif Systems, <i>ESP32 Series Datasheet</i> y documentación de ESP-NOW y LEDC, 2024.",
                     "QST Corporation, <i>QMC5883L 3-Axis Magnetic Sensor Datasheet</i>, rev. 1.0.",
                     "ams-OSRAM, <i>TCS3472 Color Light-to-Digital Converter with IR Filter</i>, datasheet.",
                     "Toshiba, <i>TB6612FNG Driver IC for Dual DC Motor</i>, datasheet.",
                     "Vishay, <i>TCRT5000 Reflective Optical Sensor</i>, datasheet.",
                     "Monolithic Power Systems, <i>MP1584 3A, 1.5MHz, 28V Step-Down Converter</i>, datasheet.",
                     "Streamlit Inc., <i>Streamlit documentation</i> (st.fragment, st.audio_input, st.chat_input).",
                     "Anthropic, <i>Claude API documentation</i> (Messages API, streaming).",
                     "NOAA NCEI, <i>Magnetic Field Calculator</i> (declinación magnética), 2026.",
                     "R. Siegwart, I. Nourbakhsh, D. Scaramuzza, <i>Introduction to Autonomous Mobile Robots</i>, "
                     "2.ª ed., MIT Press, 2011."]),
            ]


def main():
    doc = Doc(OUT, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
              title="Primer Entregable – Robot móvil ESP32", author=AUTORA)
    story = (portada() + indice() + introduccion() + objetivos() + requerimientos() + arquitectura() + mecanico()
             + electronico() + firmware() + app() + validacion() + cierre())
    flat = []

    def add(x):
        if isinstance(x, list):
            for y in x:
                add(y)
        else:
            flat.append(x)
    add(story)
    doc.multiBuild(flat, onFirstPage=on_page, onLaterPages=on_page)
    print("PDF:", OUT)


if __name__ == "__main__":
    main()
