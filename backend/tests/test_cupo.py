"""Cupo de IA: un link público no puede gastarse las llamadas gratis del día."""

import pytest

from app.llm import cupo


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    cupo.reiniciar()
    monkeypatch.setattr(cupo, "POR_HORA", 3)
    monkeypatch.setattr(cupo, "TOPE_DIARIO", 5)
    yield
    cupo.reiniciar()


def test_cada_persona_tiene_su_limite_por_hora():
    cupo.quien.set("1.1.1.1")
    assert [cupo.reservar() for _ in range(4)] == [True, True, True, False]
    assert cupo.limitado.get()
    cupo.quien.set("2.2.2.2")
    cupo.limitado.set(False)
    assert cupo.reservar()


def test_tope_diario_para_todos():
    for i in range(5):
        cupo.quien.set(f"persona-{i}")
        assert cupo.reservar()
    cupo.quien.set("otra")
    assert not cupo.reservar()
    assert cupo.restante_hoy() == 0


def test_modo_demo_no_usa_ia():
    cupo.sin_ia.set(True)
    try:
        assert not cupo.reservar()
        assert cupo.restante_hoy() == 5
    finally:
        cupo.sin_ia.set(False)
