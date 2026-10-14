"""Laberinto/almacén compartido por los nodos ESP32 simulados y el gemelo digital.

Todos los contenedores generan EXACTAMENTE el mismo laberinto a partir de la
misma semilla (MAZE_SEED), así no hace falta compartir archivos.

Convenciones
------------
* La rejilla es grid[fila][columna]; 1 = pared, 0 = libre.
* Un nodo del grafo es el índice  idx = fila * W + columna.
* Las aristas son no dirigidas entre celdas libres vecinas (4-conectividad).
"""
import os
import random
from collections import deque


class Maze:
    def __init__(self, cells_w=9, cells_h=9, seed=7, braid=0.12, room=3):
        self.cells_w, self.cells_h = cells_w, cells_h
        self.W, self.H = 2 * cells_w + 1, 2 * cells_h + 1
        self.N = self.W * self.H
        W, H = self.W, self.H
        rnd = random.Random(seed)

        grid = [[1] * W for _ in range(H)]

        # 1) Laberinto perfecto (backtracker iterativo)
        grid[1][1] = 0
        visited = {(0, 0)}
        stack = [(0, 0)]
        while stack:
            cx, cy = stack[-1]
            opts = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < cells_w and 0 <= ny < cells_h and (nx, ny) not in visited:
                    opts.append((nx, ny, dx, dy))
            if not opts:
                stack.pop()
                continue
            nx, ny, dx, dy = rnd.choice(opts)
            grid[2 * cy + 1 + dy][2 * cx + 1 + dx] = 0
            grid[2 * ny + 1][2 * nx + 1] = 0
            visited.add((nx, ny))
            stack.append((nx, ny))

        # 2) "Braiding": abrir algunas paredes para crear ciclos (rutas alternativas)
        candidates = []
        for r in range(1, H - 1):
            for c in range(1, W - 1):
                if grid[r][c] == 1 and (r + c) % 2 == 1:
                    if r % 2 == 1 and grid[r][c - 1] == 0 and grid[r][c + 1] == 0:
                        candidates.append((r, c))
                    elif r % 2 == 0 and grid[r - 1][c] == 0 and grid[r + 1][c] == 0:
                        candidates.append((r, c))
        for r, c in candidates:
            if rnd.random() < braid:
                grid[r][c] = 0

        # 3) Sala de salida (zona del punto A) de room x room celdas
        for r in range(1, room + 1):
            for c in range(1, room + 1):
                grid[r][c] = 0

        self.grid = grid
        self.room = room
        # Tres puntos de salida alrededor de A (uno por carrito) y una única meta
        self.starts = [self.idx(1, 1), self.idx(1, room), self.idx(room, 1)]
        self.goal = self.idx(W - 2, H - 2)

        # Grafo
        self.nbrs = {}
        for r in range(H):
            for c in range(W):
                if grid[r][c] == 0:
                    i = self.idx(c, r)
                    lst = []
                    for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        cc, rr = c + dc, r + dr
                        if 0 <= cc < W and 0 <= rr < H and grid[rr][cc] == 0:
                            lst.append(self.idx(cc, rr))
                    self.nbrs[i] = lst
        self.open_cells = sorted(self.nbrs)

    @classmethod
    def from_env(cls):
        """Todos los contenedores usan las mismas variables MAZE_* -> mismo laberinto."""
        e = os.environ.get
        return cls(int(e("MAZE_CELLS_W", "14")), int(e("MAZE_CELLS_H", "14")),
                   int(e("MAZE_SEED", "7")), float(e("MAZE_BRAID", "0.20")))

    # ---- utilidades -------------------------------------------------------
    def idx(self, col, row):
        return row * self.W + col

    def rc(self, i):
        """(columna, fila) de un nodo."""
        return i % self.W, i // self.W

    def ek(self, a, b):
        """Clave entera de la arista no dirigida (a, b)."""
        return a * self.N + b if a < b else b * self.N + a

    def edges(self):
        out = set()
        for a, ns in self.nbrs.items():
            for b in ns:
                out.add(self.ek(a, b))
        return out

    def manhattan(self, a, b):
        ca, ra = self.rc(a)
        cb, rb = self.rc(b)
        return abs(ca - cb) + abs(ra - rb)

    def shortest(self, a, b):
        """Longitud (en celdas, incluyendo ambos extremos) de la ruta mínima por BFS."""
        dist = {a: 1}
        q = deque([a])
        while q:
            u = q.popleft()
            if u == b:
                return dist[u]
            for v in self.nbrs[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1
                    q.append(v)
        return None

    def shortest_path(self, a, b):
        prev = {a: None}
        q = deque([a])
        while q:
            u = q.popleft()
            if u == b:
                break
            for v in self.nbrs[u]:
                if v not in prev:
                    prev[v] = u
                    q.append(v)
        path, u = [], b
        while u is not None:
            path.append(u)
            u = prev[u]
        return path[::-1]
