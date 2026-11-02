"""Conversación sin IA (modo simulado): el usuario lleva la conversación y el agente responde directo."""

import os

os.environ["LLM_MODE"] = "simulado"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agents import asistente, numeros  # noqa: E402
from app.main import app  # noqa: E402
from app.orquestador import Respuestas  # noqa: E402

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
    assert "sugerencias" not in j  # el agente no sugiere preguntas
    return j, {**estado, "respuestas": j["respuestas"]}


@pytest.mark.parametrize(
    ("pregunta", "debe_decir"),
    [
        ("Hola, como se que tengo q declarar renta?", "$69.718.600"),
        ("no, estoy preguntando como se o como investigo si declaro renta", "descarga el reporte de información exógena"),
        ("¿qué es la DIAN?", "Impuestos y Aduanas"),
        ("me pueden meter a la cárcel?", "no cárcel"),
        ("declarar es pagar?", "No."),
        ("que necesito para declarar", "formulario 220"),
        ("que pasa si me equivoco", "corregirla"),
        ("¿Cómo descargo mi exógena?", "MUISCA"),
    ],
)
def test_responde_directo_lo_que_se_pregunta(pregunta, debe_decir):
    j, _ = _turno(pregunta, {"anio_gravable": 2025})
    assert debe_decir in j["respuesta"]
    assert not j["respuesta"].rstrip().endswith("?")  # no remata con preguntas para guiar


def test_lo_que_no_es_de_impuestos_no_inventa():
    j, _ = _turno("cual es el mejor equipo de futbol", {"anio_gravable": 2025})
    assert "declaración de renta" in j["respuesta"] and not j["fuentes"]


def test_las_respuestas_cambian_con_el_anio():
    j, _ = _turno("que es la uvt", {"anio_gravable": 2022})
    assert "$38.004" in j["respuesta"]
    j, _ = _turno("quienes cuentan como dependientes", {"anio_gravable": 2022})
    assert "empezó en el año gravable 2023" in j["respuesta"]
    j, _ = _turno("tengo que declarar?", {"anio_gravable": 2023})
    assert "$59.376.800" in j["respuesta"]  # 1.400 UVT de 2023


def test_armar_la_declaracion_hablando_y_calcular_cuando_lo_pide():
    e = {"anio_gravable": 2025, "pantalla": "declarar"}
    j, e = _turno("calcula", e)
    assert not j["calcular"] and "ingresos" in j["respuesta"]  # sin datos no calcula y dice qué falta
    j, e = _turno("Gano 5 millones al mes", e)
    assert e["respuestas"]["salarios_no_reportados"] == 60_000_000 and j["respuesta"] == "Listo, lo anoté."
    j, e = _turno("tengo dos hijos", e)
    assert e["respuestas"]["dependientes"] == 2
    j, e = _turno("Prepagada de 350 mil al mes, y tengo un carro de 40 millones", e)
    assert e["respuestas"]["medicina_prepagada"] == 4_200_000
    assert e["respuestas"]["bienes_adicionales"][0]["valor"] == 40_000_000
    j, e = _turno("es la primera vez que declaro y mi cédula termina en 21", e)
    assert e["respuestas"]["declaraciones_previas"] == 0 and e["respuestas"]["ultimos_dos_digitos_nit"] == "21"
    j, e = _turno("tengo que declarar?", e)
    assert "no estás obligado" in j["respuesta"]  # lo decide el motor con sus datos
    j, e = _turno("cuando vence?", e)
    assert "terminada en 21" in j["respuesta"]
    j, e = _turno("calcula cuánto me toca", e)
    assert j["calcular"]

    r = c.post("/api/declaracion/liquidar", json={"anio_gravable": 2025, "filas": [], "topes": {}, "respuestas": e["respuestas"]})
    resultado = [line for line in r.text.splitlines() if line.startswith("data:") and "liquidacion" in line]
    assert resultado and "Estimamos tus aportes" in resultado[0]


def test_obligado_con_sus_datos():
    e = {"anio_gravable": 2025}
    j, e = _turno("gano 8 millones al mes, tengo que declarar?", e)
    assert "sí estás obligado" in j["respuesta"] and "$96.000.000" in j["respuesta"]


def test_cambia_de_anio_cuando_lo_pide():
    j, _ = _turno("quiero declarar el 2023", {"anio_gravable": 2025})
    assert j["cambiar_anio"] == 2023
    j, _ = _turno("hazlo con las reglas del 2026", {"anio_gravable": 2025})
    assert j["cambiar_anio"] is None  # 2026 es borrador, no vigente
    j, _ = _turno("qué cambió con la reforma de 2022", {"anio_gravable": 2025})
    assert j["cambiar_anio"] is None and "1.340" in j["respuesta"]


def test_subir_exogena_abre_la_carga():
    j, _ = _turno("quiero subir mi exógena", {"anio_gravable": 2025})
    assert j["widgets"] == ["subir_exogena"]
    j, _ = _turno("no tengo la exógena", {"anio_gravable": 2025})
    assert not j["widgets"] and "ingresos" in j["respuesta"]


def test_solo_se_guardan_dos_digitos_de_la_cedula():
    nuevas, hechas, _ = asistente.aplicar(Respuestas(), [{"campo": "ultimos_dos_digitos_cedula", "valor": "1012345678"}], "mi cédula es 1012345678")
    assert nuevas.ultimos_dos_digitos_nit == "78"


def test_quita_ofrecimientos_del_final():
    assert asistente._limpiar("Es la DIAN. ¿Quieres que te explique más?") == "Es la DIAN."
    assert asistente._limpiar("**Sí.** Si quieres, te ayudo con eso.") == "Sí."
