/* DeclaraFácil — service worker de la extensión.
 *
 * Guarda el borrador del 210 que manda DeclaraFácil (solo en memoria: chrome.storage.session se
 * borra al cerrar el navegador y además vence a las 3 horas), coordina el llenado en todos los
 * marcos de la pestaña de MUISCA y lleva la exógena atrapada de vuelta a la pestaña de DeclaraFácil.
 * Lo único que guarda en el disco es dónde aprendió que va cada casilla (sin valores).
 */

const MUISCA = "https://muisca.dian.gov.co/WebIdentidadLogin/";
const VIDA_BORRADOR = 3 * 60 * 60 * 1000;
const VIDA_PENDIENTE = 10 * 60 * 1000;
const MAX_ARCHIVO = 15 * 1024 * 1024;
const MAX_INTENTOS = 3;

const ORIGENES_APP = [
  /^https:\/\/declarafacil(-[a-z0-9]+)?\.onrender\.com\//,
  /^https:\/\/(suntzz|miguel-rogelis)\.github\.io\/declarafacil-ai\//,
  /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//,
];
const ES_DIAN = /^https:\/\/([a-z0-9-]+\.)*dian\.gov\.co\//;

const sesion = {
  async leer(k) {
    return (await chrome.storage.session.get(k))[k];
  },
  poner: (o) => chrome.storage.session.set(o),
  quitar: (k) => chrome.storage.session.remove(k),
};

async function borrador() {
  const f = await sesion.leer("formulario");
  if (!f) return null;
  if (Date.now() - f.recibido > VIDA_BORRADOR) {
    await sesion.quitar("formulario");
    return null;
  }
  return f;
}

const resumenBorrador = (f) => (f ? { anio: f.anio, escribir: f.casillas.filter((c) => c.escribir).length, recibido: f.recibido } : null);

async function mapas() {
  return (await chrome.storage.local.get("mapas")).mapas || {};
}

// ---------- Validación de lo que llega de la página ----------

function validarFormulario(datos) {
  if (!datos || typeof datos !== "object") throw new Error("No llegó el borrador.");
  const anio = Number(datos.anio_gravable);
  if (!Number.isInteger(anio) || anio < 2021 || anio > 2030) throw new Error("El año gravable no es válido.");
  if (!Array.isArray(datos.casillas) || datos.casillas.length > 400) throw new Error("Las casillas no son válidas.");
  const casillas = [];
  for (const c of datos.casillas) {
    const numero = Number(c?.numero);
    const valor = Number(c?.valor);
    const tipo = ["dato", "calculada", "informativa"].includes(c?.tipo) ? c.tipo : null;
    if (!Number.isInteger(numero) || numero < 1 || numero > 999 || !Number.isFinite(valor) || valor < 0 || valor > 1e14 || !tipo) continue;
    const texto = typeof c.texto === "string" ? c.texto.slice(0, 40) : null;
    const escribir = (tipo === "dato" && valor > 0) || (tipo === "informativa" && texto != null && !["0", "no", ""].includes(texto.trim().toLowerCase()));
    casillas.push({ numero, nombre: String(c.nombre || "").slice(0, 160), valor, tipo, texto: escribir && tipo === "informativa" ? texto : null, escribir });
  }
  if (!casillas.some((c) => c.escribir)) throw new Error("El borrador no tiene casillas con valor para escribir.");
  return { anio, casillas };
}

// ---------- Llenar ----------

async function ejecutarEnMarcos(tabId, func, args = [], soloPrincipal = false) {
  const res = await chrome.scripting.executeScript({ target: soloPrincipal ? { tabId, frameIds: [0] } : { tabId, allFrames: true }, func, args });
  return res.map((r) => r.result).filter(Boolean);
}

async function llenarEn(tabId) {
  const f = await borrador();
  if (!f) return { ok: false, error: "No tengo un borrador. En DeclaraFácil, en «Presentar en la DIAN», toca «Llenar con la extensión»." };
  const mapa = (await mapas())["210"] || {};
  const marcos = await ejecutarEnMarcos(tabId, (c, m) => (window.__df ? window.__df.llenar(c, m) : null), [f.casillas, mapa]);
  const conCampos = marcos.filter((r) => r.campos > 0);
  if (!conCampos.length) return { ok: false, error: "Esta página no tiene campos para llenar. Abre el formulario 210 en MUISCA." };

  const llenadas = new Map();
  const bloqueadas = new Map();
  const noQuedaron = new Set();
  const calculadas = new Map();
  for (const r of conCampos) {
    r.llenadas.forEach((x) => llenadas.set(x.n, x));
    r.bloqueadas.forEach((x) => bloqueadas.set(x.n, x));
    r.noQuedaron.forEach((n) => noQuedaron.add(n));
    r.calculadas.forEach((x) => calculadas.set(x.n, x));
  }
  const vistas = new Set([...llenadas.keys(), ...bloqueadas.keys(), ...noQuedaron]);
  const noEncontradas = f.casillas.filter((c) => c.escribir && !vistas.has(c.numero)).map((c) => c.numero);
  const anioPagina = conCampos.map((r) => r.anioPagina).find(Boolean) || null;
  const resumen = {
    anio: f.anio,
    llenadas: [...llenadas.values()],
    bloqueadas: [...bloqueadas.values()],
    noQuedaron: [...noQuedaron],
    noEncontradas,
    calculadas: [...calculadas.values()],
    anioPagina,
    avisoAnio: anioPagina && anioPagina !== f.anio ? `Ojo: la página dice año gravable ${anioPagina} y tu borrador es de ${f.anio}.` : null,
    cuando: Date.now(),
  };
  await sesion.poner({ ultimoLlenado: resumen });
  await chrome.tabs.sendMessage(tabId, { tipo: "panel:resumen", resumen }, { frameId: 0 }).catch(() => {});
  return { ok: true, resumen };
}

async function pedirEnsenar(tabId) {
  const f = await borrador();
  const ultimo = await sesion.leer("ultimoLlenado");
  const faltan = new Set([...(ultimo?.noEncontradas || []), ...(ultimo?.noQuedaron || [])]);
  const pendientes = (f?.casillas || []).filter((c) => c.escribir && (faltan.size ? faltan.has(c.numero) : true)).map((c) => ({ n: c.numero, nombre: c.nombre }));
  await chrome.tabs.sendMessage(tabId, { tipo: "panel:ensenar", pendientes: pendientes.slice(0, 60) }, { frameId: 0 }).catch(() => {});
  return { ok: true, pendientes: pendientes.length };
}

async function ensenar(tabId, n) {
  if (n == null) {
    await ejecutarEnMarcos(tabId, () => window.__df?.cancelarEnsenar());
    return pedirEnsenar(tabId);
  }
  const f = await borrador();
  const c = f?.casillas.find((x) => x.numero === n);
  const valor = c?.escribir ? (c.texto ?? String(Math.round(c.valor))) : null;
  await ejecutarEnMarcos(tabId, (num, v) => window.__df?.ensenar(num, v), [n, valor]);
  return { ok: true };
}

async function aprendido(tabId, n, selector) {
  if (!Number.isInteger(n) || !selector || typeof selector !== "object") return { ok: false };
  const todos = await mapas();
  const limpio = { id: selector.id ? String(selector.id).slice(0, 200) : null, name: selector.name ? String(selector.name).slice(0, 200) : null, css: selector.css ? String(selector.css).slice(0, 400) : null };
  todos["210"] = { ...(todos["210"] || {}), [n]: limpio };
  await chrome.storage.local.set({ mapas: todos });
  await ejecutarEnMarcos(tabId, () => window.__df?.cancelarEnsenar());
  const ultimo = await sesion.leer("ultimoLlenado");
  if (ultimo) {
    ultimo.noEncontradas = ultimo.noEncontradas.filter((x) => x !== n);
    ultimo.noQuedaron = ultimo.noQuedaron.filter((x) => x !== n);
    await sesion.poner({ ultimoLlenado: ultimo });
  }
  const quedan = ultimo ? ultimo.noEncontradas.length + ultimo.noQuedaron.length : 0;
  await chrome.tabs.sendMessage(tabId, { tipo: "panel:aprendido", n, escrita: true, quedan }, { frameId: 0 }).catch(() => {});
  return { ok: true };
}

// ---------- Exógena ----------

async function pestanaApp() {
  const lista = (await sesion.leer("pestanasApp")) || [];
  for (const p of lista.sort((a, b) => b.cuando - a.cuando)) {
    try {
      const t = await chrome.tabs.get(p.tabId);
      if (t) return p.tabId;
    } catch {
      /* la cerraron */
    }
  }
  return null;
}

async function registrarApp(tabId) {
  const lista = ((await sesion.leer("pestanasApp")) || []).filter((p) => p.tabId !== tabId);
  lista.push({ tabId, cuando: Date.now() });
  await sesion.poner({ pestanasApp: lista.slice(-5) });
}

async function iniciarExogena(anio, appTab) {
  anio = Number(anio);
  if (!Number.isInteger(anio) || anio < 2019 || anio > 2030) throw new Error("El año no es válido.");
  const abiertas = await chrome.tabs.query({ url: "https://*.dian.gov.co/*" });
  let tab = abiertas.find((t) => t.active) || abiertas[0];
  if (tab) {
    await chrome.tabs.update(tab.id, { active: true });
    await chrome.windows.update(tab.windowId, { focused: true }).catch(() => {});
  } else {
    tab = await chrome.tabs.create({ url: MUISCA });
  }
  await sesion.poner({ flujo: { activo: true, anio, appTab: appTab ?? null, dianTab: tab.id, intentos: {}, inicio: Date.now() } });
  // Si la pestaña ya estaba cargada, se le avisa a cada marco que empiece (si es nueva, empieza sola al cargar)
  await chrome.tabs.sendMessage(tab.id, { tipo: "flujo:iniciar", anio }).catch(() => {});
  return { ok: true, nueva: !abiertas.length };
}

async function flujoDe(tabId) {
  const f = await sesion.leer("flujo");
  if (!f?.activo) return null;
  if (Date.now() - f.inicio > 20 * 60 * 1000) {
    await sesion.quitar("flujo");
    return null;
  }
  if (f.dianTab !== tabId) return null;
  return f;
}

async function paso(tabId, clave) {
  const f = await flujoDe(tabId);
  if (!f) return { seguir: false };
  f.intentos[clave] = (f.intentos[clave] || 0) + 1;
  await sesion.poner({ flujo: f });
  return { seguir: f.intentos[clave] <= MAX_INTENTOS };
}

const bytesDeBase64 = (b64) => Math.floor((b64.length * 3) / 4);

async function entregarExogena(archivo, tabDian) {
  const f = await sesion.leer("flujo");
  await sesion.quitar("flujo");
  const appTab = f?.appTab ?? (await pestanaApp());
  let entregado = false;
  if (appTab != null) {
    entregado = await chrome.tabs
      .sendMessage(appTab, { tipo: "app:exogena", ...archivo })
      .then((r) => !!r?.ok)
      .catch(() => false);
  }
  if (entregado) {
    const t = await chrome.tabs.get(appTab).catch(() => null);
    if (t) {
      await chrome.tabs.update(appTab, { active: true });
      await chrome.windows.update(t.windowId, { focused: true }).catch(() => {});
    }
  } else {
    await sesion.poner({ pendiente: { ...archivo, cuando: Date.now() } });
  }
  const { opciones } = await chrome.storage.local.get("opciones");
  if (opciones?.copia) {
    await chrome.downloads.download({ url: `data:${archivo.mime || "application/octet-stream"};base64,${archivo.base64}`, filename: archivo.nombre, conflictAction: "uniquify" }).catch(() => {});
  }
  if (tabDian != null) await chrome.tabs.sendMessage(tabDian, { tipo: "panel:exogena", estado: entregado ? "entregada" : "pendiente" }, { frameId: 0 }).catch(() => {});
  return { ok: true, entregado };
}

function validarArchivo(m) {
  if (typeof m.base64 !== "string" || !m.base64.length || bytesDeBase64(m.base64) > MAX_ARCHIVO) throw new Error("El archivo no es válido.");
  const nombre = String(m.nombre || "exogena.xlsx").replace(/[\\/:*?"<>|]+/g, "_").slice(0, 120) || "exogena.xlsx";
  return { nombre, mime: String(m.mime || "").slice(0, 120), base64: m.base64 };
}

// Último recurso: si la página descargó el archivo por su cuenta (un enlace GET), se pide otra vez con la misma sesión
chrome.downloads.onCreated.addListener(async (item) => {
  const f = await sesion.leer("flujo");
  const url = item.finalUrl || item.url;
  if (!f?.activo || !ES_DIAN.test(url || "")) return;
  try {
    const r = await fetch(url, { credentials: "include" });
    const tipo = r.headers.get("content-type") || "";
    if (!r.ok || /text\/html/i.test(tipo)) throw new Error("no es un archivo");
    const buf = new Uint8Array(await r.arrayBuffer());
    let s = "";
    for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    const disp = r.headers.get("content-disposition") || "";
    const nombre = (/filename="?([^";]+)"?/i.exec(disp)?.[1] || new URL(url).pathname.split("/").pop() || "exogena.xlsx").trim();
    await entregarExogena(validarArchivo({ nombre, mime: tipo, base64: btoa(s) }), f.dianTab);
  } catch {
    // No se pudo repetir (era una petición POST): queda en Descargas y la app le dice que la suba
    const appTab = f.appTab ?? (await pestanaApp());
    if (appTab != null) await chrome.tabs.sendMessage(appTab, { tipo: "app:exogena-en-descargas" }).catch(() => {});
    if (f.dianTab != null) await chrome.tabs.sendMessage(f.dianTab, { tipo: "panel:exogena", estado: "error", texto: "Se descargó en tu carpeta de Descargas. Arrástrala a DeclaraFácil." }, { frameId: 0 }).catch(() => {});
  }
});

// ---------- Mensajes ----------

const deApp = (s) => !!s.tab && ORIGENES_APP.some((r) => r.test(s.url || ""));
const deDian = (s) => !!s.tab && ES_DIAN.test(s.url || "");
const dePopup = (s) => s.id === chrome.runtime.id && (s.url || "").startsWith(chrome.runtime.getURL("popup.html"));

async function pestanaActiva() {
  const [t] = await chrome.tabs.query({ active: true, currentWindow: true });
  return t || null;
}

async function manejar(m, s) {
  const tipo = String(m?.tipo || "");
  // Desde DeclaraFácil
  if (tipo.startsWith("df:")) {
    if (!deApp(s)) throw new Error("Origen no permitido");
    if (tipo === "df:hola") {
      await registrarApp(s.tab.id);
      const pendiente = await sesion.leer("pendiente");
      let archivo = null;
      if (pendiente && Date.now() - pendiente.cuando < VIDA_PENDIENTE) {
        archivo = { nombre: pendiente.nombre, mime: pendiente.mime, base64: pendiente.base64 };
        await sesion.quitar("pendiente");
      }
      return { ok: true, version: chrome.runtime.getManifest().version, borrador: resumenBorrador(await borrador()), archivo };
    }
    if (tipo === "df:formulario") {
      const datos = validarFormulario(m.datos);
      await sesion.poner({ formulario: { ...datos, recibido: Date.now() }, ultimoLlenado: null });
      return { ok: true, escribir: datos.casillas.filter((c) => c.escribir).length };
    }
    if (tipo === "df:pedir-exogena") return iniciarExogena(m.anio, s.tab.id);
  }
  // Desde las páginas de la DIAN
  if (tipo.startsWith("m:")) {
    if (!deDian(s)) throw new Error("Origen no permitido");
    const tabId = s.tab.id;
    if (tipo === "m:hola") {
      const f = await flujoDe(tabId);
      return { formulario: resumenBorrador(await borrador()), flujo: f ? { anio: f.anio } : null };
    }
    if (tipo === "m:llenar") return llenarEn(tabId);
    if (tipo === "m:pedir-ensenar") return pedirEnsenar(tabId);
    if (tipo === "m:ensenar") return ensenar(tabId, m.n == null ? null : Number(m.n));
    if (tipo === "m:aprendido") return aprendido(tabId, Number(m.n), m.selector);
    if (tipo === "m:paso") return paso(tabId, String(m.clave || ""));
    if (tipo === "m:detener") {
      await sesion.quitar("flujo");
      return { ok: true };
    }
    if (tipo === "m:archivo") {
      const f = await flujoDe(tabId);
      if (!f) return { ok: false, error: "No hay un pedido de exógena activo." };
      return entregarExogena(validarArchivo(m), tabId);
    }
  }
  // Desde la ventanita de la extensión
  if (tipo.startsWith("p:")) {
    if (!dePopup(s)) throw new Error("Origen no permitido");
    const t = await pestanaActiva();
    const enDian = !!t && ES_DIAN.test(t.url || "");
    if (tipo === "p:estado") {
      const { opciones } = await chrome.storage.local.get("opciones");
      const aprendidas = Object.keys((await mapas())["210"] || {}).length;
      return { borrador: resumenBorrador(await borrador()), flujo: (await sesion.leer("flujo")) || null, ultimo: (await sesion.leer("ultimoLlenado")) || null, enDian, opciones: opciones || {}, aprendidas, pendiente: !!(await sesion.leer("pendiente")) };
    }
    if (tipo === "p:llenar") return enDian ? llenarEn(t.id) : { ok: false, error: "Abre el formulario 210 en MUISCA y vuelve a tocar el botón." };
    if (tipo === "p:ensenar") return enDian ? pedirEnsenar(t.id) : { ok: false, error: "Abre el formulario 210 en MUISCA." };
    if (tipo === "p:exogena") return iniciarExogena(m.anio, await pestanaApp());
    if (tipo === "p:diagnostico") {
      if (!enDian) return { ok: false, error: "Abre una página de MUISCA." };
      const marcos = await ejecutarEnMarcos(t.id, () => (window.__df ? window.__df.diagnostico() : null));
      return { ok: true, diagnostico: { extension: chrome.runtime.getManifest().version, fecha: new Date().toISOString(), marcos } };
    }
    if (tipo === "p:opciones") {
      await chrome.storage.local.set({ opciones: { copia: !!m.copia } });
      return { ok: true };
    }
    if (tipo === "p:borrar") {
      await chrome.storage.session.clear();
      return { ok: true };
    }
    if (tipo === "p:olvidar") {
      await chrome.storage.local.remove("mapas");
      return { ok: true };
    }
    if (tipo === "p:exportar-mapa") return { ok: true, mapa: (await mapas())["210"] || {} };
  }
  throw new Error("Mensaje desconocido");
}

chrome.runtime.onMessage.addListener((m, s, responder) => {
  manejar(m, s).then(responder, (e) => responder({ ok: false, error: String(e?.message || e) }));
  return true;
});
