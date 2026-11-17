# Extensión de DeclaraFácil para Chrome

Une DeclaraFácil con MUISCA usando la sesión que la persona ya abrió en su navegador:

- **Llena el formulario 210.** DeclaraFácil le pasa el borrador casilla por casilla; en «Diligenciar y presentar formulario 210» (versión para expertos) la extensión escribe cada valor en su casilla, como si lo tecleara la persona, para que MUISCA recalcule sus totales. Después compara esos totales con el borrador y avisa si alguno no cuadra.
- **Trae la exógena.** Con un clic recorre «Consultar información exógena» (acepta las condiciones del servicio, elige el año y toca «Consultar»), atrapa el archivo y se lo pasa a DeclaraFácil, que lo lee como si se hubiera subido a mano.

**Nunca** inicia sesión por la persona, ni lee o guarda su contraseña, ni hace clic en firmar, presentar o pagar. Esos pasos siguen siendo de la persona, como pide la evaluación ética del proyecto.

## Instalarla (modo desarrollador)

1. Descarga la carpeta `extension/` (o el `declarafacil-extension.zip` que publica la app y descomprímelo).
2. En Chrome o Edge abre `chrome://extensions`, activa **Modo de desarrollador** y toca **Cargar descomprimida**.
3. Elige la carpeta `extension`. Fija el ícono de DeclaraFácil en la barra.

## Cómo se usa

**Llenar el 210**

1. En DeclaraFácil arma tu borrador y entra a **Presentar en la DIAN** → «Llenar con la extensión».
2. En MUISCA abre *Diligenciar y presentar formulario 210* del mismo año. Aparece el recuadro de DeclaraFácil: toca **Llenar casillas** (o usa el botón de la ventanita de la extensión).
3. Las casillas que escribió quedan en verde. Si alguna no la encontró, toca **Mostrarme dónde están**, elige la casilla y haz clic en su campo: la recuerda para la próxima vez.
4. Revisa todo, firma y presenta tú.

**Traer la exógena**

1. En DeclaraFácil, en la carga de documentos, toca **Traer mi exógena de la DIAN** (o en la ventanita de la extensión elige el año y toca **Traer mi exógena**).
2. Si MUISCA pide iniciar sesión, entra tú. La extensión sigue sola y te devuelve a DeclaraFácil con el archivo ya leído.
3. Si en algún paso no encuentra el botón, te dice qué tocar; cuando descargues el archivo, igual lo atrapa.

## Privacidad

- Permisos: solo los sitios de la DIAN (`*.dian.gov.co`) y las direcciones de DeclaraFácil. `storage` guarda el borrador en memoria (`chrome.storage.session`, se borra al cerrar el navegador y vence a las 3 horas); `scripting` llena los campos en todos los marcos de MUISCA; `downloads` es el último recurso para atrapar la exógena si MUISCA la descarga con un enlace.
- En el disco solo queda **dónde** va cada casilla que la persona le enseñó (el id o la ruta del campo), nunca un valor.
- La exógena no se guarda: pasa directo a la pestaña de DeclaraFácil. Si DeclaraFácil estaba cerrado, se guarda en memoria 10 minutos y se entrega al abrirlo. Opcionalmente puede dejar una copia en Descargas.
- La captura del archivo solo se activa cuando la persona pide «Traer mi exógena» y se apaga al recibirlo.

## Cómo encuentra cada casilla

En este orden: lo que la persona le enseñó → el número en el `id`, `name` o título del campo (`cas32`, `casilla_32`) → la cajita con el número de la casilla en la misma fila. Como no tenemos acceso a una cuenta de MUISCA para probar, la primera vez puede que no encuentre todas: para eso están «Mostrarme dónde están» y el **diagnóstico**.

**Diagnóstico** (ventanita → Herramientas → Copiar diagnóstico): copia cómo está armada la página abierta de MUISCA (ids y nombres de los campos, textos de botones y enlaces, números de casilla en pantalla), **sin valores** y con los números largos tapados. Si alguien del equipo lo corre una vez en el formulario 210 y en la consulta de la exógena, con eso se ajustan los selectores para todos. «Copiar casillas aprendidas» exporta lo que la persona le enseñó, para incluirlo como mapa por defecto.

## Pruebas

`node extension/pruebas/probar.mjs` abre un Chrome con la extensión contra páginas que imitan a MUISCA y a DeclaraFácil (no toca la DIAN): llenado por atributo, por etiqueta y aprendido; comparación con el total que calcula MUISCA; enseñar una casilla; el recorrido completo de la exógena (inicio de sesión hecho por la persona, menú de JSF, condiciones, año, «Consultar») y el caso en que el Excel sale de un enlace de JSF; la entrega cuando DeclaraFácil estaba cerrado; y que no queden valores, claves ni archivos guardados. Usa el Chromium de Playwright del front (`cd frontend && npx playwright install chromium`) o el que indique `CHROME`.

## Límites

- Hecha y probada contra páginas simuladas: los nombres reales de los botones y campos de MUISCA hay que confirmarlos con el diagnóstico.
- Si MUISCA abre la exógena en una ventana emergente o la manda al correo, hay que descargarla y subirla a mano.
- Las casillas que abren un anexo en MUISCA (por ejemplo, la 299 de compras con factura electrónica) se llenan a mano.
- Las casillas en 0 no se tocan: si MUISCA trae un valor sugerido ahí, revísalo.
