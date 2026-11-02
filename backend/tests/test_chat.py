"""Conversación sin IA (modo simulado): el usuario puede preguntar lo que sea y armar la declaración hablando."""

import os

os.environ["LLM_MODE"] = "simulado"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agents import numeros  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("300 mil", 300_000), ("$3.600.000", 3_600_000), ("1,5 millones", 1_500_000), ("2 palos", 2_000_000), ("500 lucas", 500_000),
     ("un millón", 1_000_000), ("medio millón", 500_000), ("1 millón 500 mil", 1_500_000), ("dos hijos", 2)],
)
def test_lee_cantidades_como_las_escribe_la_gente(texto, esperado):
    assert esperado in numeros.cantidades(texto)


def test_cifra_mensual_se_reconoce():
    assert numeros.aparece(4_200_000, "pago 350 mil al mes")
    assert not numeros.aparece(9_000_000, "pago 350 mil al mes")


def _turno(mensaje, estado, historial=None):
    r = c.post("/api/chat", json={"mensaje": mensaje, "historial": historial or [], "estado": estado})
    assert r.status_code == 200, r.text
    j = r.json()
    estado = {**estado, "respuestas": j["respuestas"], "temas_cubiertos": j["temas_cubiertos"]}
    return j, estado


def test_preguntas_basicas_sin_subir_nada():
    j, _ = _turno("¿qué es la DIAN?", {"anio_gravable": 2025})
    assert "Impuestos y Aduanas" in j["respuesta"]
    j, _ = _turno("me pueden meter a la cárcel?", {"anio_gravable": 2025})
    assert "cárcel" in j["respuesta"] or "sanciones" in j["respuesta"]


def test_armar_la_declaracion_solo_conversando_y_calcular():
    e = {"anio_gravable": 2025, "pantalla": "declarar"}
    j, e = _turno("No lo tengo", e)
    assert "exogena" in e["temas_cubiertos"]
    j, e = _turno("Gano 5 millones al mes", e)
    assert e["respuestas"]["salarios_no_reportados"] == 60_000_000
    j, e = _turno("tengo dos hijos", e)
    assert e["respuestas"]["dependientes"] == 2
    j, e = _turno("Prepagada de 350 mil al mes", e)
    assert e["respuestas"]["medicina_prepagada"] == 4_200_000
    j, e = _turno("nada más", e)
    assert "gastos" in e["temas_cubiertos"]
    j, e = _turno("No, nada más", e)
    assert "otros" in e["temas_cubiertos"]
    j, e = _turno("Es la primera vez", e)
    j, e = _turno("termina en 21", e)
    assert e["respuestas"]["ultimos_dos_digitos_nit"] == "21"
    assert "calcular" in j["widgets"]

    r = c.post("/api/declaracion/liquidar", json={"anio_gravable": 2025, "filas": [], "topes": {}, "respuestas": e["respuestas"]})
    resultado = [line for line in r.text.splitlines() if line.startswith("data:") and "liquidacion" in line]
    assert resultado and "Estimamos tus aportes" in resultado[0]


def test_siguiente_pregunta_sin_ia():
    r = c.post("/api/chat/siguiente", json={"tiene_exogena": True, "por_revisar": ["Activos aportes parafiscales"]})
    assert r.json()["tema"] == "revisar" and "revisar" in r.json()["widgets"]


def test_cambiar_de_anio_solo_a_vigentes():
    from app.agents.asistente import aplicar
    from app.orquestador import Respuestas

    nuevas, hechas, rechazadas, _ = aplicar(Respuestas(), [{"campo": "ultimos_dos_digitos_cedula", "valor": "1012345678"}], "mi cédula es 1012345678")
    assert nuevas.ultimos_dos_digitos_nit == "78"  # solo se guardan los dos últimos dígitos
