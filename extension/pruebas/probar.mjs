// Prueba de la extensión en un Chrome de verdad, contra páginas que imitan a MUISCA y a DeclaraFácil.
// No toca la DIAN: todas las direcciones se responden aquí mismo (context.route).
//
//   node extension/pruebas/probar.mjs            (usa el Chromium de Playwright)
//   CHROME=/ruta/a/chrome node extension/pruebas/probar.mjs
//
// Cubre: el puente con la app, el llenado del 210 (por atributo, por etiqueta y lo aprendido), la
// comparación con los totales que calcula MUISCA, enseñar una casilla, y el recorrido completo de la
// exógena (inicio de sesión hecho por la persona → menú → condiciones → año → Consultar → archivo).
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const aqui = fileURLToPath(new URL(".", import.meta.url));
const require = createRequire(new URL("../../frontend/package.json", import.meta.url));
const { chromium } = require("@playwright/test");

const EXTENSION = join(aqui, "..");
const EXOGENA = readFileSync(join(aqui, "../../backend/data/demo/exogena_demo_2025.xlsx"));
const APP = "http://localhost:5199/";
const MUISCA = "https://muisca.dian.gov.co";

const pagina = (titulo, cuerpo) => `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>${titulo}</title></head><body>${cuerpo}</body></html>`;

const relleno = Array.from({ length: 16 }, (_, i) => `<tr><td>${200 + i}</td><td>Casilla de relleno</td><td><input id="frm:j_idt${100 + i}"></td></tr>`).join("");

const FORMULARIO_210 = pagina(
  "Diligenciar formulario 210",
  `<h1>Formulario 210 Declaración de renta y complementario de personas naturales</h1>
   <p>Año gravable 2025</p>
   <form id="frm" method="post" action="/WebFormulario/guardar"><table>
     <tr><td>29</td><td>Total patrimonio bruto</td><td><input id="frm:j_idt10" class="mascara"></td></tr>
     <tr><td>30</td><td>Deudas</td><td><input id="frm:j_idt11" class="mascara"></td></tr>
     <tr><td>31</td><td>Total patrimonio líquido</td><td><input id="frm:j_idt12" readonly></td></tr>
     <tr><td>32</td><td>Ingresos brutos rentas de trabajo</td><td><input id="frm:cas32"></td>
         <td>33</td><td>Ingresos no constitutivos</td><td><input id="frm:cas33"></td></tr>
     <tr><td>Rentas exentas AFC (36)</td><td><input name="valorDeLaCasillaTreintaYSeis"></td></tr>
     ${relleno}
   </table>
   <button type="button" id="firmar" onclick="window.firmado = true">Firmar</button>
   </form>
   <script>
     const n = (id) => Number(document.getElementById(id).value.replace(/\\D/g, "") || 0);
     document.querySelectorAll(".mascara").forEach((i) => i.addEventListener("blur", () => {
       const d = i.value.replace(/\\D/g, ""); i.value = d ? Number(d).toLocaleString("es-CO") : "";
     }));
     const calc = () => { document.getElementById("frm:j_idt12").value = (n("frm:j_idt10") - n("frm:j_idt11")).toLocaleString("es-CO"); };
     ["frm:j_idt10", "frm:j_idt11"].forEach((id) => document.getElementById(id).addEventListener("change", calc));
   </script>`,
);

const LOGIN = pagina(
  "Ingreso MUISCA",
  `<form method="post" action="/WebIdentidadLogin/entrar"><label>Usuario <input name="usuario"></label>
   <label>Contraseña <input type="password" name="clave"></label><button id="ingresar">Ingresar</button></form>`,
);
const MENU = pagina(
  "Usuario registrado",
  `<form id="menu" method="post" action="/WebArquitectura/menu.faces"><input type="hidden" name="javax.faces.ViewState" value="vista-1">
   <ul><li><a href="#" id="firmaMenu" onclick="window.firmado = true; return false;">Firmar declaración</a></li>
   <li><a href="#" id="menu:j_idt5" onclick="var f=document.getElementById('menu');var i=document.createElement('input');i.type='hidden';i.name='menu:j_idt5';i.value='menu:j_idt5';f.appendChild(i);f.submit();f.removeChild(i);return false;">Consultar información exógena</a></li></ul></form>`,
);
const CONDICIONES = pagina(
  "Información exógena",
  `<form method="post" action="/WebInformacionExogena/condiciones"><p>Condiciones del servicio de consulta.</p>
   <label><input type="checkbox" name="acepto"> Acepto los términos y condiciones</label>
   <button type="submit">Aceptar</button></form>`,
);
const CONSULTA = pagina(
  "Consultar información exógena",
  `<form method="post" action="/WebInformacionExogena/consultar"><label>Año gravable <select name="anio">
   <option value="2023">2023</option><option value="2024">2024</option><option value="2025">2025</option></select></label>
   <input type="submit" name="consultar" value="Consultar"></form>`,
);
// Otra forma de MUISCA: «Consultar» muestra una página y el Excel sale de un enlace de JSF (form.submit con campos ocultos)
const RESULTADOS = pagina(
  "Resultado de la consulta",
  `<form id="res" method="post" action="/WebInformacionExogena/descargar"><input type="hidden" name="javax.faces.ViewState" value="vista-9">
   <p>Se encontraron 12 registros.</p>
   <a href="#" id="res:descargar" onclick="var f=document.getElementById('res');var i=document.createElement('input');i.type='hidden';i.name='res:descargar';i.value='res:descargar';f.appendChild(i);f.submit();f.removeChild(i);return false;">Descargar Excel</a></form>`,
);
// Como se ve la MUISCA real (17-nov-2026): en el tablero, un diálogo «Consulta Exógena» con las condiciones,
// un botón con ícono «Aceptar» (sin casilla), el año y otro botón con ícono «Consultar»
const TABLERO = pagina(
  "Inicio",
  `<div id="encabezado">A Nombre Propio · PERSONA DE PRUEBA</div><h1>Mis actividades</h1>
   <a href="#" id="abrirExo" onclick="document.getElementById('dlg').style.display='block'; return false;">Consulta de información exógena</a>
   <div id="dlg" style="display:none"><div>Consulta Exógena:</div>
     <form id="frmExo" method="post" action="/WebDashboard/DefDashboard.faces"><input type="hidden" name="javax.faces.ViewState" value="t-1">
       <input type="hidden" name="frmExo:aceptado" id="aceptado" value="no">
       <p>CONDICIONES ACEPTACION INFORMACION REPORTADA POR TERCEROS</p><p>4. Usted deberá aceptar las condiciones aquí mencionadas.</p>
       <input type="image" alt="Aceptar" style="width:80px;height:22px" onclick="document.getElementById('aceptado').value='si'; document.getElementById('filaAnio').style.display='block'; return false;">
       <div id="filaAnio" style="display:none">Año : <select name="frmExo:anio"><option>2023</option><option>2024</option><option selected>2025</option></select>
         <input type="image" name="frmExo:consultar" alt="Consultar" style="width:80px;height:22px"></div>
     </form></div>`,
);
const APP_HTML = pagina(
  "DeclaraFácil (simulada)",
  `<script>
     window.mensajes = []; window.recibido = null;
     window.addEventListener("message", (e) => {
       const m = e.data; if (!m || m.origen !== "declarafacil-extension") return;
       window.mensajes.push(m);
       if (m.tipo === "exogena") { window.recibido = m; window.postMessage({ origen: "declarafacil-app", tipo: "exogena-recibida" }, location.origin); }
     });
     window.mandar = (m) => window.postMessage({ origen: "declarafacil-app", ...m }, location.origin);
   </script>`,
);

const BORRADOR = {
  anio_gravable: 2025,
  casillas: [
    { numero: 29, nombre: "Total patrimonio bruto", valor: 250_000_000, tipo: "dato", texto: null },
    { numero: 30, nombre: "Deudas", valor: 50_000_000, tipo: "dato", texto: null },
    { numero: 31, nombre: "Total patrimonio líquido", valor: 200_000_000, tipo: "calculada", texto: null },
    { numero: 32, nombre: "Ingresos brutos de las rentas de trabajo", valor: 120_000_000, tipo: "dato", texto: null },
    { numero: 33, nombre: "Ingresos no constitutivos", valor: 6_000_000, tipo: "dato", texto: null },
    { numero: 36, nombre: "Rentas exentas AFC", valor: 3_000_000, tipo: "dato", texto: null },
    { numero: 58, nombre: "Ingresos brutos de las rentas de capital", valor: 1_000_000, tipo: "dato", texto: null },
    { numero: 91, nombre: "Renta líquida cédula general", valor: 0, tipo: "calculada", texto: null },
  ],
};

const esperarHasta = async (fn, ms = 15000, que = "la condición") => {
  const fin = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > fin) throw new Error(`Se acabó el tiempo esperando ${que}`);
    await new Promise((r) => setTimeout(r, 200));
  }
};

const contexto = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), "df-ext-")), {
  // El Chromium de Playwright necesita el canal "chromium" (headless nuevo) para cargar extensiones
  ...(process.env.CHROME ? { executablePath: process.env.CHROME } : { channel: "chromium" }),
  headless: true,
  args: [`--disable-extensions-except=${EXTENSION}`, `--load-extension=${EXTENSION}`, "--no-proxy-server"],
});

const peticiones = [];
await contexto.route(`${MUISCA}/**`, async (route) => {
  const r = route.request();
  const url = new URL(r.url());
  const cuerpo = r.postData() || "";
  peticiones.push(`${r.method()} ${url.pathname}`);
  const html = (h) => route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: h });
  if (url.pathname.startsWith("/WebFormulario")) return html(FORMULARIO_210);
  if (url.pathname === "/WebDashboard/DefDashboard.faces") {
    if (r.method() === "GET") return html(TABLERO);
    if (cuerpo.includes("frmExo%3Aaceptado=si") && cuerpo.includes("frmExo%3Aanio=2025") && cuerpo.includes("frmExo%3Aconsultar"))
      return route.fulfill({ status: 200, headers: { "content-type": "application/vnd.ms-excel", "content-disposition": 'attachment; filename="InformacionExogena2025.xlsx"' }, body: EXOGENA });
    return html(TABLERO);
  }
  if (url.pathname === "/WebIdentidadLogin/" && r.method() === "GET") return html(LOGIN);
  if (url.pathname === "/WebIdentidadLogin/entrar") return html(MENU);
  if (url.pathname === "/WebArquitectura/menu.faces") return html(cuerpo.includes("menu%3Aj_idt5") ? CONDICIONES : MENU);
  if (url.pathname === "/WebInformacionExogena/condiciones") return html(/acepto=on/.test(cuerpo) ? CONSULTA : CONDICIONES);
  if (url.pathname === "/WebInformacionExogena/consultar") {
    if (/anio=2024/.test(cuerpo)) return html(RESULTADOS);
    if (!/anio=2025/.test(cuerpo)) return route.fulfill({ status: 400, contentType: "text/html", body: "año equivocado" });
    return route.fulfill({
      status: 200,
      headers: { "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "content-disposition": 'attachment; filename="Reporte_Exogena_2025.xlsx"' },
      body: EXOGENA,
    });
  }
  if (url.pathname === "/WebInformacionExogena/descargar") {
    if (!cuerpo.includes("res%3Adescargar")) return html(RESULTADOS); // sin el campo oculto de JSF no hay descarga
    return route.fulfill({
      status: 200,
      headers: { "content-type": "application/octet-stream", "content-disposition": "attachment; filename*=UTF-8''Ex%C3%B3gena_2024.xlsx" },
      body: EXOGENA,
    });
  }
  return html(pagina("MUISCA", "<p>Página</p>"));
});
await contexto.route(`${APP}**`, (route) => route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: APP_HTML }));

let [sw] = contexto.serviceWorkers();
if (!sw) sw = await contexto.waitForEvent("serviceworker");

let ok = 0;
const paso = (t) => console.log(`✓ ${t}`) || ok++;

// 1) La app ve la extensión y le manda el borrador
const app = await contexto.newPage();
await app.goto(APP);
await app.evaluate(() => window.mandar({ tipo: "hola", id: 1 }));
await esperarHasta(() => app.evaluate(() => window.mensajes.some((m) => m.tipo === "lista")), 5000, "el aviso de la extensión");
assert.equal(await app.evaluate(() => document.documentElement.dataset.declarafacilExtension), JSON.parse(readFileSync(join(EXTENSION, "manifest.json"))).version);
await app.evaluate((b) => window.mandar({ tipo: "formulario", id: 2, datos: b }), BORRADOR);
const resp = await esperarHasta(() => app.evaluate(() => window.mensajes.find((m) => m.tipo === "respuesta" && m.id === 2)), 5000, "la respuesta al borrador");
assert.equal(resp.ok, true);
assert.equal(resp.escribir, 6); // 29, 30, 32, 33, 36, 58 (las calculadas no se escriben)
paso("la app detecta la extensión y le pasa el borrador del 210");

// Un mensaje de otro origen no entra
const malo = await sw.evaluate(async () => manejar({ tipo: "df:formulario", datos: {} }, { tab: { id: 1 }, url: "https://otra.com/" }).catch((e) => e.message));
assert.equal(malo, "Origen no permitido");
paso("el service worker rechaza mensajes de otros sitios");

// 2) Llenar el formulario en MUISCA
const f210 = await contexto.newPage();
await f210.goto(`${MUISCA}/WebFormulario210/diligenciar.faces`);
await f210.waitForSelector("#declarafacil-panel", { timeout: 10000 });
const tabId = await sw.evaluate(async () => (await chrome.tabs.query({ url: "https://muisca.dian.gov.co/WebFormulario210/*" }))[0].id);
const r1 = await sw.evaluate((id) => llenarEn(id), tabId);
assert.equal(r1.ok, true, r1.error);
assert.deepEqual(r1.resumen.llenadas.map((x) => x.n).sort((a, b) => a - b), [29, 30, 32, 33]);
assert.deepEqual(r1.resumen.noEncontradas.sort((a, b) => a - b), [36, 58]);
assert.equal(await f210.inputValue("#frm\\:j_idt10"), "250.000.000"); // la máscara de la página formateó lo escrito
assert.equal(await f210.inputValue("#frm\\:cas32"), "120000000");
assert.equal(await f210.inputValue("#frm\\:cas33"), "6000000");
const c31 = r1.resumen.calculadas.find((c) => c.n === 31);
assert.ok(c31 && c31.muisca === 200_000_000 && c31.borrador === 200_000_000, JSON.stringify(r1.resumen.calculadas));
assert.equal(r1.resumen.avisoAnio, null);
assert.equal(await f210.evaluate(() => window.firmado ?? false), false);
paso("llena por atributo y por etiqueta, respeta la máscara y compara el total que calcula MUISCA");

// 3) Enseñar la casilla 36 y volver a llenar
await sw.evaluate((id) => ensenar(id, 36), tabId);
await f210.click('input[name="valorDeLaCasillaTreintaYSeis"]');
await esperarHasta(() => sw.evaluate(async () => !!(await chrome.storage.local.get("mapas")).mapas?.["210"]?.[36]), 5000, "que aprenda la casilla 36");
assert.equal(await f210.inputValue('input[name="valorDeLaCasillaTreintaYSeis"]'), "3000000");
await f210.fill('input[name="valorDeLaCasillaTreintaYSeis"]', "");
const r2 = await sw.evaluate((id) => llenarEn(id), tabId);
assert.ok(r2.resumen.llenadas.some((x) => x.n === 36 && x.como === "aprendido"), JSON.stringify(r2.resumen.llenadas));
assert.deepEqual(r2.resumen.noEncontradas, [58]);
const guardado = await sw.evaluate(async () => JSON.stringify(await chrome.storage.local.get(null)));
assert.ok(!guardado.includes("3000000") && !guardado.includes("250000000"), "en el disco no quedan valores");
paso("aprende dónde va una casilla y la usa la vez siguiente (sin guardar valores en el disco)");

// Capturas para la ficha de Chrome Web Store (1280×800): CAPTURAS=extension/tienda/capturas
if (process.env.CAPTURAS) {
  const { mkdirSync } = await import("node:fs");
  mkdirSync(process.env.CAPTURAS, { recursive: true });
  const idExt = new URL(sw.url()).host;
  const popup = await contexto.newPage();
  await popup.setViewportSize({ width: 1280, height: 800 });
  await popup.goto(`chrome-extension://${idExt}/popup.html`);
  await popup.waitForTimeout(600);
  await popup.addStyleTag({ content: `html{background:#eef1ee;min-height:100%;display:grid;place-items:center}body{box-shadow:0 18px 50px #0003;border-radius:12px;zoom:1.3}` });
  await popup.screenshot({ path: join(process.env.CAPTURAS, "ventanita.png") });
  await popup.close();
  const promo = await contexto.newPage();
  await promo.setViewportSize({ width: 440, height: 280 });
  await promo.goto(`chrome-extension://${idExt}/tienda/promo.html`).catch(() => {});
  if (!(await promo.title()).includes("DeclaraFácil")) await promo.goto("file://" + join(EXTENSION, "tienda", "promo.html"));
  await promo.screenshot({ path: join(process.env.CAPTURAS, "promo-440x280.png") });
  await promo.close();
  console.log(`· capturas en ${process.env.CAPTURAS}`);
}

// 4) Traer la exógena: la persona inicia sesión; la extensión hace el resto.
// (MUISCA ya está abierto en una pestaña: las pestañas que abre la extensión no pasan por context.route)
await f210.close();
const dian = await contexto.newPage();
await dian.goto(`${MUISCA}/WebIdentidadLogin/`);
await app.bringToFront();
await app.evaluate(() => window.mandar({ tipo: "pedir-exogena", id: 3, anio: 2025 }));
const r3 = await esperarHasta(() => app.evaluate(() => window.mensajes.find((m) => m.tipo === "respuesta" && m.id === 3)), 5000, "la respuesta al pedido");
assert.equal(r3.ok, true, r3.error);
assert.equal(r3.nueva, false);
await dian.waitForSelector('input[type="password"]');
await dian.waitForSelector("#declarafacil-panel", { timeout: 10000 });
await dian.fill('input[name="usuario"]', "persona");
await dian.fill('input[type="password"]', "clave-de-prueba");
await dian.click("#ingresar"); // esto lo hace la persona, nunca la extensión
const recibido = await esperarHasta(() => app.evaluate(() => window.recibido), 30000, "la exógena en la app");
assert.equal(recibido.nombre, "Reporte_Exogena_2025.xlsx");
assert.ok(Buffer.from(recibido.base64, "base64").equals(EXOGENA), "el archivo llegó completo");
assert.ok(peticiones.includes("POST /WebArquitectura/menu.faces") && peticiones.includes("POST /WebInformacionExogena/condiciones"));
assert.equal(peticiones.filter((p) => p === "POST /WebInformacionExogena/consultar").length, 1, "la consulta se hizo una sola vez");
assert.equal(await dian.evaluate(() => window.firmado ?? false), false);
const guardado2 = await sw.evaluate(async () => JSON.stringify(await chrome.storage.local.get(null)));
assert.ok(!guardado2.includes("clave-de-prueba") && !guardado2.includes(recibido.base64.slice(0, 40)), "no guarda la clave ni el archivo");
paso("trae la exógena: menú → condiciones → año → Consultar, y el archivo llega a DeclaraFácil");

// 4b) Con la sesión ya abierta y el Excel detrás de un enlace de JSF
await app.evaluate(() => {
  window.recibido = null;
});
await dian.goto(`${MUISCA}/WebIdentidadLogin/entrar`); // ya entró: está en el menú
await app.evaluate(() => window.mandar({ tipo: "pedir-exogena", id: 4, anio: 2024 }));
const recibido2 = await esperarHasta(() => app.evaluate(() => window.recibido), 30000, "la exógena de 2024");
assert.equal(recibido2.nombre, "Exógena_2024.xlsx");
assert.ok(Buffer.from(recibido2.base64, "base64").equals(EXOGENA));
assert.ok(peticiones.includes("POST /WebInformacionExogena/descargar"));
paso("también la atrapa cuando sale de un enlace de JSF después de consultar, con la sesión ya abierta");

// 4c) Como en la MUISCA real: diálogo en el tablero, condiciones con botón «Aceptar» y botones con ícono
await app.evaluate(() => {
  window.recibido = null;
});
await dian.goto(`${MUISCA}/WebDashboard/DefDashboard.faces`);
await app.evaluate(() => window.mandar({ tipo: "pedir-exogena", id: 5, anio: 2025 }));
const recibido3 = await esperarHasta(() => app.evaluate(() => window.recibido), 30000, "la exógena desde el diálogo del tablero");
assert.equal(recibido3.nombre, "InformacionExogena2025.xlsx");
assert.ok(Buffer.from(recibido3.base64, "base64").equals(EXOGENA));
paso("en el tablero real: abre «Consulta de información exógena», acepta con el botón, consulta y trae el archivo");

// 5) Si DeclaraFácil estaba cerrado, la exógena queda en memoria y se entrega al abrirlo
await sw.evaluate(async () => {
  await chrome.storage.session.set({ pendiente: { nombre: "x.xlsx", mime: "", base64: "QUJD", cuando: Date.now() } });
});
const app2 = await contexto.newPage();
await app2.goto(APP);
await app2.evaluate(() => window.mandar({ tipo: "hola", id: 9 }));
const tarde = await esperarHasta(() => app2.evaluate(() => window.recibido), 5000, "la exógena pendiente");
assert.equal(tarde.base64, "QUJD");
assert.equal(await sw.evaluate(async () => (await chrome.storage.session.get("pendiente")).pendiente ?? null), null);
paso("entrega la exógena pendiente cuando se abre DeclaraFácil");

await contexto.close();
console.log(`\n${ok} pruebas de la extensión pasaron.`);
