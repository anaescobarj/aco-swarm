"""Valida la lógica autónoma en el gemelo digital para los tres niveles de la meta final."""
import threading
from http.server import ThreadingHTTPServer

import pytest

from commands import parse
from robot_client import RobotClient
from simulator import LEVELS, SimRobot, make_handler


def run_auto(level: int, seconds: float):
    r = SimRobot(level)
    r.handle("/api/mode", {"m": ["auto"]})
    n = len(r.world.track)
    last, prog = r.world.nearest(r.x, r.y)[0], 0
    for _ in range(int(seconds / 0.05)):
        r.step()
        i, _ = r.world.nearest(r.x, r.y)
        prog += (i - last + n // 2) % n - n // 2
        last = i
    return r, prog / n


@pytest.mark.parametrize("level", [1, 2, 3])
def test_full_lap_without_collisions(level):
    r, laps = run_auto(level, 90)
    assert laps >= 1.0, f"no completó una vuelta ({laps:.2f})"
    assert r.collisions == 0
    assert r.obstacles_avoided >= LEVELS[level]["obstacles"]
    assert r.color_changes >= len(LEVELS[level]["colors"])


def test_manual_and_safety_stop():
    r = SimRobot(1)
    r.handle("/api/cmd", {"move": ["forward"], "speed": ["80"], "ms": ["1000"]})
    x0 = r.x
    for _ in range(10):
        r.step()
    assert r.mode == "MANUAL" and abs(r.x - x0) > 0.02
    for _ in range(30):
        r.step()
    assert r.pwm_l == 0 and r.pwm_r == 0           # el pulso expiró: se detiene solo


def test_http_api_roundtrip():
    robot = SimRobot(1)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(robot))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = RobotClient(f"http://127.0.0.1:{srv.server_port}")
        s = c.state()
        for key in ("heading", "heading_des", "dist_cm", "color", "line", "mode", "batt_v"):
            assert key in s
        c.execute(parse("rumbo 135"))
        assert c.state()["heading_des"] == 135
        c.execute(parse("modo automático"))
        assert c.state()["mode"] == "AUTO"
        c.execute(parse("detente"))
        assert c.state()["mode"] == "MANUAL"
        assert c.track()["level"] == 1
    finally:
        srv.shutdown()
