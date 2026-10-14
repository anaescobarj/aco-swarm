"""Punto de acceso (ESP32 en modo AP) simulado.

Un ESP32 en modo SoftAP crea la red 192.168.4.0/24 (el AP es 192.168.4.1) y
las estaciones (los otros ESP32 + el gemelo digital) se asocian a él.
Aquí el AP es un relé UDP: cada datagrama recibido se reenvía a todas las
demás estaciones registradas, con latencia y pérdida de paquetes configurables
para emular el canal WiFi.

Variables de entorno: AP_PORT (5000), AP_LOSS (0.02), AP_LATENCY_MS (15),
AP_JITTER_MS (10)
"""
import heapq
import os
import random
import socket
import threading
import time

from common.net import decode

PORT = int(os.environ.get("AP_PORT", "5000"))
LOSS = float(os.environ.get("AP_LOSS", "0.02"))
LATENCY = float(os.environ.get("AP_LATENCY_MS", "15")) / 1000.0
JITTER = float(os.environ.get("AP_JITTER_MS", "10")) / 1000.0

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", PORT))

stations = {}          # addr -> nombre
queue = []             # heap de (t_envio, seq, data, addr_destino)
cv = threading.Condition()
seq = 0
stats = {"rx": 0, "fwd": 0, "dropped": 0}


def sender():
    while True:
        with cv:
            while not queue or queue[0][0] > time.time():
                timeout = None if not queue else max(0.0, queue[0][0] - time.time())
                cv.wait(timeout)
            _, _, data, dst = heapq.heappop(queue)
        try:
            sock.sendto(data, dst)
            stats["fwd"] += 1
        except OSError:
            pass


def name_of(msg, addr):
    t = msg.get("t")
    if t in ("hello", "pher", "route"):
        return "nodo%s" % msg.get("n")
    return "gemelo" if t in ("go", "ack", "twin") else "sta%s" % addr[1]


def main():
    global seq
    threading.Thread(target=sender, daemon=True).start()
    print("[AP] SSID=ESP32-ACO escuchando en UDP/%d  loss=%.0f%%  lat=%.0f±%.0f ms"
          % (PORT, LOSS * 100, LATENCY * 1000, JITTER * 1000), flush=True)
    last = time.time()
    while True:
        data, addr = sock.recvfrom(2048)
        stats["rx"] += 1
        msg = decode(data)
        if msg is None:
            continue
        if addr not in stations:
            stations[addr] = name_of(msg, addr)
            print("[AP] estación asociada: %s (%s:%d)  total=%d"
                  % (stations[addr], addr[0], addr[1], len(stations)), flush=True)
        for dst in list(stations):
            if dst == addr:
                continue
            if random.random() < LOSS and msg.get("t") not in ("hello", "go", "ack"):
                stats["dropped"] += 1
                continue
            delay = max(0.0, LATENCY + random.uniform(-JITTER, JITTER))
            with cv:
                seq += 1
                heapq.heappush(queue, (time.time() + delay, seq, data, dst))
                cv.notify()
        if time.time() - last > 5:
            last = time.time()
            print("[AP] rx=%d fwd=%d perdidos=%d estaciones=%d"
                  % (stats["rx"], stats["fwd"], stats["dropped"], len(stations)), flush=True)


if __name__ == "__main__":
    main()
