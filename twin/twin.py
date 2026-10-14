"""Gemelo digital en PyBullet del enjambre de 3 carritos con ACO.

Fases
-----
WAIT   : se asocia al AP y espera los "hello" de los 3 nodos ESP32; luego envía "go".
LEARN  : escucha las feromonas ("pher") que viajan por la red y las pinta como un
         mapa de calor sobre el laberinto (el gemelo ve lo mismo que los nodos).
DRIVE  : cuando llegan las 3 rutas finales ("route") responde "ack" y los 3 robots
         virtuales las recorren en la simulación física.
DONE   : guarda resultados (JSON/CSV/PNG/GIF) y sigue sirviendo el visor web.

Salidas en OUT_DIR (/out): latest.png, simulation.gif, results.json,
convergence.csv, convergence.png, status.json, index.html
"""
import csv
import functools
import http.server
import json
import math
import os
import threading
import time

import numpy as np
import pybullet as p
from PIL import Image, ImageDraw

from common.maze import Maze
from common.net import drain, encode, make_socket

AP = (os.environ.get("AP_HOST", "192.168.4.1"), int(os.environ.get("AP_PORT", "5000")))
OUT = os.environ.get("OUT_DIR", "/out")
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8080"))
N_NODES = int(os.environ.get("N_NODES", "3"))
RES = int(os.environ.get("FRAME_RES", "480"))
CELL = 0.25                  # m por celda
SPEED = float(os.environ.get("CAR_SPEED", "0.6"))   # m/s
DT = 1.0 / 240.0
DRIVE_FPS = 8
EXIT_WHEN_DONE = os.environ.get("EXIT_WHEN_DONE", "0") == "1"
USE_GUI = os.environ.get("TWIN_GUI", "0") == "1"
LEARN_TIMEOUT = float(os.environ.get("LEARN_TIMEOUT", "300"))

CAR_COLORS = [(0.90, 0.15, 0.15), (0.15, 0.65, 0.20), (0.15, 0.30, 0.90)]
Q_VIZ = 40.0

os.makedirs(OUT, exist_ok=True)
maze = Maze.from_env()

state = {"phase": "WAIT", "nodes_seen": [], "iters": {}, "best": {}, "routes": {},
         "arrived": {}, "sim_time": 0.0}
conv_rows = []               # (nodo, iteración, mejor_iter, mejor_hasta_ahora)


def log(*a):
    print("[gemelo]", *a, flush=True)


# ---------------------------------------------------------------------------
# Visor web mínimo
# ---------------------------------------------------------------------------
INDEX = """<!doctype html><meta charset=utf-8><title>Gemelo digital ACO</title>
<style>body{font-family:system-ui;background:#111;color:#eee;text-align:center;margin:1rem}
img{max-width:92vmin;border:2px solid #444;image-rendering:auto}a{color:#8cf}</style>
<h2>Enjambre de 3 carritos · ACO en ESP32 · gemelo digital PyBullet</h2>
<img id=f src=latest.png><pre id=s></pre>
<p><a href=simulation.gif>simulation.gif</a> · <a href=results.json>results.json</a> ·
<a href=convergence.png>convergence.png</a> · <a href=convergence.csv>convergence.csv</a></p>
<script>setInterval(()=>{f.src='latest.png?'+Date.now();
fetch('status.json?'+Date.now()).then(r=>r.json()).then(j=>s.textContent=JSON.stringify(j,null,1))},700)</script>
"""


def atomic_write(path, data, mode="w"):
    tmp = path + ".tmp"
    with open(tmp, mode) as f:
        f.write(data)
    os.replace(tmp, path)


def write_status():
    atomic_write(os.path.join(OUT, "status.json"), json.dumps(state, indent=1))


def start_http():
    atomic_write(os.path.join(OUT, "index.html"), INDEX)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    handler = functools.partial(Quiet, directory=OUT)
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log("visor web en http://localhost:%d" % HTTP_PORT)


# ---------------------------------------------------------------------------
# Escena PyBullet
# ---------------------------------------------------------------------------
def cell_xy(i):
    c, r = maze.rc(i)
    return c * CELL, (maze.H - 1 - r) * CELL


def build_world():
    p.connect(p.GUI if USE_GUI else p.DIRECT)
    p.setGravity(0, 0, -9.81)
    p.setTimeStep(DT)

    cx, cy = (maze.W - 1) * CELL / 2, (maze.H - 1) * CELL / 2
    # suelo
    fl = p.createVisualShape(p.GEOM_BOX, halfExtents=[maze.W * CELL / 2 + .1, maze.H * CELL / 2 + .1, .01],
                             rgbaColor=[0.25, 0.27, 0.30, 1])
    fc = p.createCollisionShape(p.GEOM_BOX, halfExtents=[maze.W * CELL / 2 + .1, maze.H * CELL / 2 + .1, .01])
    p.createMultiBody(0, fc, fl, [cx, cy, -.01])

    # paredes: se fusionan tramos horizontales contiguos en una sola caja
    wall_h = 0.12
    for r in range(maze.H):
        c = 0
        while c < maze.W:
            if maze.grid[r][c] == 1:
                c0 = c
                while c < maze.W and maze.grid[r][c] == 1:
                    c += 1
                n = c - c0
                x = (c0 + (n - 1) / 2) * CELL
                y = (maze.H - 1 - r) * CELL
                he = [n * CELL / 2, CELL / 2, wall_h / 2]
                vs = p.createVisualShape(p.GEOM_BOX, halfExtents=he, rgbaColor=[0.55, 0.40, 0.30, 1])
                cs = p.createCollisionShape(p.GEOM_BOX, halfExtents=he)
                p.createMultiBody(0, cs, vs, [x, y, wall_h / 2])
            else:
                c += 1

    # baldosas de color por celda libre (visual solamente) -> mapa de feromonas
    tiles = {}
    tv = p.createVisualShape(p.GEOM_BOX, halfExtents=[CELL / 2 * .96, CELL / 2 * .96, .004],
                             rgbaColor=[.93, .93, .93, 1])
    for i in maze.open_cells:
        x, y = cell_xy(i)
        tiles[i] = p.createMultiBody(0, -1, tv, [x, y, .004])
    base_col = {i: (.93, .93, .93) for i in maze.open_cells}
    for s in maze.starts:
        base_col[s] = (.65, .80, 1.0)               # zona de salida (punto A)
    base_col[maze.goal] = (1.0, .85, .20)           # meta
    # bandera de meta
    gx, gy = cell_xy(maze.goal)
    pole = p.createVisualShape(p.GEOM_CYLINDER, radius=.008, length=.22, rgbaColor=[.9, .9, .9, 1])
    flag = p.createVisualShape(p.GEOM_BOX, halfExtents=[.06, .004, .035], rgbaColor=[.05, .05, .05, 1])
    p.createMultiBody(0, -1, pole, [gx - .06, gy, .11])
    p.createMultiBody(0, -1, flag, [gx, gy, .20])
    for i, col in base_col.items():
        p.changeVisualShape(tiles[i], -1, rgbaColor=list(col) + [1])
    return tiles, base_col


def make_car(color, start_idx):
    bx, by = cell_xy(start_idx)
    half = [.055, .035, .018]
    body_v = p.createVisualShape(p.GEOM_BOX, halfExtents=half, rgbaColor=list(color) + [1])
    body_c = p.createCollisionShape(p.GEOM_BOX, halfExtents=half)
    wheel_q = p.getQuaternionFromEuler([math.pi / 2, 0, 0])
    wv = p.createVisualShape(p.GEOM_CYLINDER, radius=.022, length=.016, rgbaColor=[.05, .05, .05, 1],
                             visualFrameOrientation=wheel_q)
    offs = [[.04, .04, -.01], [.04, -.04, -.01], [-.04, .04, -.01], [-.04, -.04, -.01]]
    car = p.createMultiBody(
        baseMass=1.0, baseCollisionShapeIndex=body_c, baseVisualShapeIndex=body_v,
        basePosition=[bx, by, .03],
        linkMasses=[0] * 4, linkCollisionShapeIndices=[-1] * 4, linkVisualShapeIndices=[wv] * 4,
        linkPositions=offs, linkOrientations=[[0, 0, 0, 1]] * 4,
        linkInertialFramePositions=[[0, 0, 0]] * 4, linkInertialFrameOrientations=[[0, 0, 0, 1]] * 4,
        linkParentIndices=[0] * 4, linkJointTypes=[p.JOINT_FIXED] * 4, linkJointAxis=[[0, 0, 1]] * 4)
    p.changeDynamics(car, -1, lateralFriction=0.0, linearDamping=0.0, angularDamping=0.0)
    return car


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


class Car:
    TOL = 0.04

    def __init__(self, body, route):
        self.body = body
        self.wps = [cell_xy(i) for i in route]
        self.k = 1
        self.arrived_at = None

    def step(self, t):
        if self.k >= len(self.wps):
            if self.arrived_at is None:
                self.arrived_at = t
            p.resetBaseVelocity(self.body, [0, 0, 0], [0, 0, 0])
            return
        pos, orn = p.getBasePositionAndOrientation(self.body)
        yaw = p.getEulerFromQuaternion(orn)[2]
        tx, ty = self.wps[self.k]
        dx, dy = tx - pos[0], ty - pos[1]
        if math.hypot(dx, dy) < self.TOL:
            self.k += 1
            return
        err = wrap(math.atan2(dy, dx) - yaw)
        w = max(-6.0, min(6.0, 6.0 * err))
        v = SPEED * max(0.0, math.cos(err)) if abs(err) < 0.5 else 0.0
        vz = p.getBaseVelocity(self.body)[0][2]
        p.resetBaseVelocity(self.body, [v * math.cos(yaw), v * math.sin(yaw), vz], [0, 0, w])

    @property
    def done(self):
        return self.arrived_at is not None


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def make_camera():
    cx, cy = (maze.W - 1) * CELL / 2, (maze.H - 1) * CELL / 2
    H = maze.W * CELL / (2 * math.tan(math.radians(22.5))) + .35
    view = p.computeViewMatrix([cx, cy, H], [cx, cy, 0], [0, 1, 0])
    proj = p.computeProjectionMatrixFOV(45, 1.0, .05, H + 1)
    return view, proj


frames = []
view_m = proj_m = None


def render(caption):
    img = p.getCameraImage(RES, RES, viewMatrix=view_m, projectionMatrix=proj_m,
                           renderer=p.ER_TINY_RENDERER, flags=p.ER_NO_SEGMENTATION_MASK)
    rgb = np.array(img[2], dtype=np.uint8).reshape(RES, RES, 4)[:, :, :3]
    im = Image.fromarray(rgb)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, RES, 14], fill=(0, 0, 0))
    d.text((4, 2), caption, fill=(255, 255, 255))
    im.save(os.path.join(OUT, "latest.png.tmp.png"))
    os.replace(os.path.join(OUT, "latest.png.tmp.png"), os.path.join(OUT, "latest.png"))
    frames.append(im.convert("P", palette=Image.ADAPTIVE, colors=128))


def paint_heat(tiles, base_col, heat):
    m = max(heat.values()) if heat else 1.0
    m = max(m, 1e-6)
    for i in maze.open_cells:
        h = min(1.0, heat.get(i, 0.0) / m)
        b = base_col[i]
        col = [b[0] + (1.0 - b[0]) * h, b[1] + (.35 - b[1]) * h, b[2] + (.0 - b[2]) * h, 1]
        p.changeVisualShape(tiles[i], -1, rgbaColor=col)


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------
def main():
    global view_m, proj_m
    start_http()
    tiles, base_col = build_world()
    view_m, proj_m = make_camera()
    sock = make_socket()
    heat = {}
    routes = {}
    seen_nodes, got_pher = set(), set()
    t_last_go, t_last_frame = 0.0, 0.0
    t_learn0 = None
    optimal = {k + 1: maze.shortest(s, maze.goal) for k, s in enumerate(maze.starts[:N_NODES])}
    log("laberinto %dx%d | meta=%s | rutas óptimas (BFS, referencia del informe): %s"
        % (maze.W, maze.H, maze.rc(maze.goal), optimal))
    render("Gemelo digital - esperando nodos ESP32...")

    # ---------------- WAIT + LEARN -------------------------------------------
    while len(routes) < N_NODES:
        now = time.time()
        if now - t_last_go > 1.0:
            sock.sendto(encode({"t": "twin"}), AP)        # asociarse al AP
            if len(seen_nodes) >= N_NODES and len(got_pher) < N_NODES:
                sock.sendto(encode({"t": "go"}), AP)
                if state["phase"] == "WAIT":
                    log("3 nodos asociados -> orden 'go'")
                    state["phase"] = "LEARN"
                    t_learn0 = now
            t_last_go = now
        dirty = False
        for m, _ in drain(sock):
            t, n = m.get("t"), m.get("n")
            if t == "hello":
                seen_nodes.add(n)
                state["nodes_seen"] = sorted(seen_nodes)
            elif t == "pher":
                got_pher.add(n)
                for k in heat:
                    heat[k] *= 0.985
                amt = Q_VIZ / max(1, len(m["p"]))
                for c in m["p"]:
                    heat[c] = heat.get(c, 0.0) + amt
                state["iters"][n] = m["i"]
                state["best"][n] = m["b"]
                conv_rows.append((n, m["i"], m["len"], m["b"]))
                dirty = True
            elif t == "route" and n not in routes:
                routes[n] = m
                state["routes"][n] = {"len": m["len"], "iters": m["i"]}
                log("ruta recibida del nodo %s: %d celdas (óptima %s)" % (n, m["len"], optimal.get(n)))
            if t == "route":
                sock.sendto(encode({"t": "ack", "n": n}), AP)    # (re)confirmar siempre
        if dirty and now - t_last_frame > 0.30:
            paint_heat(tiles, base_col, heat)
            it_txt = " ".join("n%d:it%d/b%d" % (k, state["iters"].get(k, 0), state["best"].get(k, 0))
                              for k in sorted(state["iters"]))
            render("ACO aprendiendo | " + it_txt)
            t_last_frame = now
            write_status()
        if t_learn0 and now - t_learn0 > LEARN_TIMEOUT:
            log("timeout esperando rutas")
            break
        time.sleep(0.01)
    # dar tiempo a que los ack lleguen y re-confirmar
    for _ in range(3):
        for n in routes:
            sock.sendto(encode({"t": "ack", "n": n}), AP)
        time.sleep(0.3)
    if not routes:
        return 1

    # ---------------- DRIVE ---------------------------------------------------
    state["phase"] = "DRIVE"
    paint_heat(tiles, base_col, heat)
    # resaltar cada ruta final con el color del carrito
    for n, m in routes.items():
        col = CAR_COLORS[(n - 1) % 3]
        for c in m["p"]:
            p.changeVisualShape(tiles[c], -1, rgbaColor=[.5 + .5 * col[0], .5 + .5 * col[1], .5 + .5 * col[2], 1])
    cars = {}
    for n, m in routes.items():
        body = make_car(CAR_COLORS[(n - 1) % 3], m["p"][0])
        cars[n] = Car(body, m["p"])
    for a in cars.values():                       # los carritos no chocan entre sí
        for b in cars.values():
            if a is not b:
                p.setCollisionFilterPair(a.body, b.body, -1, -1, 0)
    log("simulación física: %d robots virtuales en marcha" % len(cars))
    t, next_frame = 0.0, 0.0
    while t < 400.0 and not all(c.done for c in cars.values()):
        for n, c in cars.items():
            c.step(t)
        p.stepSimulation()
        t += DT
        if t >= next_frame:
            next_frame += 1.0 / DRIVE_FPS
            state["sim_time"] = round(t, 2)
            render("DRIVE t=%.1fs | " % t + " ".join(
                "R%d:%d/%d" % (n, c.k, len(c.wps)) for n, c in sorted(cars.items())))
            if len(frames) % 8 == 0:
                state["arrived"] = {n: c.arrived_at for n, c in cars.items() if c.done}
                write_status()
    render("FIN | t=%.1fs" % t)

    # ---------------- DONE ----------------------------------------------------
    state["phase"] = "DONE"
    results = {"maze": {"W": maze.W, "H": maze.H, "cell_m": CELL,
                        "starts": [maze.rc(s) for s in maze.starts], "goal": maze.rc(maze.goal)},
               "robots": {}}
    for n, m in sorted(routes.items()):
        opt = optimal.get(n)
        results["robots"][str(n)] = {
            "start": list(maze.rc(m["p"][0])), "route_cells": m["len"],
            "optimal_cells": opt, "optimality_ratio": round(opt / m["len"], 3) if opt else None,
            "is_optimal": m["len"] == opt, "aco_iterations": m["i"], "node_time_s": m.get("dt"),
            "arrival_sim_s": round(cars[n].arrived_at, 2) if cars[n].done else None}
    atomic_write(os.path.join(OUT, "results.json"), json.dumps(results, indent=2, ensure_ascii=False))
    with open(os.path.join(OUT, "convergence.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["nodo", "iteracion", "mejor_iteracion", "mejor_hasta_ahora"])
        w.writerows(conv_rows)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 3.6))
        for n in sorted(routes):
            rows = [r for r in conv_rows if r[0] == n]
            col = CAR_COLORS[(n - 1) % 3]
            ax.plot([r[1] for r in rows], [r[3] for r in rows], color=col, label="nodo %d (mejor)" % n)
            ax.plot([r[1] for r in rows], [r[2] for r in rows], color=col, alpha=.25, lw=.8)
            if optimal.get(n):
                ax.axhline(optimal[n], color=col, ls=":", lw=.8)
        ax.set_xlabel("iteración ACO")
        ax.set_ylabel("longitud de ruta [celdas]")
        ax.set_title("Convergencia del ACO (punteado = óptimo BFS)")
        ax.legend()
        ax.grid(alpha=.3)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, "convergence.png"), dpi=130)
    except Exception as e:                                  # noqa
        log("sin gráfica de convergencia:", e)
    if frames:
        gif = os.path.join(OUT, "simulation.gif")
        frames[0].save(gif, save_all=True, append_images=frames[1:], duration=110, loop=0, optimize=False)
    write_status()
    log("TERMINADO | resultados en", OUT)
    for n, r in results["robots"].items():
        log("  robot %s: ruta %d celdas (óptimo %s) | llegó a t=%s s" %
            (n, r["route_cells"], r["optimal_cells"], r["arrival_sim_s"]))
    if EXIT_WHEN_DONE:
        return 0
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    raise SystemExit(main())
