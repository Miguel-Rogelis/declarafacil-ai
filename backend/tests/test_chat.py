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
    nuevo = {**estado, "respuestas": j["respuestas"], "pregunta_pendiente": j["pregunta"], "ya_preguntado": j["ya_preguntado"],
             "descartados": j["descartados"]}
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
    assert not j["calcular"] and "Antes de calcular" in j["respuesta"]  # retoma: primera ronda de lo que falta
    assert j["pregunta"]["temas"] == ["retenciones", "patrimonio"]
    j = ch("tengo dos hijos, y un carro de 40 millones")
    assert ch.estado["respuestas"]["dependientes"] == 2
    assert ch.estado["respuestas"]["bienes_adicionales"][0]["valor"] == 40_000_000
    assert "últimas cosas" in j["respuesta"] and j["pregunta"]["rondas"] == 2
    j = ch("tengo que declarar?")
    assert "no estás obligado" in j["respuesta"]  # lo decide el motor con sus datos
    j = ch("mi cédula termina en 21 y no vendí nada")
    assert j["calcular"] and ch.estado["respuestas"]["ultimos_dos_digitos_nit"] == "21"  # última ronda respondida: calcula
    j = ch("cuando vence?")
    assert "terminada en 21" in j["respuesta"]
    j = ch("calcula así")
    assert j["calcular"]

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
    assert ch.estado["respuestas"]["dependientes"] == 2 and not j["calcular"]  # todavía hay una ronda
    assert ch("calcula así")["calcular"]
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
    assert j["cambiar_anio"] == 2026  # AG 2026 ya está vigente (HU-37)
    j, _ = _turno("hazlo con las reglas del 2027", {"anio_gravable": 2025})
    assert j["cambiar_anio"] is None  # 2027 no tiene reglas todavía
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
    assert not j["calcular"] and j["pregunta"]["rondas"] == 2  # segunda ronda
    j = ch("no")
    assert j["calcular"]  # máximo dos rondas: calcula con lo que hay


def test_no_se_no_se_anota_como_cero():
    ch = Charla(respuestas={"honorarios_no_reportados": 90_000_000})
    ch("calcula")
    j = ch("no sé")
    assert not j["anotaciones"]
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
    assert "Cuánto pagaste por tu carro" in j["respuesta"] and j["pregunta"]["temas"] == ["valor"]
    ch("unos 40 millones")
    assert ch.estado["respuestas"]["bienes_adicionales"][0] == {"concepto": "Carro", "valor": 40_000_000, "fuente": "chat"}
    j = ch("pago medicina prepagada")
    assert "al mes o en todo el año" in j["respuesta"]
    j = ch("300 mil al mes")
    assert ch.estado["respuestas"]["medicina_prepagada"] == 3_600_000


# ---------- Con exógena: deduce, pregunta lo que no muestra y guía ----------

import json  # noqa: E402


def _estado_exogena(**extra):
    demo = c.get("/api/demo/exogena").content
    r = c.post("/api/documentos/analizar", files={"archivo": ("exo.xlsx", demo)}, data={"anio_gravable": "2025"})
    ext = next(json.loads(x[5:])["extraccion"] for x in r.text.splitlines() if x.startswith("data:") and '"extraccion"' in x)
    revisar = [f["detalle"] for f in ext["filas"] if f["tratamiento"] == "revisar"]
    return {"anio_gravable": 2025, "tiene_exogena": True, "anio_exogena": ext["anio"], "filas": ext["filas"], "topes": {**ext["topes"], **extra.pop("topes", {})},
            "resumen_exogena": ext["resumen_campos"], "perfil": ext["perfil"], "por_revisar": revisar,
            "respuestas": {"ultimos_dos_digitos_nit": ext["ultimos_dos_digitos_nit"]}, **extra}


def test_al_subir_la_exogena_deduce_y_pregunta_lo_que_no_muestra():
    e = _estado_exogena()
    d = c.post("/api/chat/diagnostico", json=e).json()
    assert "trabajas para COMERCIALIZADORA ANDINA S.A.S." in d["respuesta"] and "sí estás obligado" in d["respuesta"]
    assert "Ya vienen incluidos" in d["respuesta"] and "prepagada" in d["respuesta"]
    assert d["pregunta"]["temas"] == ["dependientes", "deducciones"] and d["widgets"] == ["revisar"]
    assert "¿Pagas intereses de un crédito del ICETEX o aportes voluntarios a pensión o AFC?" in d["respuesta"]  # no pregunta por lo que ya trae (prepagada, vivienda)
    ch = Charla(**{**e, "pregunta_pendiente": d["pregunta"], "ya_preguntado": d["ya_preguntado"]})
    j = ch("no, a ninguna")
    assert not j["calcular"] and "carro o moto" in j["respuesta"]  # la exógena no muestra vehículos
    j = ch("no")
    assert j["calcular"]


def test_consignaciones_que_no_cuadran():
    e = _estado_exogena(topes={"Tope 4 - Movimiento": 400_000_000})
    d = c.post("/api/chat/diagnostico", json=e).json()
    assert d["pregunta"]["temas"] == ["consignaciones"] and "no me cuadra" in d["respuesta"]
    ch = Charla(**{**e, "pregunta_pendiente": d["pregunta"], "ya_preguntado": d["ya_preguntado"]})
    j = ch("fue un préstamo de mi papá")
    assert "no es ingreso" in j["respuesta"]


def test_que_me_falta_y_documentos_de_su_caso():
    ch = Charla(**_estado_exogena())
    j = ch("qué me falta?")
    assert "me falta saber" in j["respuesta"] and j["pregunta"]
    j = ch("qué documentos necesito?")
    assert "formulario 220) de COMERCIALIZADORA ANDINA S.A.S." in j["respuesta"] and "BANCO EJEMPLO S.A." in j["respuesta"]
    assert j["respuesta"].count("\n– ") >= 5 and ".." not in j["respuesta"]  # una línea por documento


@pytest.mark.parametrize(
    ("pregunta", "seccion"),
    [("como saco el certificado del banco", "¿Cómo saco el certificado tributario del banco?"),
     ("donde pido el certificado 220", "¿Cómo saco el certificado de ingresos y retenciones?"),
     ("que valor le pongo a mi moto", "¿Qué valor le pongo a mi carro?"),
     ("como saco el certificado de porvenir", "¿Cómo saco el certificado de cesantías o de aportes voluntarios?")],
)
def test_guia_como_conseguir_cada_documento(pregunta, seccion):
    j, _ = _turno(pregunta, {"anio_gravable": 2025})
    assert j["fuentes"] == [seccion]


def test_venta_calcula_la_ganancia():
    ch = Charla(respuestas={"salarios_no_reportados": 60_000_000})
    j = ch("vendí mi carro en 50 millones")
    assert "En cuánto habías comprado" in j["respuesta"] and not j["anotaciones"]
    j = ch("en 40 millones")
    assert ch.estado["respuestas"]["ganancias_ocasionales"]["utilidad_venta_otros_activos"] == 10_000_000
    assert "ganancia de la venta es $10.000.000" in j["respuesta"]


# ---------- Respuestas rápidas del cuadro de preguntas ----------


def _con_pregunta(temas, texto, **estado):
    from app.agents.asistente import PreguntaPendiente, _completar_partes
    p = _completar_partes(PreguntaPendiente(texto=texto, temas=temas, intencion="calcular", rondas=1))
    return Charla(pregunta_pendiente=p.model_dump(), ya_preguntado=temas, respuestas={"salarios_no_reportados": 144_000_000}, **estado)


@pytest.mark.parametrize(
    ("tema", "texto", "opcion", "campo", "esperado"),
    [
        ("dependientes", "¿Alguien depende económicamente de ti?", "No, nadie", "dependientes", 0),
        ("dependientes", "¿Alguien depende económicamente de ti?", "Sí, 2 personas", "dependientes", 2),
        ("dependientes", "¿Cuántas personas dependen de ti?", "3", "dependientes", 3),
        ("historial", "¿Es la primera vez que declaras renta?", "Es la primera vez", "declaraciones_previas", 0),
        ("historial", "¿Es la primera vez que declaras renta?", "Es la segunda", "declaraciones_previas", 1),
        ("historial", "¿Es la primera vez que declaras renta?", "Ya llevo más de dos", "declaraciones_previas", 2),
        ("sanciones", "¿La DIAN te ha sancionado por declarar tarde en los últimos dos años?", "No", "sin_sanciones_ultimos_2_anios", True),
        ("sanciones", "¿La DIAN te ha sancionado por declarar tarde en los últimos dos años?", "Sí", "sin_sanciones_ultimos_2_anios", False),
    ],
)
def test_cada_respuesta_rapida_se_entiende(tema, texto, opcion, campo, esperado):
    ch = _con_pregunta([tema], texto)
    assert opcion in ch.estado["pregunta_pendiente"]["partes"][0]["opciones"]
    ch(opcion)
    assert ch.estado["respuestas"][campo] == esperado


def test_respuestas_rapidas_de_periodo_concepto_y_consignaciones():
    ch = Charla()
    j = ch("me pagan 4 millones")
    assert j["pregunta"]["partes"][0]["opciones"] == ["Al mes", "En todo el año"] and j["texto_visible"] == ""
    ch("En todo el año")
    assert ch.estado["respuestas"]["salarios_no_reportados"] == 4_000_000
    ch = Charla()
    j = ch("2 millones")
    assert "Salario" in j["pregunta"]["partes"][0]["opciones"]
    j = ch("Arriendo")
    assert j["pregunta"]["partes"][0]["opciones"] == ["Al mes", "En todo el año"]  # sigue con el periodo
    ch = _con_pregunta(["consignaciones"], "¿De dónde salió la diferencia?")
    assert "no es ingreso" in ch("Pasé plata entre mis cuentas")["respuesta"]


def test_ronda_antes_de_calcular_trae_una_parte_por_dato():
    ch = Charla(respuestas={"salarios_no_reportados": 144_000_000})
    j = ch("calcula")
    partes = j["pregunta"]["partes"]
    assert len(partes) == 2 and all(p["texto"].endswith("?") or p["texto"].endswith(".") for p in partes)
    assert j["pregunta"]["intro"].startswith("Antes de calcular") and "calcula así" not in j["texto_visible"]
    j = ch(". ".join(p["opciones"][0] for p in partes))  # el cuadro manda las respuestas juntas
    assert j["anotaciones"] or j["pregunta"] or j["calcular"]


# ---------- Toma bien la información y pide solo lo que falta ----------


def _anotado(j, clave):
    return next((a for a in j["anotaciones"] if a["clave"] == clave), None)


def test_retencion_mensual_se_anota_y_no_se_vuelve_a_pedir():
    ch = Charla()
    ch("soy empleado y gano 4.500.000 al mes")
    j = ch("me retienen como 150 mil cada mes")
    assert _anotado(j, "retenciones")["valor"] == "$1.800.000"
    j = ch("calcula")
    assert "retencion" not in asistente.norm(j["respuesta"])


def test_independiente_que_factura_y_tiene_gastos():
    j = Charla()("soy independiente, facturé 95 millones el año pasado y tuve gastos de 20 millones")
    assert _anotado(j, "honorarios")["valor"] == "$95.000.000"
    assert _anotado(j, "costos_independiente")["valor"] == "$20.000.000"


def test_lo_que_dice_que_no_tiene_no_se_vuelve_a_preguntar():
    ch = Charla()
    ch("soy independiente, facturé 95 millones el año pasado")
    j = ch("no me hicieron retención")
    assert "no te hicieron retencion" in asistente.norm(j["respuesta"])
    assert next(i for i in j["ficha"] if i["tema"] == "retenciones")["estado"] == "no_aplica"
    j = ch("calcula")
    assert "retencion" not in asistente.norm(j["respuesta"])


@pytest.mark.parametrize(("mensaje", "n"), [
    ("mi mamá vive conmigo y yo la mantengo", 1),
    ("mantengo a mis papás", 2),
    ("tengo 2 hijos y mi mamá depende de mí", 3),
])
def test_familiares_a_cargo(mensaje, n):
    assert _anotado(Charla()(mensaje), "dependientes")["valor"] == str(n)


def test_corrige_la_ultima_cifra_con_su_periodo():
    ch = Charla()
    ch("gano 5 millones al mes")
    j = ch("no, perdón, eran 4 millones no 5")
    assert _anotado(j, "salarios")["valor"] == "$48.000.000"


def test_deuda_con_el_banco_tiene_nombre():
    j = Charla()("tengo un apartamento que vale 280 millones y le debo al banco 120 millones")
    assert any(a["etiqueta"] == "Deuda: Crédito con el banco" for a in j["anotaciones"])


def test_ficha_muestra_lo_que_tiene_y_lo_que_falta():
    j = Charla()("gano 3 millones al mes y mi cédula termina en 21")
    estados = {i["tema"]: i["estado"] for i in j["ficha"]}
    assert estados["ingresos"] == "tengo" and estados["cedula"] == "tengo"
    assert estados["patrimonio"] == "falta"


# ---------- Batería de frases como las escribe la gente ----------


@pytest.mark.parametrize(("mensaje", "clave", "valor"), [
    ("en todo el 2025 me pagaron 62 millones de salario", "salarios", "$62.000.000"),
    ("pago intereses del credito de vivienda, como 900 mil al mes", "intereses_vivienda", "$10.800.000"),
    ("soy pensionado, me llegan 2.800.000 al mes", "pension", "$33.600.000"),
    ("tengo un trabajo donde gano 4 millones al mes y aparte hago consultorias por 2 millones al mes", "honorarios", "$24.000.000"),
    ("arriendo un local por 2 millones al mes y pago 3 millones de predial y administracion al año por ese local", "costos_arriendos", "$3.000.000"),
    ("gano 5 millones mensuales y me dieron 5 millones de cesantias", "cesantias", "$5.000.000"),
    ("vendi mi carro en 40 millones, lo habia comprado en 35", "venta_otros_activos", "$5.000.000"),
])
def test_frases_reales_se_anotan_bien(mensaje, clave, valor):
    a = _anotado(Charla()(mensaje), clave)
    assert a and a["valor"] == valor


def test_me_retuvieron_no_se_confunde_con_no_me_retuvieron():
    ch = Charla()
    ch("gano 8 millones al mes")
    j = ch("en el año me retuvieron 6 millones")
    assert _anotado(j, "retenciones")["valor"] == "$6.000.000"
    assert "no te hicieron" not in asistente.norm(j["respuesta"])


def test_venta_con_compra_en_otro_mensaje_sin_millones():
    ch = Charla()
    ch("vendi un lote en 120 millones")
    assert _anotado(ch("lo compre en 80"), "venta_otros_activos")["valor"] == "$40.000.000"


def test_cuando_me_toca_pregunta_la_cedula_para_la_fecha():
    j = Charla()("cuando me toca declarar?")
    assert "cedula" in j["pregunta"]["temas"]


@pytest.mark.parametrize("mensaje", ["debo 8 millones en la tarjeta de credito", "como contratista me pagan 6 millones al mes por prestacion de servicios"])
def test_un_dato_no_se_toma_como_pregunta(mensaje):
    assert asistente.norm(Charla()(mensaje)["respuesta"]) == "listo, lo anote."


def test_cesantias_del_chat_tienen_su_exencion():
    from app.orquestador import SolicitudLiquidacion, construir_declaracion
    from app.tax.motor import liquidar
    sol = SolicitudLiquidacion(respuestas=Respuestas(salarios_no_reportados=60_000_000, cesantias_no_reportadas=5_000_000))
    liq = liquidar(construir_declaracion(sol))
    lineas = {l.clave: l.valor for s in liq.secciones for l in s.lineas}
    assert lineas["cesantias_exentas"] > 0


# ---------- Respuestas en vivo ----------


def test_lector_saca_la_respuesta_mientras_llega():
    lector = asistente._LectorRespuesta()
    crudo = '{"respuesta": "Listo, anoté \\"4 millones\\" al mes.", "anotar": []}'
    salida = "".join(lector.nuevo_texto(crudo[i:i + 3]) for i in range(0, len(crudo), 3))
    assert salida == 'Listo, anoté "4 millones" al mes.'


def test_chat_en_vivo_termina_con_la_respuesta_validada():
    r = c.post("/api/chat/en-vivo", json={"mensaje": "gano 4 millones al mes", "estado": {"anio_gravable": 2025}})
    assert r.status_code == 200
    assert "event: final" in r.text and "Salarios del año" in r.text


def test_ficha_sin_ingresos_no_da_nada_por_listo():
    j = Charla()("hola, ¿tengo que declarar renta?")
    assert all(i["estado"] == "falta" for i in j["ficha"])


# ---------- Datos nuevos: factura electrónica, intereses, exterior, PILA ----------


@pytest.mark.parametrize(("mensaje", "clave", "valor"), [
    ("gano 6 millones al mes y compré como 30 millones con factura electrónica a mi nombre", "compras_factura", "$30.000.000"),
    ("el CDT me dio 2 millones de intereses en el año", "rendimientos", "$2.000.000"),
    ("soy independiente, facturo 8 millones al mes y pago 1.100.000 al mes de la PILA", "aportes_independiente", "$13.200.000"),
])
def test_datos_nuevos_se_anotan(mensaje, clave, valor):
    a = _anotado(Charla()(mensaje), clave)
    assert a and a["valor"] == valor


def test_cripto_y_cuenta_afuera_van_al_patrimonio():
    j = Charla()("tengo 15 millones en bitcoin y una cuenta en Estados Unidos con 40 millones")
    etiquetas = {a["etiqueta"] for a in j["anotaciones"]}
    assert "Bien: Criptomonedas" in etiquetas
    assert any("exterior" in x for x in etiquetas)
    assert next(i for i in j["ficha"] if i["tema"] == "exterior")["estado"] == "tengo"


def test_no_tengo_nada_de_eso_responde_lo_que_se_pregunto():
    assert set(asistente.descartes("No tengo nada de eso", ["factura", "rendimientos"])) == {"factura", "rendimientos"}
    assert asistente.descartes("No tengo nada de eso") == []
    assert asistente.descartes("ninguna de esas", ["deducciones"]) == ["deducciones"]


def test_aportes_pila_bajan_la_base():
    from app.orquestador import SolicitudLiquidacion, construir_declaracion
    d = construir_declaracion(SolicitudLiquidacion(respuestas=Respuestas(honorarios_no_reportados=90e6, aportes_independiente=12e6)))
    assert round(d.independiente.aportes_obligatorios_salud + d.independiente.aportes_obligatorios_pension) == 12_000_000


def test_mas_de_2000_uvt_afuera_pide_formulario_160():
    from app.orquestador import SolicitudLiquidacion, construir_declaracion
    from app.agents import auditor
    from app.tax import reglas
    from app.tax.modelos import ItemPatrimonio
    from app.tax.motor import liquidar
    r = Respuestas(salarios_no_reportados=80e6, bienes_adicionales=[ItemPatrimonio(concepto="Cuentas bancarias en el exterior", valor=150e6)])
    d = construir_declaracion(SolicitudLiquidacion(respuestas=r))
    liq = liquidar(d, reglas.cargar(2025))
    assert any("160" in a.titulo for a in auditor.auditar(d, liq, []))


def test_preguntar_por_entrar_por_primera_vez_no_es_su_historial():
    j = Charla()("¿cómo entro a muisca por primera vez?")
    assert not _anotado(j, "declaraciones_previas")
    assert "historial" not in j["descartados"]
    assert _anotado(Charla()("es la primera vez que declaro"), "declaraciones_previas")


def test_bitcoin_de_la_ia_queda_como_criptomonedas():
    r, hechas, _ = asistente.aplicar(Respuestas(), [{"campo": "bien", "concepto": "Bitcoin", "valor": "10 millones"}], "tengo 10 millones en bitcoin")
    assert r.bienes_adicionales[0].concepto == "Criptomonedas" and hechas


def test_el_160_no_se_menciona_por_debajo_del_tope(monkeypatch):
    async def falso(t, vp, al_texto=None):
        plan = asistente._Plan()
        plan.respuesta = "Listo, lo anoté. Como tienes más de 2.000 UVT afuera, debes presentar el formulario 160."
        plan.anotar = [{"campo": "bien", "concepto": "Bitcoin", "valor": "10 millones"}]
        return plan, "falso"
    monkeypatch.setattr(asistente.cliente, "disponible", lambda: True)
    monkeypatch.setattr(asistente, "_con_ia", falso)
    j = Charla()("tengo 10 millones en bitcoin")
    assert "160" not in j["respuesta"] and j["respuesta"].startswith("Listo")


# ---------- HU-39: rentas del exterior y comparación patrimonial desde el chat (sin IA) ----------


def test_anota_pension_del_exterior_al_mes():
    j, _ = _turno("recibo una pensión de Estados Unidos de 5 millones al mes", {"anio_gravable": 2025})
    assert j["respuestas"]["exterior"]["pensiones"] == 60_000_000


def test_anota_impuesto_pagado_en_el_exterior():
    j, _ = _turno("pagué 3 millones de impuestos en el exterior", {"anio_gravable": 2025})
    assert j["respuestas"]["exterior"]["impuesto_pagado_renta"] == 3_000_000


def test_anota_patrimonio_liquido_del_anio_pasado():
    j, _ = _turno("mi patrimonio líquido del año pasado era de 200 millones", {"anio_gravable": 2025})
    assert j["respuestas"]["comparacion"]["patrimonio_liquido_anterior"] == 200_000_000
