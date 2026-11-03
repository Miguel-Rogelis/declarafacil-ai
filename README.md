# DeclaraFácil AI

Asistente agéntico que convierte el reporte de **información exógena** de la DIAN en un **borrador de la declaración de renta** de personas naturales en Colombia (años gravables 2021 a 2025), explicado en lenguaje simple y con cada cifra trazable hasta su origen.

Proyecto del curso *Problem Discovery & Solution Design with AI*, Ingeniería de Sistemas, Universidad Católica de Colombia.

> Es un prototipo con fines educativos. No presenta la declaración ni reemplaza a un contador: la revisión y la firma en MUISCA siempre son del contribuyente.

## Qué hace

Todo pasa en un **chat a pantalla completa** con un agente. El usuario lleva la conversación de inicio a fin: el agente no sugiere preguntas ni guía con un cuestionario, responde lo que se le pregunta y hace lo que se le pide.

- Responde directo, incluso lo más básico ("¿qué es la DIAN?", "¿cómo sé si tengo que declarar?", "¿me pueden meter a la cárcel?"), sin haber subido nada. Las respuestas usan las cifras del año elegido.
- Si el usuario cuenta sus datos con sus palabras ("gano 4 millones al mes", "tengo 2 hijos", "un carro de 40 millones"), el agente los anota, muestra qué anotó y deja deshacerlo.
- Si pide calcular ("calcula", "¿cuánto me toca pagar?"), calcula ahí mismo. Si después cambia un dato o el año, el agente actualiza el cálculo solo.
- **Deduce de la exógena apenas se sube**: quién le reportó qué (empleador, bancos, créditos, fondo de cesantías, catastro), si está obligado y por qué, y qué beneficios ya vienen incluidos (retenciones, prepagada, intereses de vivienda, 1 % de facturas). Si algo no cuadra (por ejemplo, consignaciones muy por encima de los ingresos), pregunta de dónde salió la diferencia.
- **Pregunta cuando le falta información**, como un contador, solo cuando el dato cambia la respuesta y sin preguntar lo que ya trae la exógena:
  - Lo que la exógena no muestra: personas a cargo, aportes voluntarios, vehículos, ingresos que no pasan por un banco o un empleador, ventas, herencias o premios, sanciones previas, el impuesto del año pasado.
  - Cifras ambiguas: "gano 3 millones y medio" → "¿al mes o en todo el año?"; "tengo un carro" → "¿cuánto pagaste?"; "tengo hijos" → "¿cuántos?"; "vendí el lote en 80 millones" → "¿en cuánto lo habías comprado?" (la ganancia la calcula el código).
  - Antes de calcular hace como máximo dos rondas de preguntas (hasta dos datos cada una). Con "calcula así" calcula con lo que hay; el resultado dice qué supuso.
  - Si pregunta por su caso ("¿tengo que declarar?", "¿cuándo vence?") y falta el dato, lo pide y retoma. Nunca repite una pregunta; entiende respuestas cortas ("2", "al mes", "no", "no sé", "fue un préstamo").
- **Guía para conseguir cada dato**: "¿qué documentos necesito?" da la lista de SU caso con los nombres de sus entidades; "¿qué me falta?" dice lo que falta y empieza a preguntarlo; y explica cómo sacar cada certificado (220, tributario del banco, intereses de vivienda, prepagada, cesantías, pensión, predial, declaración anterior, soportes de dependientes).
- Simula escenarios sin tocar los datos: "¿y si pagara prepagada de 400 mil al mes?" → cuánto cambia el impuesto.
- Corrige: "quita la moto", "me equivoqué, no son 2 hijos" y cada cambio se puede deshacer.
- Si pregunta por su caso ("¿tengo que declarar?", "¿cuándo vence?") y ya hay datos, responde con su caso: la obligación la decide el motor con sus cifras y la fecha sale de su cédula.
- Puede adjuntar la exógena con el clip en cualquier momento. Si es de otro año, el agente cambia a las reglas de ese año.
- Puede cambiar de año gravable (2021 a 2025) desde el selector de arriba o pidiéndolo en el chat.
- "Tus datos" abre un panel con cada cifra y de dónde sale.

Recibe: si está obligado a declarar, el saldo a pagar o a favor, la sanción si va tarde, alertas antes de firmar, el borrador por cédulas y, al tocar cada línea, la norma y las filas de la exógena de donde sale.

Cubre la cédula general (trabajo, honorarios, capital y no laborales), pensiones, dividendos (subcédulas 1 y 2 con el descuento del art. 254-1), ganancias ocasionales, patrimonio, anticipo (art. 807) y sanción por extemporaneidad (arts. 639-641).

## Arquitectura: un agente, una responsabilidad

```mermaid
flowchart LR
    U([Usuario]) -->|exógena .xlsx/.pdf| L
    subgraph F1[Fase 1: documento]
        L[Lector<br/>reglas] --> A[Anonimizador<br/>reglas] --> C[Clasificador<br/>reglas + IA si hay duda] --> I[Intérprete<br/>reglas + IA]
    end
    I -->|filas ubicadas| AS
    AS -->|datos validados| M
    subgraph F2[Fase 2: cálculo]
        M[Motor tributario<br/>reglas por año] --> AU[Auditor<br/>reglas] --> E[Explicador<br/>IA verificada]
    end
    E --> R([Borrador + alertas])
    U <-->|chat libre| AS[Asistente<br/>IA validada + reglas]
    I & C & E & AS -.-> OR[(OpenRouter<br/>modelos gratis con respaldo)]
```

| Agente | Usa IA | Responsabilidad única |
|---|---|---|
| Lector | No | Lee el Excel o PDF y lo convierte en filas (detalle, valor, renglón sugerido). |
| Anonimizador | No | Enmascara cédula, nombres y cuentas antes de que algo salga del servidor. |
| Clasificador | Solo si hay duda | Confirma que el archivo es una exógena y de qué año. |
| Intérprete | Sí, acotada | Ubica cada concepto en la declaración y lo explica. **Nunca recibe montos**: elige una casilla de una lista cerrada y el código copia la cifra de la fila original. |
| Motor tributario | No | Liquida la declaración con las reglas del año (UVT, topes, art. 241, límite del 40 % / 1.340 UVT, etc.). |
| Auditor | No | Detecta datos por confirmar, ingresos menores a los reportados, patrimonio, vencimientos y beneficios no usados. |
| Explicador | Sí | Redacta el resumen. Cada cifra que escribe se compara contra el cálculo; si inventa una, se descarta y se usa la plantilla. |
| Asistente | Sí | El agente del chat: responde con la base de conocimiento completa (`backend/data/conocimiento`, con las cifras del año elegido) y decide la acción que pide el usuario (anotar, calcular, cambiar de año, abrir la carga de la exógena). La IA solo propone; el código valida cada dato (lista cerrada de campos y rangos, **cada monto anotado debe aparecer en el mensaje del usuario** y **cada cifra de la respuesta debe estar en los datos que recibió**; si no, se descarta). Sin IA o sin cupo, sigue funcionando con reglas. |

El **orquestador** (`backend/app/orquestador.py`) es un flujo fijo y trazable: cada agente emite eventos en vivo (Server-Sent Events) que el front muestra como sellos.

### Decisiones de diseño (ética y riesgo)

- **La IA no calcula.** El mayor riesgo identificado en la evaluación ética era que la IA inventara un valor y el usuario lo firmara. Por eso todas las cifras salen de reglas y de las filas originales.
- **Privacidad (Ley 1581).** El archivo se procesa en memoria y no se guarda. A los modelos solo llegan descripciones de conceptos sin montos ni datos personales. Los proveedores gratuitos de OpenRouter pueden entrenar con lo que reciben; por eso el Anonimizador va antes de cualquier llamada.
- **Revisión humana obligatoria.** Lo que las reglas no reconocen o lo que ubica la IA queda marcado para que el usuario lo confirme.
- **Reglas por año, no en el código.** `backend/data/reglas/agAAAA.json` guarda UVT, topes, tablas, límites, tarifas, calendario de vencimientos y sanciones. Para un año nuevo se clona el anterior desde la pantalla *Reglas y agentes*.
- **Modelos intercambiables.** `backend/data/agentes.json` define los modelos de cada agente en orden de preferencia. Si uno falla o llega al límite, pasa al siguiente. Se cambian desde la pantalla sin volver a desplegar.

## Estructura

```
backend/
  app/agents/       un archivo por agente (el Asistente usa conocimiento.py para la base por año y diagnostico.py para deducir y saber qué falta)
  app/tax/          motor tributario y modelos (sin IA)
  app/llm/          cliente de OpenRouter con respaldo entre modelos
  app/orquestador.py
  app/routers/api.py
  data/reglas/      ag2021 a ag2025 (vigentes), ag2026 (borrador)
  data/uvt.json     UVT de cada año (para la sanción según el año en que se presenta)
  data/agentes.json modelos y temperatura por agente
  data/conocimiento base de conocimiento del Asistente
  data/demo/        exógena ficticia para probar
  tests/            93 pruebas (motor por año, agentes, conversaciones del chat, API, ruta con IA simulada)
  scripts/          generadores de la exógena demo y de las reglas 2021-2024
frontend/           React + Vite + TypeScript, animaciones con Motion
Dockerfile          construye el front y lo sirve desde FastAPI
render.yaml         despliegue gratuito en Render
```

## Correr en local

Requisitos: Python 3.12+ y Node 20+.

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export OPENROUTER_API_KEY=sk-or-...                  # opcional; sin llave funciona en modo simulado
uvicorn app.main:app --reload --port 8000

# Front (otra terminal)
cd frontend
npm install
npm run dev        # http://localhost:5173, redirige /api al backend
```

Pruebas: `cd backend && pytest`. Para regenerar la exógena ficticia: `python scripts/generar_exogena_demo.py`.

## Desplegar gratis (Render + OpenRouter)

1. Crea una cuenta en [openrouter.ai](https://openrouter.ai) y genera una API key en *Keys*. No necesitas tarjeta.
2. Entra a [render.com](https://render.com) con tu cuenta de GitHub.
3. *New* → *Blueprint* → elige este repositorio. Render lee `render.yaml`.
4. Cuando lo pida, pega tu llave en `OPENROUTER_API_KEY`. `ADMIN_TOKEN` se genera solo: búscalo en *Environment* del servicio; es la clave para editar reglas y agentes.
5. *Apply*. La primera construcción tarda unos minutos. La app queda en `https://<nombre>.onrender.com`.

Límites a tener en cuenta:

- **Render gratis** apaga el servicio tras 15 minutos sin uso; la primera visita después tarda cerca de un minuto. Ábrelo antes de presentar.
- **OpenRouter gratis** permite 20 solicitudes por minuto y 50 al día sin créditos (1.000 al día si se compran 10 USD una vez). Cada análisis usa de 1 a 3 llamadas y **cada mensaje del chat usa una**. Cuando se acaba el cupo, el chat sigue respondiendo con reglas y la base de conocimiento.
- Modelos por defecto (revisados el 1 de noviembre de 2026): `nvidia/nemotron-3-ultra-550b-a55b:free`, `nvidia/nemotron-3.5-lightning:free` y `nvidia/nemotron-3.5-super-vl:free`, con `openrouter/free` de respaldo. Gemma 4 devolvía 429 de su proveedor, Inkling solo funciona con herramientas de agente y Nemotron 3 Super dejó de ser gratis.
- Casi todos los modelos gratis razonan antes de responder y ese razonamiento gasta tokens. Por eso cada agente pide razonamiento corto y oculto (`"razonamiento": "low"` en `agentes.json`); si un proveedor no acepta el parámetro, se reintenta sin él.
- Los modelos `:free` cambian seguido. En *Reglas y agentes* → *Agentes* → *Consultar OpenRouter* ves los disponibles hoy y los reemplazas. `openrouter/free` funciona como último respaldo.
- Lo que se edite desde la pantalla de configuración dura hasta que el servicio se reinicie. Para dejarlo fijo, descarga el JSON y súbelo al repositorio.

## Alcance y supuestos

- Personas naturales **residentes**, no obligadas a llevar contabilidad.
- No cubre: rentas del exterior, régimen SIMPLE, descuento por donaciones, renta presuntiva (0 % desde 2021) ni el cálculo de renta por comparación patrimonial (el Auditor solo la advierte).
- Años 2021 y 2022 usan las reglas anteriores a la Ley 2277 (límite de 5.040 UVT, renta exenta de 2.880 UVT, dividendos con tabla propia, ganancias ocasionales al 10 %). Los vencimientos de los años 2021 a 2024 se generaron con la regla de cada decreto de calendario (el método reproduce el calendario oficial 2026); conviene revisarlos contra el calendario publicado.
- Deducciones y rentas exentas se agregan para toda la cédula general (no se reparten por subcédula como en el formulario).
- La sanción se estima con la reducción del art. 640 si el usuario indica que no ha sido sancionado en los últimos dos años; no incluye intereses de mora.
- Los renglones R29, R30, R32 y R132 que se mencionan vienen de la columna *Uso declaración sugerida* de la propia exógena.

## Fuentes normativas

Estatuto Tributario (arts. 206, 241, 242, 254-1, 307, 311-1, 314, 317, 331, 336, 387, 639-641, 807); Ley 2277 de 2022; resoluciones DIAN de UVT de cada año (2021: $36.308; 2022: $38.004; 2023: $42.412; 2024: $47.065; 2025: $49.799); Resolución DIAN 000238 de 2025 (UVT 2026: $52.374); Decreto 0898 de 2026 (componente inflacionario AG 2025: 55,43 %); Decreto 2229 de 2023 (calendario tributario); calendario 2026 para personas naturales.
