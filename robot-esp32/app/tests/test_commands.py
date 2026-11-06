import pytest

from commands import parse


@pytest.mark.parametrize("text,kind,params", [
    ("Arriba", "move", {"move": "forward"}),
    ("abajo por favor", "move", {"move": "backward"}),
    ("Derecha", "move", {"move": "right"}),
    ("izquierda", "move", {"move": "left"}),
    ("¡Detente!", "stop", {}),
    ("alto", "stop", {}),
    ("modo automático", "mode", {"m": "auto", "nav": "linea"}),
    ("modo autónomo por rumbo", "mode", {"m": "auto", "nav": "rumbo"}),
    ("modo manual", "mode", {"m": "manual"}),
    ("rumbo 90", "heading", {"deg": 90}),
    ("oriéntate al sur", "heading", {"deg": 180}),
    ("rumbo noventa", "heading", {"deg": 90}),
    ("gira 45 grados a la derecha", "heading_rel", {"rel": 45}),
    ("gira treinta grados a la izquierda", "heading_rel", {"rel": -30}),
    ("calibra la brújula", "calibrate", {"what": "compass"}),
])
def test_parse(text, kind, params):
    a = parse(text)
    assert a is not None and a.kind == kind
    for k, v in params.items():
        assert a.params[k] == v


def test_duration():
    a = parse("avanza 2 segundos")
    assert a.params == {"move": "forward", "ms": 2000}


def test_unknown():
    assert parse("hola qué tal") is None
    assert parse("") is None
