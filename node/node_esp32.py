"""Nodo ESP32 simulado: corre ACO (colonia de hormigas) y comparte feromonas por red.

Sólo usa la biblioteca estándar de Python (sin numpy), para parecerse a lo que
correría un ESP32 con MicroPython: diccionarios, listas, random y sockets UDP.

Ciclo de cada iteración
-----------------------
1. Lee los mensajes de la red y deposita feromona con las rutas de los otros nodos.
2. Lanza ANTS hormigas desde su punto de salida hasta la meta.
3. Evapora, deposita (ranking + mejor global) y acota la feromona (estilo MAX-MIN).
4. Publica por el AP la mejor ruta de la iteración ("pher").
5. Si la mejor ruta no mejora en WINDOW iteraciones, publica la ruta final ("route")
   y espera la confirmación del gemelo digital ("ack").

Variables de entorno: NODE_ID, AP_HOST, AP_PORT, MAZE_*, ANTS, ALPHA, BETA, RHO,
Q, WINDOW, MIN_ITERS, MAX_ITERS, ITER_PERIOD, SEED
"""
import os
import random
import sys
import time

from common.maze import Maze
from common.net import drain, encode, make_socket

NODE_ID = int(os.environ.get("NODE_ID", "1"))
AP = (os.environ.get("AP_HOST", "192.168.4.1"), int(os.environ.get("AP_PORT", "5000")))

ANTS = int(os.environ.get("ANTS", "10"))
ALPHA = float(os.environ.get("ALPHA", "1.0"))
BETA = float(os.environ.get("BETA", "2.0"))
RHO = float(os.environ.get("RHO", "0.20"))
Q = float(os.environ.get("Q", "20"))
SHARE_W = float(os.environ.get("SHARE_W", "0.5"))      # peso de la feromona de otros nodos
TAU0, TAU_MIN, TAU_MAX = 1.0, 0.05, 6.0
WINDOW = int(os.environ.get("WINDOW", "50"))
MIN_ITERS = int(os.environ.get("MIN_ITERS", "80"))
MAX_ITERS = int(os.environ.get("MAX_ITERS", "300"))
ITER_PERIOD = float(os.environ.get("ITER_PERIOD", "0.12"))

maze = Maze.from_env()
START = maze.starts[(NODE_ID - 1) % len(maze.starts)]
GOAL = maze.goal
rnd = random.Random(int(os.environ.get("SEED", "1000")) + NODE_ID)
TAG = "[nodo%d]" % NODE_ID


def log(*a):
    print(TAG, *a, flush=True)


# --- estado ACO -------------------------------------------------------------
tau = {e: TAU0 for e in maze.edges()}
eta = {c: 1.0 / (1.0 + maze.manhattan(c, GOAL)) for c in maze.open_cells}


def ant_walk():
    """Una hormiga: elección probabilística + retroceso en callejones sin salida.

    Devuelve la ruta simple START->GOAL (lista de celdas) o None.
    """
    path = [START]
    visited = {START}
    steps, max_steps = 0, 4 * len(maze.open_cells)
    while path[-1] != GOAL and steps < max_steps:
        cur = path[-1]
        cands = [n for n in maze.nbrs[cur] if n not in visited]
        steps += 1
        if not cands:
            path.pop()
            if not path:
                return None
            continue
        w = [(tau[maze.ek(cur, n)] ** ALPHA) * (eta[n] ** BETA) for n in cands]
        r = rnd.random() * sum(w)
        acc = 0.0
        nxt = cands[-1]
        for n, wi in zip(cands, w):
            acc += wi
            if r <= acc:
                nxt = n
                break
        visited.add(nxt)
        path.append(nxt)
    return path if path and path[-1] == GOAL else None


def deposit(path, amount):
    for a, b in zip(path, path[1:]):
        k = maze.ek(a, b)
        if k in tau:
            tau[k] = min(TAU_MAX, tau[k] + amount)


def main():
    sock = make_socket()
    log("arranca | salida=%s meta=%s | hormigas=%d α=%.1f β=%.1f ρ=%.2f"
        % (maze.rc(START), maze.rc(GOAL), ANTS, ALPHA, BETA, RHO))

    # --- 1) Asociarse al AP y esperar la orden "go" del gemelo digital -------
    go = False
    last_hello = 0.0
    while not go:
        if time.time() - last_hello > 1.0:
            sock.sendto(encode({"t": "hello", "n": NODE_ID}), AP)
            last_hello = time.time()
        for m, _ in drain(sock):
            if m.get("t") == "go":
                go = True
        time.sleep(0.05)
    log("orden 'go' recibida, inicia ACO")

    best_len, best_path, last_improve = 10 ** 9, None, 0
    it = 0
    t0 = time.time()
    while it < MAX_ITERS:
        it += 1
        t_it = time.time()

        # 1) feromona de los demás nodos
        for m, _ in drain(sock):
            if m.get("t") == "pher" and m.get("n") != NODE_ID and m.get("p"):
                deposit(m["p"], SHARE_W * Q / max(1, len(m["p"])))

        # 2) hormigas
        results = []
        for _ in range(ANTS):
            p = ant_walk()
            if p:
                results.append(p)
        if not results:
            continue
        it_best = min(results, key=len)

        # 3) evaporación + depósito elitista + límites MAX-MIN
        for k in tau:
            tau[k] = max(TAU_MIN, tau[k] * (1.0 - RHO))
        if len(it_best) < best_len:
            best_len, best_path, last_improve = len(it_best), list(it_best), it
        # ranking: las 3 mejores hormigas de la iteración (pesos 3,2,1) + mejor global
        for rank, p in enumerate(sorted(results, key=len)[:3]):
            deposit(p, (3 - rank) * Q / len(p) / 3.0)
        deposit(best_path, Q / len(best_path))

        # 4) publicar por la red
        sock.sendto(encode({"t": "pher", "n": NODE_ID, "i": it, "len": len(it_best),
                            "b": best_len, "p": it_best}), AP)
        if it % 10 == 0 or it == 1:
            log("it=%3d  mejor_iter=%3d  mejor=%3d celdas  éxito=%d/%d"
                % (it, len(it_best), best_len, len(results), ANTS))

        # 5) convergencia
        if it >= MIN_ITERS and it - last_improve >= WINDOW:
            log("convergió en it=%d (sin mejora en %d iteraciones)" % (it, WINDOW))
            break
        time.sleep(max(0.0, ITER_PERIOD - (time.time() - t_it)))

    # --- 2) publicar la ruta final hasta recibir el ack del gemelo ------------
    dt = time.time() - t0
    log("ruta final: %d celdas (%d pasos) | %d iteraciones | %.1f s" %
        (best_len, best_len - 1, it, dt))
    acked = False
    deadline = time.time() + 120
    while not acked and time.time() < deadline:
        sock.sendto(encode({"t": "route", "n": NODE_ID, "i": it, "len": best_len,
                            "p": best_path, "dt": round(dt, 2)}), AP)
        t_wait = time.time() + 1.0
        while time.time() < t_wait and not acked:
            for m, _ in drain(sock):
                if m.get("t") == "ack" and m.get("n") == NODE_ID:
                    acked = True
            time.sleep(0.05)
    log("ruta confirmada por el gemelo digital" if acked else "SIN ack (timeout)")
    return 0 if acked else 1


if __name__ == "__main__":
    sys.exit(main())
