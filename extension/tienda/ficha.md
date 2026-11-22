# Ficha para Chrome Web Store (HU-42)

Todo lo que pide el panel de desarrollador de Chrome Web Store, listo para copiar. El paquete se arma con:

```
python extension/tienda/empaquetar.py --tienda
```

Sale `extension/dist/declarafacil-extension-<versión>-tienda.zip`, sin pruebas ni direcciones de desarrollo (localhost).
Las imágenes están en `capturas/` y se regeneran con
`CAPTURAS=extension/tienda/capturas node extension/pruebas/probar.mjs`.

Lo único que falta es humano: abrir una cuenta de desarrollador de Chrome Web Store (pago único de USD 5, con
verificación de identidad), subir el .zip, pegar estos textos y enviar a revisión (suele tardar de 1 a 3 días hábiles).

## Ficha de la tienda

- **Nombre:** DeclaraFácil: puente con la DIAN
- **Resumen (máx. 132 caracteres):** Llena en MUISCA las casillas de tu borrador del formulario 210 y trae tu exógena con tu sesión abierta. Nunca firma ni presenta.
- **Categoría:** Productividad (Herramientas)
- **Idioma:** Español (Latinoamérica)
- **Descripción:**

> DeclaraFácil te ayuda a armar el borrador de tu declaración de renta de persona natural en Colombia
> (formulario 210). Esta extensión es el puente entre DeclaraFácil y MUISCA, el portal de la DIAN:
>
> • Llena el formulario 210: en «Diligenciar y presentar formulario 210» escribe cada valor de tu borrador en su
>   casilla, como si lo tecleara una persona, y te avisa si los totales que calcula MUISCA no cuadran con tu borrador.
> • Trae tu exógena: con tu sesión de MUISCA abierta, consulta la información exógena del año que elijas y se la
>   pasa a DeclaraFácil para que la lea.
> • Aprende: si no encuentra una casilla, le muestras dónde está y la recuerda (solo la ubicación, nunca el valor).
>
> Lo que nunca hace: iniciar sesión por ti, leer o guardar tu contraseña, firmar, presentar ni pagar. Esos pasos
> siempre son tuyos.
>
> Proyecto educativo de la Universidad Católica de Colombia. No reemplaza la asesoría de un contador.

- **Imágenes:** ícono `../iconos/icono-128.png`; captura `capturas/ventanita.png` (1280×800); imagen promocional
  pequeña `capturas/promo-440x280.png`. Recomendado: una segunda captura del formulario 210 real con las casillas en
  verde, tomada con una cuenta del equipo y con cédula y nombre tapados.
- **Sitio web:** https://declarafacil.onrender.com
- **Asistencia:** https://github.com/suntzz/declarafacil-ai/issues

## Prácticas de privacidad

**Propósito único:** llevar el borrador del formulario 210 que arma DeclaraFácil a las casillas de MUISCA y traer la
información exógena de la persona desde MUISCA hacia DeclaraFácil, usando la sesión que la persona abrió.

**Justificación de permisos**

| Permiso | Para qué |
|---|---|
| `storage` | Guardar el borrador en `chrome.storage.session` (solo memoria, vence a las 3 horas) y, en `chrome.storage.local`, la ubicación de las casillas que la persona le enseña (sin valores) y la preferencia de guardar copia en Descargas. |
| `scripting` | Escribir los valores en los campos del formulario 210 de MUISCA, que está repartido en varios marcos (frames), y leer los totales que MUISCA recalcula para compararlos. |
| `downloads` | Último recurso para atrapar el archivo de la exógena cuando MUISCA lo descarga con un enlace, y guardar una copia en Descargas solo si la persona lo pide. |
| Host `https://*.dian.gov.co/*` | Es donde están el formulario 210 y la consulta de la exógena. No pide acceso a ningún otro sitio. |
| Content script en las direcciones de DeclaraFácil | Recibir el borrador desde la app y entregarle la exógena (mensajes con verificación de origen). |

**Código remoto:** No. Todo el código va dentro del paquete; no se carga JavaScript de afuera ni se usa `eval`.

**Uso de datos (casillas a marcar en el panel):**

- Recopila: *Información financiera y de pagos* (valores del borrador y archivo de la exógena) y *Contenido del sitio
  web* (estructura de la página de MUISCA para encontrar las casillas).
- No recopila: información de identificación personal, de salud, de autenticación (contraseñas), comunicaciones
  personales, ubicación, historial web ni actividad del usuario.

**Certificaciones (las tres se cumplen):**

- No vendo ni transfiero datos de usuarios a terceros, fuera de los casos de uso aprobados.
- No uso ni transfiero datos de usuarios para fines no relacionados con el propósito único del elemento.
- No uso ni transfiero datos de usuarios para determinar la solvencia crediticia ni para préstamos.

**Política de privacidad:** https://declarafacil.onrender.com/privacidad.html#extension

## Antes de enviar a revisión

1. Subir la versión en `manifest.json` si cambió el código (la tienda no acepta repetir versión).
2. `node extension/pruebas/probar.mjs` en verde.
3. `python extension/tienda/empaquetar.py --tienda` y subir ese .zip.
4. Si la app cambia de dominio, actualizar `content_scripts[2].matches` y `ORIGENES_APP` en `fondo.js`.
