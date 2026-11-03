"""Ejercita la ruta con IA usando un cliente falso de OpenRouter (sin red)."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.agents import anonimizador, asistente, explicador, interprete, lector
from app.config import settings
from app.llm import cliente
from app.tax.modelos import DatosDeclaracion
from app.tax.motor import liquidar
from tests.test_agentes import FIXTURE


class _Falso:
    def __init__(self, respuestas, fallar_primero=False):
        self.respuestas = respuestas
        self.llamadas = []
        self.fallar_primero = fallar_primero
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, model, messages, **kw):
        self.llamadas.append({"model": model, "messages": messages, **kw})
        if self.fallar_primero and len(self.llamadas) == 1:
            raise RuntimeError("429 rate limit")
        texto = self.respuestas(messages)
        return SimpleNamespace(model=model, choices=[SimpleNamespace(message=SimpleNamespace(content=texto))])


@pytest.fixture
def con_llm(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-prueba")

    def instalar(falso):
        monkeypatch.setattr(cliente, "_get_cliente", lambda: falso)
        return falso

    return instalar


def test_interprete_con_ia_no_recibe_montos_ni_datos_personales(con_llm):
    falso = con_llm(_Falso(lambda m: json.dumps({"conceptos": [
        {"i": 0, "campo": "laboral.salarios_y_pagos_laborales", "explicacion": "Bonos que te dio tu empleador; cuentan como ingreso laboral."},
        {"i": 1, "campo": "patrimonio.bienes", "explicacion": "Aportes reportados por tu empleador."},
    ]}), fallar_primero=True))
    anon, ult, n = anonimizador.anonimizar(lector.leer(FIXTURE.read_bytes(), "x.xlsx"))
    ext, modelo, enviados = asyncio.run(interprete.interpretar(anon, ult, n))
    prompt = json.dumps(falso.llamadas[-1]["messages"])
    assert "1012345678" not in prompt and "LAURA" not in prompt
    assert "1800000" not in prompt and "1.800.000" not in prompt  # sin montos
    assert len(falso.llamadas) == 2  # el primer modelo falló y pasó al siguiente
    assert modelo and enviados >= 1
    bonos = next(f for f in ext.filas if "bonos" in f.detalle)
    assert bonos.origen_mapeo == "ia" and bonos.campo == "laboral.salarios_y_pagos_laborales"
    assert bonos.valor == 1_800_000  # la cifra sale de la fila, no del modelo
    parafiscales = next(f for f in ext.filas if "parafiscales" in f.detalle)
    assert parafiscales.tratamiento == "revisar"  # la IA explica pero no puede aprobar lo que las reglas marcaron


def test_explicador_descarta_texto_con_cifras_inventadas(con_llm):
    liq = liquidar(DatosDeclaracion(laboral={"salarios_y_pagos_laborales": 120_000_000}))
    con_llm(_Falso(lambda m: "Debes pagar $9.999.999. " * 5))
    texto, modelo, con_ia = asyncio.run(explicador.explicar(liq, liq.alertas))
    assert not con_ia and "$9.999.999" not in texto

    bueno = f"Tu impuesto a cargo es de ${liq.resumen.total_impuesto_cargo:,.0f}. ".replace(",", ".") * 3
    con_llm(_Falso(lambda m: bueno))
    texto, modelo, con_ia = asyncio.run(explicador.explicar(liq, liq.alertas))
    assert con_ia and texto == bueno.strip()


def test_asistente_recibe_toda_la_base_y_responde_directo(con_llm):
    falso = con_llm(_Falso(lambda m: json.dumps({"respuesta": "Es un pago adelantado del impuesto del año siguiente. ¿Quieres que te explique cómo se calcula?",
                                                 "anotar": [], "calcular": False, "fuente": "¿Qué es el anticipo de renta?"})))
    r = asyncio.run(asistente.responder(asistente.TurnoChat(mensaje="¿Qué es el anticipo de renta?")))
    assert r.con_ia and r.respuesta == "Es un pago adelantado del impuesto del año siguiente."  # sin el ofrecimiento final
    assert r.fuentes == ["¿Qué es el anticipo de renta?"]
    llamada = falso.llamadas[0]
    sistema = llamada["messages"][0]["content"]
    assert "BASE DE CONOCIMIENTO" in sistema and "¿Puedo ir a la cárcel" in sistema  # toda la base, no solo coincidencias
    assert "$69.718.600" in sistema  # topes del año elegido
    assert llamada["extra_body"]["reasoning"]["exclude"] is True  # razonamiento corto y oculto


def test_asistente_descarta_cifras_inventadas(con_llm):
    con_llm(_Falso(lambda m: json.dumps({"respuesta": "Te toca pagar $7.777.777.", "anotar": []})))
    r = asyncio.run(asistente.responder(asistente.TurnoChat(mensaje="¿cuánto impuesto se paga?")))
    assert not r.con_ia and "7.777.777" not in r.respuesta  # se usó la ruta con reglas


def test_asistente_pregunta_antes_de_calcular(con_llm):
    con_llm(_Falso(lambda m: json.dumps({"respuesta": "Calculo tu borrador con lo que tengo.", "calcular": True})))
    r = asyncio.run(asistente.responder(asistente.TurnoChat(mensaje="calcula")))
    assert not r.calcular and "ingresos" in r.respuesta and r.pregunta.intencion == "calcular"
    e = asistente.EstadoChat(respuestas={"salarios_no_reportados": 60_000_000})
    r = asyncio.run(asistente.responder(asistente.TurnoChat(mensaje="calcula", estado=e)))
    assert not r.calcular and "Antes de calcular" in r.respuesta and "Calculo tu borrador" not in r.respuesta
    e = e.model_copy(update={"pregunta_pendiente": r.pregunta, "ya_preguntado": r.ya_preguntado})
    con_llm(_Falso(lambda m: json.dumps({"respuesta": "Listo, lo anoté.", "anotar": [{"campo": "ultimos_dos_digitos_cedula", "valor": "21"}]})))
    r = asyncio.run(asistente.responder(asistente.TurnoChat(mensaje="termina en 21 y no me retuvieron", estado=e)))
    assert r.calcular  # al responder, el agente retoma y calcula


def test_la_pregunta_del_modelo_queda_pendiente_y_la_cifra_sale_del_historial(con_llm):
    con_llm(_Falso(lambda m: json.dumps({"respuesta": "¿Esos 3 millones son al mes o en todo el año?", "pregunta": {"campos": ["salarios"], "intencion": None}})))
    r = asyncio.run(asistente.responder(asistente.TurnoChat(mensaje="me pagan 3 millones")))
    assert r.pregunta and r.pregunta.campo == "salarios" and r.pregunta.valor == 3_000_000 and not r.anotaciones
    e = asistente.EstadoChat(pregunta_pendiente=r.pregunta, ya_preguntado=r.ya_preguntado)
    con_llm(_Falso(lambda m: json.dumps({"respuesta": "Listo, lo anoté.", "anotar": [{"campo": "salarios", "valor": "3 millones", "periodo": "mensual"}]})))
    historial = [{"rol": "usuario", "texto": "me pagan 3 millones"}, {"rol": "asistente", "texto": r.respuesta}]
    r = asyncio.run(asistente.responder(asistente.TurnoChat(mensaje="al mes", historial=historial, estado=e)))
    assert r.respuestas.salarios_no_reportados == 36_000_000  # la cifra la dijo el usuario en el mensaje anterior


def test_si_el_modelo_no_dice_el_periodo_el_agente_pregunta(con_llm):
    con_llm(_Falso(lambda m: json.dumps({"respuesta": "Listo, lo anoté.", "anotar": [{"campo": "salarios", "valor": "5 millones"}]})))
    r = asyncio.run(asistente.responder(asistente.TurnoChat(mensaje="me pagan 5 millones")))
    assert not r.anotaciones and "al mes o en todo el año" in r.respuesta and "Listo" not in r.respuesta


def test_simulacion_con_ia(con_llm):
    con_llm(_Falso(lambda m: json.dumps({"respuesta": "Mira la diferencia:", "simular": [{"campo": "aportes_voluntarios", "valor": "1 millón", "periodo": "mensual"}]})))
    e = asistente.EstadoChat(respuestas={"salarios_no_reportados": 144_000_000})
    r = asyncio.run(asistente.responder(asistente.TurnoChat(mensaje="cuánto me ahorro si aportara 1 millón al mes a una AFC?", estado=e)))
    assert r.simulacion and r.simulacion.impuesto_despues < r.simulacion.impuesto_antes
    assert r.respuestas.aportes_voluntarios_afc_fpv == 0


def test_asistente_acepta_texto_plano(con_llm):
    con_llm(_Falso(lambda m: "La DIAN es la entidad que recibe las declaraciones."))
    r = asyncio.run(asistente.responder(asistente.TurnoChat(mensaje="que es la dian")))
    assert r.con_ia and r.respuesta.startswith("La DIAN")


def test_la_ia_no_puede_anotar_cifras_que_el_usuario_no_dijo(con_llm):
    con_llm(_Falso(lambda m: json.dumps({
        "respuesta": "Listo, anotado.",
        "anotar": [
            {"campo": "medicina_prepagada", "valor": 350000, "periodo": "mensual"},
            {"campo": "intereses_vivienda", "valor": 9000000, "periodo": "anual"},
            {"campo": "dependientes", "valor": 2},
            {"campo": "campo_inventado", "valor": 1},
        ],
    })))
    turno = asistente.TurnoChat(mensaje="pago prepagada de 350 mil al mes y tengo dos hijos")
    r = asyncio.run(asistente.responder(turno))
    assert r.respuestas.medicina_prepagada == 4_200_000  # 350.000 × 12, multiplicado por el código
    assert r.respuestas.intereses_vivienda == 0  # la IA lo inventó: rechazado
    assert "Intereses de crédito de vivienda" in r.rechazadas
    assert r.respuestas.dependientes == 2


def test_extraer_json_tolera_texto_extra():
    assert cliente.extraer_json('Claro:\n```json\n{"a": {"b": 1}}\n```') == {"a": {"b": 1}}
