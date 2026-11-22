# Prueba de carga y costo del pico de temporada (HU-40)

Fecha: 22 de noviembre de 2026. Script: `backend/scripts/carga.py`. Perfil de modelos de pago (Claude Haiku 4.5 con
Sonnet de respaldo), proveedores sin retención de datos, sin caché de IA.

Cada declaración simulada recorre el flujo completo contra la app real: sube la exógena y dos certificados, liquida,
conversa 12 turnos (incluye responder lo que el agente pregunta antes de calcular), vuelve a liquidar y pregunta por el
saldo. Solo OpenRouter es un doble: responde con la latencia típica de Haiku 4.5 (0,6 s al primer token + 110 tokens/s)
y cuenta los tokens de entrada reales de cada llamada.

| Escenario | Declaraciones | Rechazos por cupo | Errores 5xx | Llamadas IA / declaración | Costo / declaración | Chat p95 | Documentos p95 |
|---|---|---|---|---|---|---|---|
| Pico realista: 10 a la vez, salidas típicas | 30/30 | 0 | 0 | 15 | USD 0,073 | 2,8 s | 5,6 s |
| Las 95 del día a la vez, salidas típicas | 95/95 | 0 | 0 | 15 | USD 0,073 | 2,9 s | 13,9 s |
| Las 95 a la vez, salidas casi al máximo | 95/95 | 0 | 0 | 15 | USD 0,086 | 4,6 s | 16,5 s |

Resultado frente a la historia:

- **CA1 cumple:** ninguna solicitud se rechaza por cupo. Con el perfil de pago el cupo sube solo a 40 llamadas por hora
  por persona y 3.000 al día (una declaración usa 15).
- **CA2 cumple:** USD 0,073 por declaración (0,086 en el caso conservador), frente a la meta de 0,30. Las 95
  declaraciones de un día cuestan entre USD 7 y 8.
- Tokens de entrada por turno de chat: mediana 4.842 (meta KPI-12: 5.000). Para llegar ahí, el prompt del chat ya no
  manda los ~60 títulos de la base de conocimiento ni los campos de exterior, pérdidas y comparación patrimonial cuando
  la conversación no los toca, y los ejemplos omiten las claves vacías (antes: 5.957).
- Si las 95 llegan en el mismo instante, el análisis de documentos se demora hasta 14 s porque la lectura de PDF y Excel
  hace fila en el mismo proceso (sin IA, una declaración completa usa ~0,3 s de CPU). Con 10 a la vez, que ya es más
  que el pico esperado, cumple los 10 s del KPI-05.

Limitaciones: la latencia y los tokens de salida del modelo son supuestos (los de entrada sí son medidos). En
producción los KPI-03, 05, 08, 09 y 12 se miden con tráfico real en Configuración → Métricas y KPI.

Los JSON de esta carpeta son la salida completa de cada corrida.
