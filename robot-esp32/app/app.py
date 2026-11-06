"""Dashboard Streamlit del robot ESP32.

- Control manual inalámbrico (Wi-Fi): botones Arriba/Abajo/Derecha/Izquierda y comandos de voz.
- Visualización en tiempo real de la dirección polar actual y deseada (brújula).
- Telemetría: obstáculos, color de la superficie, sensores de línea, motores, batería.
- Chatbot J.A.R.V.I.S. que explica el proyecto y las variables en tiempo real.

Ejecutar:
    streamlit run app.py
Con el simulador (sin hardware):
    python simulator.py --nivel 1      # en otra terminal
    ROBOT_URL=http://localhost:8000 streamlit run app.py
"""
from __future__ import annotations

import io
import os
import time
from collections import deque

import plotly.graph_objects as go
import requests
import streamlit as st

import jarvis
from commands import parse
from robot_client import DEFAULT_URL, RobotClient

st.set_page_config(page_title="Robot ESP32 – Dashboard", page_icon="🤖", layout="wide")

COLOR_HEX = {"negro": "#111111", "blanco": "#f4f4f4", "rojo": "#d62828", "amarillo": "#f6c90e",
             "verde": "#2a9d3f", "azul": "#1d4ed8", "desconocido": "#888888"}

# ----------------------------------------------------------------------------- estado de sesión
ss = st.session_state
ss.setdefault("history", deque(maxlen=240))      # (t, heading, heading_des, dist)
ss.setdefault("events", deque(maxlen=30))
ss.setdefault("last_event_id", -1)
ss.setdefault("chat", [])
ss.setdefault("last_state", None)
ss.setdefault("voice_log", [])

# ----------------------------------------------------------------------------- barra lateral
with st.sidebar:
    st.title("🤖 Robot ESP32")
    url = st.text_input("URL del robot", os.environ.get("ROBOT_URL", DEFAULT_URL),
                        help="ESP32 real: http://192.168.4.1 (conéctese a la red ROBOT-ESP32). "
                             "Simulador: http://localhost:8000")
    robot = RobotClient(url, timeout=0.8)
    speed = st.slider("Velocidad manual (%)", 20, 100, 60, 5)
    refresh = st.select_slider("Refresco del dashboard (s)", [0.25, 0.5, 1.0, 2.0], value=0.5)
    use_llm = st.toggle("J.A.R.V.I.S. con Claude", value=jarvis.llm_available(),
                        help="Requiere ANTHROPIC_API_KEY. Sin ella se usa un motor de reglas local.")
    st.caption("Conexión inalámbrica: Wi-Fi (SoftAP) + API REST/JSON. "
               "Control físico alterno: ESP-NOW.")


def safe(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except requests.RequestException as e:
        st.toast(f"Sin respuesta del robot: {e.__class__.__name__}", icon="⚠️")
        return None


def compass_figure(heading: float, desired: float) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=[0, 1], theta=[desired, desired], mode="lines+markers",
                                  line=dict(color="#f97316", width=5, dash="dash"),
                                  marker=dict(size=[0, 14], symbol="circle"), name=f"Deseada {desired:.0f}°"))
    fig.add_trace(go.Scatterpolar(r=[0, 1], theta=[heading, heading], mode="lines+markers",
                                  line=dict(color="#2563eb", width=7),
                                  marker=dict(size=[0, 18], symbol="triangle-up"), name=f"Actual {heading:.0f}°"))
    fig.update_layout(
        polar=dict(angularaxis=dict(rotation=90, direction="clockwise",
                                    tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                                    ticktext=["N", "NE", "E", "SE", "S", "SO", "O", "NO"]),
                   radialaxis=dict(visible=False, range=[0, 1.05])),
        showlegend=True, legend=dict(orientation="h", y=-0.12), height=360,
        margin=dict(l=30, r=30, t=20, b=30))
    return fig


def history_figure(hist) -> go.Figure:
    t0 = hist[0][0] if hist else 0
    xs = [h[0] - t0 for h in hist]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=[h[1] for h in hist], name="Rumbo actual", line=dict(color="#2563eb")))
    fig.add_trace(go.Scatter(x=xs, y=[h[2] for h in hist], name="Deseado", line=dict(color="#f97316", dash="dash")))
    fig.add_trace(go.Scatter(x=xs, y=[min(h[3], 200) for h in hist], name="Distancia (cm)", yaxis="y2",
                             line=dict(color="#6b7280", width=1)))
    fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10), xaxis_title="t (s)",
                      yaxis=dict(title="°", range=[0, 360]),
                      yaxis2=dict(title="cm", overlaying="y", side="right", range=[0, 200]),
                      legend=dict(orientation="h", y=1.15))
    return fig


def track_figure(track: dict, s: dict) -> go.Figure:
    fig = go.Figure()
    pts, cols = track["track"], track["sections"]
    for i in range(len(pts) - 1):
        if i % 4:
            continue
        seg = pts[i:i + 5]
        fig.add_trace(go.Scatter(x=[p[0] for p in seg], y=[p[1] for p in seg], mode="lines",
                                 line=dict(color=COLOR_HEX[cols[i]], width=14), hoverinfo="skip", showlegend=False))
    if track["trail"]:
        fig.add_trace(go.Scatter(x=[p[0] for p in track["trail"]], y=[p[1] for p in track["trail"]], mode="lines",
                                 line=dict(color="#a855f7", width=2), name="Trayectoria"))
    fig.add_trace(go.Scatter(x=[o[0] for o in track["obstacles"]], y=[o[1] for o in track["obstacles"]],
                             mode="markers", marker=dict(symbol="triangle-up", size=14, color="#ea580c"),
                             name="Obstáculos"))
    fig.add_trace(go.Scatter(x=[s["sim"]["x"]], y=[s["sim"]["y"]], mode="markers",
                             marker=dict(size=14, color="#2563eb", line=dict(color="white", width=2)), name="Robot"))
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(scaleanchor="x"),
                      legend=dict(orientation="h", y=-0.05), plot_bgcolor="#d9d9d9")
    return fig


# ----------------------------------------------------------------------------- encabezado
st.title("Robot móvil ESP32 · Dashboard en tiempo real")
tab_dash, tab_ctrl, tab_chat, tab_cal = st.tabs(["🧭 Dashboard", "🎮 Control y voz", "🤖 J.A.R.V.I.S.",
                                                  "⚙️ Calibración"])


@st.fragment(run_every=refresh)
def live_dashboard():
    try:
        s = robot.state()
    except requests.RequestException:
        st.error(f"No hay conexión con el robot en {url}. ¿Está conectado a la red ROBOT-ESP32 "
                 "o corriendo el simulador?")
        ss.last_state = None
        return
    ss.last_state = s
    ss.history.append((time.time(), s["heading"], s["heading_des"], s["dist_cm"]))
    if s["event_id"] != ss.last_event_id:
        ss.last_event_id = s["event_id"]
        ss.events.appendleft(f"{time.strftime('%H:%M:%S')} · {s['event']}")

    m = st.columns(6)
    m[0].metric("Modo", s["mode"], s["nav"] if s["mode"] == "AUTO" else None)
    m[1].metric("Rumbo actual", f"{s['heading']:.0f}°")
    m[2].metric("Dirección deseada", f"{s['heading_des']:.0f}°", f"{s['heading_err']:+.0f}° error",
                delta_color="off")
    m[3].metric("Obstáculo", f"{s['dist_cm']:.0f} cm", "¡CERCA!" if s["obstacle"] else "libre",
                delta_color="inverse" if s["obstacle"] else "normal")
    m[4].metric("Color superficie", s["color"].capitalize(), f"{s['color_changes']} cambios", delta_color="off")
    m[5].metric("Batería", f"{s['batt_v']:.2f} V", "baja" if s["batt_v"] < 7.0 else "ok",
                delta_color="inverse" if s["batt_v"] < 7.0 else "normal")

    c1, c2, c3 = st.columns([1.1, 1.3, 1])
    with c1:
        st.subheader("Dirección polar")
        st.plotly_chart(compass_figure(s["heading"], s["heading_des"]), width="stretch",
                        key="compass")
    with c2:
        if "sim" in s:
            st.subheader(f"Pista simulada – nivel {s['sim']['level']}")
            track = robot.track()
            if track:
                st.plotly_chart(track_figure(track, s), width="stretch", key="track")
        else:
            st.subheader("Historial de rumbo")
        st.plotly_chart(history_figure(list(ss.history)), width="stretch", key="hist")
    with c3:
        st.subheader("Sensores")
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px'>"
            f"<div style='width:46px;height:46px;border-radius:8px;border:2px solid #555;"
            f"background:{COLOR_HEX.get(s['color'], '#888')}'></div>"
            f"<div><b>{s['color']}</b><br><small>RGBC {s['rgbc']}</small></div></div>", unsafe_allow_html=True)
        line = "".join("⬛" if v else "⬜" for v in s["line"])
        st.markdown(f"**Línea (I‑C‑D):** {line}")
        st.markdown(f"**Estado autónomo:** `{s['state']}`")
        st.markdown(f"**Obstáculos esquivados:** {s['obstacles_avoided']}")
        st.markdown(f"**Servo ultrasonido:** {s['servo']}°")
        st.progress(min(1.0, abs(s["pwm_l"])), text=f"Motor izq. {s['pwm_l']:+.2f}")
        st.progress(min(1.0, abs(s["pwm_r"])), text=f"Motor der. {s['pwm_r']:+.2f}")
        st.caption(f"Último comando: {s['last_move']} ({s['cmd_src']}) · uptime {s['uptime_s']} s")
        if "sim" in s:
            st.caption(f"Simulador: colisiones {s['sim']['collisions']} · recorrido {s['sim']['distance_m']} m")
        st.markdown("**Eventos**")
        st.code("\n".join(ss.events) or "—", language=None)


with tab_dash:
    live_dashboard()

# ----------------------------------------------------------------------------- control
with tab_ctrl:
    left, right = st.columns([1, 1.2])
    with left:
        st.subheader("Control manual")
        hold = st.slider("Duración de cada pulso (ms)", 200, 2000, 600, 100)
        _, cu, _ = st.columns(3)
        if cu.button("⬆️ Arriba", width="stretch"):
            safe(robot.move, "forward", speed, hold)
        cl, cs, cr = st.columns(3)
        if cl.button("⬅️ Izquierda", width="stretch"):
            safe(robot.move, "left", speed, hold)
        if cs.button("⏹️ Detener", width="stretch", type="primary"):
            safe(robot.stop)
        if cr.button("➡️ Derecha", width="stretch"):
            safe(robot.move, "right", speed, hold)
        _, cd, _ = st.columns(3)
        if cd.button("⬇️ Abajo", width="stretch"):
            safe(robot.move, "backward", speed, hold)

        st.divider()
        st.subheader("Modo de operación")
        nav = st.radio("Navegación autónoma", ["linea", "rumbo"], horizontal=True,
                       format_func=lambda v: "Seguir pista" if v == "linea" else "Mantener rumbo (brújula)")
        a, b, c = st.columns(3)
        if a.button("▶️ Autónomo", width="stretch"):
            safe(robot.mode, "auto", nav)
        if b.button("⏸️ Pausa", width="stretch"):
            safe(robot.mode, "pausa")
        if c.button("🕹️ Manual", width="stretch"):
            safe(robot.mode, "manual")
        auto_speed = st.slider("Velocidad modo autónomo (%)", 20, 100, 55, 5)
        if st.button("Aplicar velocidad autónoma"):
            safe(robot.speed, auto_speed)

        st.subheader("Dirección polar deseada")
        deg = st.slider("Rumbo deseado (°)", 0, 359, 90)
        if st.button("Enviar dirección deseada"):
            safe(robot.heading, deg=deg)

    with right:
        st.subheader("🎙️ Comandos de voz")
        st.caption("Diga: «arriba», «abajo», «derecha», «izquierda», «detente», «modo automático», "
                   "«rumbo 90», «gira 45 grados a la derecha», «modo manual».")
        audio = st.audio_input("Grabar comando")
        if audio is not None and ss.get("last_audio_id") != audio.file_id:
            ss.last_audio_id = audio.file_id
            try:
                import speech_recognition as sr
                rec = sr.Recognizer()
                with sr.AudioFile(io.BytesIO(audio.getvalue())) as source:
                    data = rec.record(source)
                text = rec.recognize_google(data, language="es-CO")
            except ImportError:
                text, err = None, "Instale SpeechRecognition (pip install SpeechRecognition)."
            except Exception as e:  # noqa: BLE001 – errores de reconocimiento o de red
                text, err = None, f"No se pudo reconocer el audio ({e.__class__.__name__})."
            if text:
                action = parse(text)
                if action:
                    safe(robot.execute, action, speed, "voz")
                    ss.voice_log.insert(0, f"🗣️ «{text}» → {action}")
                else:
                    ss.voice_log.insert(0, f"🗣️ «{text}» → comando no reconocido")
            else:
                ss.voice_log.insert(0, f"⚠️ {err}")

        typed = st.text_input("…o escriba el comando", placeholder="ej. avanza 2 segundos")
        if st.button("Ejecutar comando escrito") and typed:
            action = parse(typed)
            if action:
                safe(robot.execute, action, speed, "texto")
                ss.voice_log.insert(0, f"⌨️ «{typed}» → {action}")
            else:
                ss.voice_log.insert(0, f"⌨️ «{typed}» → comando no reconocido")
        for line in ss.voice_log[:10]:
            st.write(line)

# ----------------------------------------------------------------------------- chatbot
with tab_chat:
    st.subheader("J.A.R.V.I.S. · asistente del proyecto")
    st.caption("Pregunte por el proyecto o por las variables en tiempo real: «¿qué rumbo tienes?», "
               "«¿hay obstáculos?», «explícame cómo detectas colores», «¿cómo está la batería?»")
    for msg in ss.chat:
        with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else None):
            st.markdown(msg["content"])
    question = st.chat_input("Hable con J.A.R.V.I.S.")
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        state = safe(robot.state)
        with st.chat_message("assistant", avatar="🤖"):
            answer = None
            if use_llm:
                import anthropic
                try:
                    answer = st.write_stream(jarvis.ask_claude(ss.chat, question, state))
                except anthropic.AuthenticationError:
                    st.warning("Credenciales de Claude no válidas; uso el motor local.")
                except anthropic.RateLimitError:
                    st.warning("Límite de uso de la API alcanzado; uso el motor local.")
                except anthropic.APIStatusError as e:
                    st.warning(f"Error de la API ({e.status_code}); uso el motor local.")
                except anthropic.APIConnectionError:
                    st.warning("Sin conexión a internet; uso el motor local.")
            if not answer:
                answer = jarvis.ask_local(question, state)
                st.markdown(answer)
        ss.chat += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]

# ----------------------------------------------------------------------------- calibración
with tab_cal:
    st.subheader("Calibración de sensores")
    st.markdown("**Brújula:** coloque el robot en el piso lejos de objetos metálicos y pulse el botón; "
                "girará en el sitio durante 8 s para medir los offsets hard/soft-iron.")
    if st.button("🧭 Calibrar brújula"):
        safe(robot.calibrate, "compass")
    st.markdown("**Color:** ponga el sensor sobre cada sección de la pista y guarde la referencia.")
    col = st.selectbox("Color de referencia", ["negro", "blanco", "rojo", "amarillo", "verde", "azul"])
    if st.button("🎨 Guardar referencia de color"):
        r = safe(robot.calibrate, "color", col)
        if r:
            st.success(r.get("msg"))
