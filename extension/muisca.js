/* DeclaraFácil — corre en las páginas de la DIAN (en cada marco).
 *
 * - Llena las casillas del formulario 210 cuando la persona lo pide (botón «Llenar casillas»).
 * - Trae la exógena: recorre los pasos de «Consultar información exógena» con la sesión que ya
 *   está abierta y atrapa el archivo (lo hace captura.js). La persona inicia sesión siempre ella.
 * - Aprende dónde está una casilla cuando la persona le muestra el campo.
 * - Arma un diagnóstico de la página (sin valores) para mejorar la extensión.
 * Nunca hace clic en firmar, presentar, pagar ni nada parecido, y nunca lee contraseñas.
 */
(() => {
  if (window.__df || !window.DF) return;
  const DF = window.DF;
  const ES_TOP = window === window.top;
  const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
  const enviar = (m) => chrome.runtime.sendMessage(m).catch(() => null);
  const pesos = (n) => "$" + Math.round(n).toLocaleString("es-CO");

  // ---------- Panel (solo en el marco principal) ----------

  const panel = (() => {
    let host = null;
    let cuerpo = null;
    const crear = () => {
      if (host?.isConnected) return true;
      if (document.querySelector("frameset")) return false;
      // MUISCA puede tener dos <body>: el panel va en el que tiene el contenido
      const destino = Array.from(document.querySelectorAll("body")).sort((a, b) => b.childElementCount - a.childElementCount)[0];
      if (!destino) return false;
      host = document.createElement("div");
      host.id = "declarafacil-panel";
      host.style.cssText = "all: initial; position: fixed; right: 16px; bottom: 16px; z-index: 2147483647;";
      const raiz = host.attachShadow({ mode: "closed" });
      const estilo = document.createElement("style");
      estilo.textContent = `
        .caja { font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #123b33; background: #eef2ea;
          border: 1px solid #123b33; border-radius: 14px; box-shadow: 0 10px 30px rgba(18,59,51,.25); width: 330px; max-height: 70vh; overflow: auto; }
        .cabeza { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #123b33; color: #eef2ea; border-radius: 13px 13px 0 0; }
        .cabeza b { flex: 1; font-size: 14px; letter-spacing: .01em; }
        .sello { width: 18px; height: 18px; border-radius: 5px; background: #5a3bc0; display: inline-block; }
        .x { all: unset; cursor: pointer; padding: 0 4px; font-size: 18px; line-height: 1; }
        .cuerpo { padding: 12px; display: grid; gap: 8px; }
        p { margin: 0; }
        .suave { color: #48635c; font-size: 12.5px; }
        .boton { all: unset; cursor: pointer; background: #5a3bc0; color: #fff; border-radius: 999px; padding: 8px 14px; font-weight: 600; text-align: center; }
        .boton.sec { background: transparent; color: #123b33; border: 1px solid #123b33; }
        .boton:focus-visible, .chip:focus-visible, .x:focus-visible { outline: 2px solid #5a3bc0; outline-offset: 2px; }
        .fila { display: flex; gap: 8px; flex-wrap: wrap; }
        .lista { margin: 0; padding-left: 18px; }
        .chip { all: unset; cursor: pointer; border: 1px solid #5a3bc0; color: #5a3bc0; border-radius: 999px; padding: 2px 9px; font-size: 13px; }
        .ok { color: #1f6b48; font-weight: 600; } .mal { color: #a2312a; font-weight: 600; }
      `;
      const caja = document.createElement("div");
      caja.className = "caja";
      caja.setAttribute("role", "dialog");
      caja.setAttribute("aria-label", "DeclaraFácil");
      const cabeza = document.createElement("div");
      cabeza.className = "cabeza";
      const sello = document.createElement("span");
      sello.className = "sello";
      const titulo = document.createElement("b");
      titulo.textContent = "DeclaraFácil";
      const cerrar = document.createElement("button");
      cerrar.className = "x";
      cerrar.textContent = "×";
      cerrar.setAttribute("aria-label", "Ocultar");
      cerrar.addEventListener("click", () => host.remove());
      cabeza.append(sello, titulo, cerrar);
      cuerpo = document.createElement("div");
      cuerpo.className = "cuerpo";
      cuerpo.setAttribute("aria-live", "polite");
      caja.append(cabeza, cuerpo);
      raiz.append(estilo, caja);
      destino.appendChild(host);
      return true;
    };
    const el = (tag, clase, texto) => {
      const x = document.createElement(tag);
      if (clase) x.className = clase;
      if (texto != null) x.textContent = texto;
      return x;
    };
    const boton = (texto, accion, secundario) => {
      const b = el("button", secundario ? "boton sec" : "boton", texto);
      b.addEventListener("click", accion);
      return b;
    };
    return {
      el,
      boton,
      /** Cambia el contenido del panel (los nodos se arman con textContent: nada de HTML con datos). */
      poner(...nodos) {
        if (!ES_TOP && !esMarcoGrande()) return;
        if (!crear()) return;
        cuerpo.replaceChildren(...nodos.filter(Boolean));
      },
      quitar() {
        host?.remove();
      },
    };
  })();

  /** Si la página principal es un frameset, el panel va en el marco grande. */
  const esMarcoGrande = () => {
    try {
      return window.parent === window.top && window.top.document.body?.tagName === "FRAMESET" && innerWidth >= 600 && innerHeight >= 300;
    } catch {
      return false;
    }
  };

  // ---------- Llenar el formulario ----------

  async function llenar(casillas, mapa) {
    const r = { ruta: location.pathname, campos: 0, llenadas: [], bloqueadas: [], noEncontradas: [], noQuedaron: [], calculadas: [], anioPagina: DF.anioDeLaPagina() };
    r.campos = Array.from(document.querySelectorAll(DF.CAMPOS)).filter(DF.esCampo).length;
    if (!r.campos) return r;
    const usados = new Set();
    for (const c of casillas.filter((x) => x.escribir)) {
      const hallado = DF.buscarCampo(c.numero, mapa, usados);
      if (!hallado) {
        r.noEncontradas.push(c.numero);
        continue;
      }
      usados.add(hallado.el);
      if (DF.bloqueado(hallado.el)) {
        r.bloqueadas.push({ n: c.numero, enPagina: DF.leerNumero(hallado.el) });
        continue;
      }
      const valor = c.texto ?? String(Math.round(c.valor));
      const escrito = DF.escribir(hallado.el, valor);
      await esperar(30);
      const quedo = escrito && (c.texto != null || DF.leerNumero(hallado.el) === Math.round(c.valor));
      if (quedo) {
        r.llenadas.push({ n: c.numero, como: hallado.como });
        DF.resaltar(hallado.el, "#1f8a5b");
      } else {
        r.noQuedaron.push(c.numero);
        DF.resaltar(hallado.el, "#c0392b");
      }
    }
    // MUISCA recalcula sus totales al salir de cada casilla: se espera y se comparan con el borrador
    await esperar(1500);
    for (const c of casillas.filter((x) => x.tipo === "calculada")) {
      const hallado = DF.buscarCampo(c.numero, mapa, usados);
      if (!hallado) continue;
      usados.add(hallado.el);
      const v = DF.leerNumero(hallado.el);
      if (v !== null) r.calculadas.push({ n: c.numero, muisca: v, borrador: Math.round(c.valor) });
    }
    return r;
  }

  function mostrarResumen(res) {
    const P = panel;
    if (!res.llenadas.length && !res.noEncontradas.length) {
      P.poner(P.el("p", null, "No encontré casillas para llenar en esta página. Abre «Diligenciar y presentar formulario 210», versión para expertos, y vuelve a tocar «Llenar casillas»."));
      return;
    }
    const nodos = [P.el("p", "ok", `Escribí ${res.llenadas.length} casilla${res.llenadas.length === 1 ? "" : "s"} (en verde).`)];
    if (res.avisoAnio) nodos.push(P.el("p", "mal", res.avisoAnio));
    if (res.noQuedaron.length) nodos.push(P.el("p", "mal", `No quedaron bien (en rojo): ${res.noQuedaron.join(", ")}. Escríbelas tú.`));
    if (res.bloqueadas.length) nodos.push(P.el("p", "suave", `MUISCA no deja escribir en: ${res.bloqueadas.map((b) => b.n).join(", ")}.`));
    const distintas = res.calculadas.filter((c) => c.muisca !== c.borrador);
    if (res.calculadas.length) {
      nodos.push(
        distintas.length
          ? P.el("p", "mal", "Totales que MUISCA calculó distinto: " + distintas.map((c) => `${c.n} (MUISCA ${pesos(c.muisca)}, borrador ${pesos(c.borrador)})`).join("; ") + ".")
          : P.el("p", "ok", res.calculadas.length === 1 ? "El total que calcula MUISCA cuadra con tu borrador." : `Los ${res.calculadas.length} totales que calcula MUISCA cuadran con tu borrador.`),
      );
    }
    if (res.noEncontradas.length) {
      nodos.push(P.el("p", null, `No encontré el campo de: ${res.noEncontradas.join(", ")}.`));
      nodos.push(P.boton("Mostrarme dónde están", () => void enviar({ tipo: "m:pedir-ensenar" }), true));
    }
    nodos.push(P.el("p", "suave", "Revisa cada casilla antes de firmar. La firma y la presentación son tuyas: yo no toco esos botones."));
    P.poner(...nodos);
  }

  // ---------- Enseñar dónde está una casilla ----------

  let ensenando = null;
  let estiloEnsenar = null;

  function ensenar(n, valor) {
    cancelarEnsenar();
    ensenando = { n, valor };
    estiloEnsenar = document.createElement("style");
    estiloEnsenar.textContent = `${DF.CAMPOS.split(",").map((s) => s.trim() + ":hover").join(",")} { outline: 3px dashed #5a3bc0 !important; cursor: crosshair !important; }`;
    (document.head || document.documentElement).appendChild(estiloEnsenar);
    document.addEventListener("click", alClicEnsenar, true);
    return true;
  }

  function cancelarEnsenar() {
    ensenando = null;
    estiloEnsenar?.remove();
    document.removeEventListener("click", alClicEnsenar, true);
    return true;
  }

  function alClicEnsenar(e) {
    const el = e.target?.closest?.(DF.CAMPOS);
    if (!ensenando || !DF.esCampo(el)) return;
    e.preventDefault();
    e.stopPropagation();
    const { n, valor } = ensenando;
    if (valor != null && !DF.bloqueado(el) && DF.escribir(el, valor)) DF.resaltar(el, "#1f8a5b");
    void enviar({ tipo: "m:aprendido", n, selector: DF.selectorDe(el) });
    cancelarEnsenar();
  }

  function mostrarEnsenar(pendientes) {
    const P = panel;
    if (!pendientes.length) {
      P.poner(P.el("p", null, "No hay casillas pendientes por ubicar."));
      return;
    }
    const fila = P.el("div", "fila");
    for (const c of pendientes) {
      const chip = P.el("button", "chip", String(c.n));
      chip.title = c.nombre;
      chip.addEventListener("click", () => {
        void enviar({ tipo: "m:ensenar", n: c.n });
        P.poner(P.el("p", null, `Ahora haz clic en el campo de la casilla ${c.n} (${c.nombre}) en el formulario.`), P.boton("Cancelar", () => void enviar({ tipo: "m:ensenar", n: null }), true));
      });
      fila.append(chip);
    }
    P.poner(P.el("p", null, "Toca una casilla y luego haz clic en su campo en el formulario. La recuerdo para la próxima vez."), fila);
  }

  // ---------- Traer la exógena ----------

  const armarCaptura = (si) => document.dispatchEvent(new CustomEvent("df-armar", { detail: JSON.stringify({ armado: !!si }) }));

  document.addEventListener("df-archivo", (e) => {
    let d;
    try {
      d = JSON.parse(e.detail);
    } catch {
      return;
    }
    if (!d || typeof d.base64 !== "string") return;
    flujo = null;
    panel.poner(panel.el("p", null, "Recibí el archivo. Lo estoy pasando a DeclaraFácil…"));
    void enviar({ tipo: "m:archivo", nombre: String(d.nombre || "exogena.xlsx").slice(0, 120), mime: String(d.mime || "").slice(0, 120), base64: d.base64 });
  });

  const MENU = /consultar informacion exogena|informacion reportada por terceros|consulta (de )?(la )?informacion exogena|^informacion exogena$|^exogena$/;
  const ACEPTA = /acepto|aceptar (los )?terminos|terminos y condiciones|condiciones (de uso|del servicio)|he leido|autorizo|declaro que/;
  const FINAL = /^(consultar|buscar|generar|generar reporte|descargar|descargar archivo|descargar excel|exportar|exportar a excel|excel|ver reporte|consultar reporte)$/;
  const SEGUIR = /^(aceptar|continuar|siguiente)$/;

  const CLICABLES = 'a, button, input[type="submit"], input[type="button"], input[type="image"], [role="button"], [role="menuitem"], [role="link"], [onclick]';

  /** El elemento visible más específico cuyo texto cumple el patrón (nunca uno peligroso). */
  const hallar = (patron, selector = CLICABLES) => {
    const candidatos = Array.from(document.querySelectorAll(selector)).filter((el) => {
      const t = DF.norm(DF.textoDe(el));
      return t && t.length <= 90 && patron.test(t) && !DF.PELIGRO.test(t) && DF.visible(el);
    });
    candidatos.sort((a, b) => DF.textoDe(a).length - DF.textoDe(b).length);
    return candidatos[0] || null;
  };

  const textoCerca = (el) => DF.norm([el.labels ? Array.from(el.labels, (l) => l.innerText).join(" ") : "", el.closest("label, tr, li, p, div")?.innerText || ""].join(" ").slice(0, 400));

  function siguienteAccion(anio, hechos) {
    const clave = Array.from(document.querySelectorAll('input[type="password"]')).find(DF.visible);
    if (clave) return { clave: "login", texto: "Inicia sesión en MUISCA con tu usuario y contraseña (eso lo haces tú). Cuando entres, sigo yo." };

    if (!hechos.has("acepto")) {
      const caja = Array.from(document.querySelectorAll('input[type="checkbox"], input[type="radio"]')).find((c) => !c.checked && DF.visible(c) && ACEPTA.test(textoCerca(c)));
      if (caja) return { clave: "acepto", texto: "Acepto las condiciones del servicio de consulta.", hacer: () => caja.click() };
      // En MUISCA las condiciones se aceptan con un botón «Aceptar» debajo del texto (sin casilla)
      if (/condiciones|terminos/.test(DF.textoPagina())) {
        const b = hallar(/^(aceptar|acepto|aceptar condiciones)$/);
        if (b)
          return {
            clave: "acepto",
            texto: "Acepto las condiciones del servicio de consulta.",
            hacer: () => {
              hechos.add("seguir"); // ese mismo botón era el «continuar»
              b.click();
            },
          };
      }
    }
    if (hechos.has("acepto") && !hechos.has("seguir")) {
      const b = hallar(SEGUIR);
      if (b) return { clave: "seguir", texto: "Continúo.", hacer: () => b.click() };
    }
    if (!hechos.has("anio")) {
      for (const s of document.querySelectorAll("select")) {
        if (!DF.visible(s) || s.disabled) continue;
        const op = Array.from(s.options).find((o) => new RegExp(`\\b${anio}\\b`).test(o.text) || o.value === String(anio));
        const anios = Array.from(s.options, (o) => (o.text.match(/\b(20\d{2})\b/) || [])[1]).filter(Boolean);
        if (!op && anios.length >= 2)
          return { clave: "sin_anio", texto: `La DIAN todavía no tiene la exógena del año gravable ${anio}. En la consulta solo aparecen ${anios.join(", ")}.` };
        if (op && s.value !== op.value) return { clave: "anio", texto: `Elijo el año gravable ${anio}.`, hacer: () => DF.escribir(s, op.value) };
        if (op) hechos.add("anio");
      }
      const caja = Array.from(document.querySelectorAll('input[type="text"], input[type="number"], input:not([type])')).find(
        (i) => DF.visible(i) && !DF.bloqueado(i) && /\bano\b|periodo|vigencia/.test(textoCerca(i)) && (i.maxLength === 4 || /ano/.test(DF.norm(i.id + " " + i.name))) && i.value !== String(anio),
      );
      if (caja) return { clave: "anio", texto: `Escribo el año gravable ${anio}.`, hacer: () => DF.escribir(caja, String(anio)) };
    }
    if (!hechos.has("final")) {
      const b = hallar(FINAL);
      if (b) return { clave: "final", texto: "Consulto tu exógena. En cuanto llegue el archivo, lo paso a DeclaraFácil.", hacer: () => b.click() };
    }
    if (!hechos.has("menu") && !hechos.has("final")) {
      const m = hallar(MENU) || hallar(MENU, "div, span, li, p, h2, h3, h4, td");
      if (m) return { clave: "menu", texto: "Abro «Consultar información exógena».", hacer: () => m.click() };
    }
    return null;
  }

  let flujo = null;

  async function recorrerExogena() {
    if (!flujo) return;
    armarCaptura(true);
    // Lo que ya se hizo en otra página del mismo pedido no se repite (aceptar las condiciones)
    const hechos = new Set(flujo.aceptado ? ["acepto", "seguir"] : []);
    let quieto = 0;
    let avisoLogin = false;
    while (flujo && quieto < 40) {
      const a = siguienteAccion(flujo.anio, hechos);
      if (a?.clave === "sin_anio") {
        mostrarFlujo(a.texto);
        void enviar({ tipo: "m:detener" });
        flujo = null;
        return;
      }
      if (a?.clave === "login") {
        if (!avisoLogin) mostrarFlujo(a.texto);
        avisoLogin = true;
        await esperar(1000);
        continue;
      }
      if (a) {
        if (a.clave === "menu" || a.clave === "final" || a.clave === "acepto") {
          const r = await enviar({ tipo: "m:paso", clave: a.clave });
          if (!r?.seguir) {
            mostrarFlujo("Ya lo intenté varias veces y no avanzo. Hazlo tú: acepta las condiciones, elige el año y toca «Consultar». Yo atrapo el archivo.");
            return;
          }
        }
        hechos.add(a.clave);
        mostrarFlujo(a.texto);
        a.hacer();
        quieto = 0;
        await esperar(a.clave === "final" ? 4000 : 1200);
        continue;
      }
      quieto++;
      await esperar(500);
    }
    if (flujo && !hechos.has("final")) {
      mostrarFlujo(`No encontré el siguiente paso en esta página. Busca «Consultar información exógena», acepta las condiciones, elige el año ${flujo.anio} y toca «Consultar». Yo atrapo el archivo.`);
    }
  }

  function mostrarFlujo(texto) {
    if (!ES_TOP && !esMarcoGrande()) return;
    panel.poner(
      panel.el("p", null, texto),
      panel.el("p", "suave", "Solo leo y descargo tu exógena. No guardo tu clave ni firmo nada."),
      panel.boton("Detener", () => {
        flujo = null;
        armarCaptura(false);
        void enviar({ tipo: "m:detener" });
        panel.poner(panel.el("p", null, "Listo, me detuve."));
      }, true),
    );
  }

  // ---------- Diagnóstico (sin valores) ----------

  const rutaSinConsulta = (href) => {
    try {
      const u = new URL(href, location.href);
      return u.protocol === "javascript:" ? "javascript:" : u.hostname + u.pathname;
    } catch {
      return null;
    }
  };

  function diagnostico() {
    const cerca = (el) => {
      const l = el.labels?.[0]?.innerText || el.closest("td")?.previousElementSibling?.innerText || el.parentElement?.innerText || "";
      return DF.enmascarar(l.replace(/\s+/g, " ").trim());
    };
    const campos = Array.from(document.querySelectorAll("input, select, textarea"))
      .filter((el) => el.type !== "hidden" && el.type !== "password")
      .slice(0, 500)
      .map((el) => ({
        etiqueta: el.tagName.toLowerCase(),
        tipo: el.type || null,
        id: el.id || null,
        name: el.getAttribute("name"),
        clase: typeof el.className === "string" ? el.className.slice(0, 80) : null,
        title: DF.enmascarar(el.title) || null,
        aria: DF.enmascarar(el.getAttribute("aria-label")) || null,
        soloLectura: DF.bloqueado(el),
        visible: DF.visible(el),
        maxlength: el.maxLength > 0 ? el.maxLength : null,
        casillaDetectada: DF.numeroEnAtributos(el),
        cerca: cerca(el),
      }));
    const acciones = Array.from(document.querySelectorAll(CLICABLES))
      .filter(DF.visible)
      .slice(0, 250)
      .map((el) => ({ etiqueta: el.tagName.toLowerCase(), id: el.id || null, texto: DF.enmascarar(DF.textoDe(el)), destino: el.tagName === "A" ? rutaSinConsulta(el.href) : null }));
    const numeros = new Set();
    for (const el of document.querySelectorAll("td, th, span, div, label, b, strong, font")) {
      const t = DF.textoPropio(el);
      if (/^\(?\d{1,3}\)?\.?$/.test(t) && DF.visible(el)) numeros.add(Number(t.replace(/\D/g, "")));
    }
    return {
      ruta: location.hostname + location.pathname,
      titulo: DF.enmascarar(document.title),
      marcoPrincipal: ES_TOP,
      formularios: Array.from(document.forms, (f) => ({ id: f.id || null, metodo: (f.getAttribute("method") || "get").toLowerCase(), accion: rutaSinConsulta(f.getAttribute("action") || location.href) })),
      campos,
      acciones,
      numerosEnPantalla: [...numeros].sort((a, b) => a - b).slice(0, 300),
      anioPagina: DF.anioDeLaPagina(),
    };
  }

  // ---------- Mensajes de la extensión ----------

  chrome.runtime.onMessage.addListener((m) => {
    if (m?.tipo === "panel:resumen") mostrarResumen(m.resumen);
    else if (m?.tipo === "panel:ensenar") mostrarEnsenar(m.pendientes || []);
    else if (m?.tipo === "panel:aprendido") panel.poner(panel.el("p", "ok", `Listo: ya sé dónde va la casilla ${m.n}${m.escrita ? " y la escribí" : ""}.`), m.quedan ? panel.boton("Ubicar otra", () => void enviar({ tipo: "m:pedir-ensenar" }), true) : null);
    else if (m?.tipo === "panel:exogena") {
      const P = panel;
      if (m.estado === "entregada") P.poner(P.el("p", "ok", "Tu exógena ya está en DeclaraFácil. Puedes cerrar esta pestaña."));
      else if (m.estado === "pendiente") P.poner(P.el("p", "ok", "Tengo tu exógena. Abre DeclaraFácil y te la paso (la guardo 10 minutos, solo en memoria)."));
      else P.poner(P.el("p", "mal", m.texto || "No pude pasar el archivo. Descárgalo y súbelo en DeclaraFácil."));
    } else if (m?.tipo === "flujo:iniciar" && m.anio && !flujo) {
      flujo = { anio: m.anio };
      void recorrerExogena();
    }
  });

  window.__df = { llenar, diagnostico, ensenar, cancelarEnsenar, mostrarResumen, mostrarEnsenar };

  // ---------- Al cargar ----------

  const pareceFormulario210 = () => {
    const campos = Array.from(document.querySelectorAll(DF.CAMPOS)).filter(DF.esCampo).length;
    const texto = DF.textoPagina();
    return campos >= 15 && /\b210\b/.test(texto) && /renta/.test(texto);
  };

  /** Espera unos segundos a que aparezca el 210 y ofrece llenarlo. */
  const ofrecerLlenado = async (f) => {
    for (let i = 0; i < 15; i++) {
      if (pareceFormulario210()) {
        panel.poner(
          panel.el("p", null, `Tienes tu borrador del formulario 210 (año gravable ${f.anio}): ${f.escribir} casilla${f.escribir === 1 ? "" : "s"} para escribir.`),
          panel.boton("Llenar casillas", async () => {
            panel.poner(panel.el("p", null, "Escribiendo tus casillas…"));
            const r = await enviar({ tipo: "m:llenar" });
            if (!r?.ok) panel.poner(panel.el("p", "mal", r?.error || "No pude llenar las casillas."));
          }),
          panel.el("p", "suave", "Solo escribo los valores. Revisas, firmas y presentas tú."),
        );
        return true;
      }
      await esperar(2000);
    }
    return false;
  };

  (async () => {
    const estado = await enviar({ tipo: "m:hola", principal: ES_TOP });
    if (!estado) return;
    if (estado.flujo) {
      flujo = { anio: estado.flujo.anio, aceptado: !!estado.flujo.aceptado };
      void recorrerExogena();
      return;
    }
    if (!(ES_TOP || esMarcoGrande())) return;
    // El formulario de MUISCA puede tardar en armarse: se revisa unos segundos
    if (estado.formulario) await ofrecerLlenado(estado.formulario);
    // El 210 nuevo de MUISCA es una aplicación de una sola página (Angular): el formulario aparece al
    // cambiar la ruta (#/ingreso → #/formulario) sin recargar, así que se vuelve a mirar en cada cambio
    let buscando = false;
    addEventListener("hashchange", async () => {
      if (buscando || flujo) return;
      buscando = true;
      try {
        const e = await enviar({ tipo: "m:hola", principal: ES_TOP });
        if (e?.formulario) await ofrecerLlenado(e.formulario);
      } finally {
        buscando = false;
      }
    });
  })();
})();
