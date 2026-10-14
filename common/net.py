"""Protocolo de red muy liviano (JSON sobre UDP) pensado para un ESP32.

Mensajes (campo "t" = tipo, "n" = id del nodo):
  hello  {"t":"hello","n":1}                      -> el nodo se anuncia en el AP
  go     {"t":"go"}                               -> el gemelo ordena iniciar el ACO
  pher   {"t":"pher","n":1,"i":12,"len":47,"b":45,"p":[...]}
                                                  -> mejor ruta de la iteración i (feromona)
  route  {"t":"route","n":1,"i":57,"len":45,"p":[...]}
                                                  -> ruta final del carrito
  ack    {"t":"ack","n":1}                        -> el gemelo confirma la ruta
"""
import json
import socket

MAX_DGRAM = 1400


def encode(obj):
    data = json.dumps(obj, separators=(",", ":")).encode()
    if len(data) > MAX_DGRAM:
        raise ValueError("datagrama demasiado grande (%d B)" % len(data))
    return data


def decode(data):
    try:
        return json.loads(data.decode())
    except Exception:
        return None


def make_socket(bind_port=0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", bind_port))
    s.setblocking(False)
    return s


def drain(sock):
    """Lee todos los datagramas pendientes sin bloquear."""
    msgs = []
    while True:
        try:
            data, addr = sock.recvfrom(2048)
        except (BlockingIOError, InterruptedError):
            break
        except OSError:
            break
        m = decode(data)
        if m is not None:
            msgs.append((m, addr))
    return msgs
