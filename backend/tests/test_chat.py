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
    nuevo = {**estado, "respuestas": j["respuestas"], "pregunta_pendiente": j["pregunta"], "ya_preguntado": j["ya_preguntado"]}
    if j["cambiar_anio"]:
        nuevo["anio_gravable"] = j["cambiar_anio"]
    return j, nuevo


class Charla:
    """Conversación de varios turnos con historial, como la manda el front."""

    def __init__(self, **estado):
        self.estado = {"anio_gravable": 2025, **estado}
        self.historial = []

    def __call__(self, mensaje):
        j, self.estado = _turno(mensaje, self.estado, self.historial)
        self.historial += [{"rol": "usuario", "texto": mensaje}, {"rol": "asistente", "texto": j["respuesta"]}]
        return j


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
    ch = Charla()
    j = ch("calcula")
    assert not j["calcular"] and "ingresos" in j["respuesta"] and j["pregunta"]["intencion"] == "calcular"
    j = ch("me pagan 5 millones")
    assert not j["anotaciones"] and "al mes o en todo el año" in j["respuesta"]  # cifra ambigua: pregunta
    j = ch("al mes")
    assert ch.estado["respuestas"]["salarios_no_reportados"] == 60_000_000
    j = ch("tengo dos hijos, y un carro de 40 millones")
    assert ch.estado["respuestas"]["dependientes"] == 2
    assert ch.estado["respuestas"]["bienes_adicionales"][0]["valor"] == 40_000_000
    j = ch("tengo que declarar?")
    assert "no estás obligado" in j["respuesta"]  # lo decide el motor con sus datos
    j = ch("calcula")
    assert not j["calcular"] and "Antes de calcular" in j["respuesta"]  # pregunta lo que cambia el resultado
    assert set(j["pregunta"]["temas"]) == {"retenciones", "cedula"}
    j = ch("no me hicieron retención y mi cédula termina en 21")
    assert j["calcular"] and ch.estado["respuestas"]["ultimos_dos_digitos_nit"] == "21"  # retoma: calcula
    j = ch("cuando vence?")
    assert "terminada en 21" in j["respuesta"]
    j = ch("calcula de nuevo")
    assert j["calcular"]  # ya preguntó: no vuelve a preguntar

    r = c.post("/api/declaracion/liquidar", json={"anio_gravable": 2025, "filas": [], "topes": {}, "respuestas": ch.estado["respuestas"]})
    resultado = [line for line in r.text.splitlines() if line.startswith("data:") and "liquidacion" in line]
    assert resultado and "Estimamos tus aportes" in resultado[0]


def test_calcula_asi_no_pregunta():
    ch = Charla(respuestas={"salarios_no_reportados": 60_000_000})
    assert ch("calcula así")["calcular"]


def test_pregunta_por_su_caso_y_retoma():
    ch = Charla()
    j = ch("¿tengo que declarar?")
    assert "$69.718.600" in j["respuesta"] and j["pregunta"]["intencion"] == "obligacion"
    j = ch("gano 9 millones mensuales y tengo un apartamento de 250 millones")
    assert "sí estás obligado" in j["respuesta"]
    ch = Charla()
    j = ch("cuándo vence mi declaración?")
    assert j["pregunta"]["temas"] == ["cedula"]
    j = ch("termina en 21")
    assert "27 de agosto de 2026" in j["respuesta"]


def test_respuestas_cortas_a_sus_preguntas():
    ch = Charla(respuestas={"salarios_no_reportados": 144_000_000})
    j = ch("calcula")
    assert "dependientes" in j["pregunta"]["temas"]
    j = ch("sí")
    assert "Cuántas" in j["respuesta"] and not j["calcular"]  # "sí" sin número: pregunta cuántas
    j = ch("dos")
    assert ch.estado["respuestas"]["dependientes"] == 2 and j["calcular"]
    ch = Charla()
    j = ch("8 millones")
    assert j["pregunta"]["temas"] == ["concepto"]
    j = ch("es lo que vale mi carro")
    assert ch.estado["respuestas"]["bienes_adicionales"][0]["valor"] == 8_000_000


def test_simula_sin_cambiar_los_datos():
    ch = Charla(respuestas={"salarios_no_reportados": 144_000_000})
    j = ch("y si pagara prepagada de 500 mil al mes?")
    assert j["simulacion"] and j["simulacion"]["impuesto_despues"] < j["simulacion"]["impuesto_antes"]
    assert "te ahorrarías" in j["respuesta"] and ch.estado["respuestas"]["medicina_prepagada"] == 0


def test_corrige_y_quita():
    ch = Charla()
    ch("tengo un carro de 40 millones y un apartamento de 200 millones")
    j = ch("ya no tengo el carro")
    assert j["quitadas"] == ["Bien: Carro"] and len(ch.estado["respuestas"]["bienes_adicionales"]) == 1
    j = ch("quita la moto")
    assert "No tenía eso anotado" in j["respuesta"]


def test_obligado_con_sus_datos():
    j, _ = _turno("gano 8 millones al mes, tengo que declarar?", {"anio_gravable": 2025})
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


def test_retoma_lo_que_queria_aunque_pregunte_otra_cosa_en_medio():
    ch = Charla()
    j = ch("y yo tengo que declarar?")
    assert j["pregunta"]["intencion"] == "obligacion"
    j = ch("me gano como 3 millones y medio")
    assert "$3.500.000" in j["respuesta"] and j["pregunta"]["intencion"] == "obligacion"  # pregunta el periodo sin olvidar el objetivo
    j = ch("al mes")
    assert ch.estado["respuestas"]["salarios_no_reportados"] == 42_000_000 and "no estás obligado" in j["respuesta"]


def test_calcula_sin_datos_pide_ingresos_y_luego_pregunta_lo_que_cambia_el_resultado():
    ch = Charla()
    j = ch("calcula cuanto me toca pagar")
    assert j["respuesta"].startswith("Para calcular necesito tus ingresos") and not j["fuentes"]
    j = ch("8 millones mensuales de salario")
    assert not j["calcular"] and "Antes de calcular" in j["respuesta"]  # una ronda de preguntas antes de calcular
    j = ch("me retuvieron 4.800.000")
    assert j["calcular"]  # respondió: calcula con lo que hay


def test_no_se_no_se_anota_como_cero():
    ch = Charla(respuestas={"honorarios_no_reportados": 90_000_000})
    ch("calcula")
    j = ch("no sé")
    assert j["calcular"] and not j["anotaciones"]


def test_tengo_hijos_sin_numero_pregunta_cuantos():
    ch = Charla()
    j = ch("tengo hijos")
    assert j["respuesta"] == "¿Cuántas personas dependen económicamente de ti?"
    ch("3")
    assert ch.estado["respuestas"]["dependientes"] == 3


def test_que_es_eso_de_la_renta():
    j, _ = _turno("que es eso de la renta?", {"anio_gravable": 2025})
    assert j["fuentes"] == ["¿Qué es la declaración de renta?"]


def test_dato_sin_cifra_pregunta_cuanto():
    ch = Charla()
    j = ch("tengo un carro")
    assert "Cuánto vale" in j["respuesta"] and j["pregunta"]["temas"] == ["valor"]
    ch("unos 40 millones")
    assert ch.estado["respuestas"]["bienes_adicionales"][0] == {"concepto": "Carro", "valor": 40_000_000, "fuente": "chat"}
    j = ch("pago medicina prepagada")
    assert "al mes o en todo el año" in j["respuesta"]
    j = ch("300 mil al mes")
    assert ch.estado["respuestas"]["medicina_prepagada"] == 3_600_000
