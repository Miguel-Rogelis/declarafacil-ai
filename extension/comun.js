/* DeclaraFácil — utilidades que comparten los scripts de las páginas de la DIAN.
 *
 * Aquí está la parte delicada: encontrar en MUISCA el campo de cada casilla y escribir en él
 * como si fuera una persona (para que MUISCA recalcule sus totales). Nada de esto hace clic en
 * botones: escribir es lo único que hace sobre el formulario.
 */
(() => {
  if (window.DF) return;

  const norm = (t) =>
    String(t ?? "")
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();

  /** Botones y enlaces que la extensión nunca toca, por seguro. */
  const PELIGRO = /firmar|firma electronica|presentar|pagar|recibo 490|enviar declaraci|borrar|eliminar|anular|cerrar sesion|salir|radicar|corregir declaraci/;

  const visible = (el) => {
    if (!el || !el.isConnected) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  };

  /** El texto de un botón de imagen sin alt, sacado del nombre del archivo (MUISCA: botaceptarutv.gif → «aceptar»). */
  const textoDeImagen = (src) => {
    const base = String(src || "").split(/[?#;]/)[0].split("/").pop().replace(/\.(gif|png|jpe?g|svg|webp)$/i, "");
    const t = base.replace(/^(boton|bot|btn)[_-]?/i, "").replace(/(utv|_?es|_?on|_?off|_?activo|_?hover|\d+)$/i, "").replace(/[_-]+/g, " ").trim();
    return t.length >= 3 ? t : "";
  };

  /** La imagen «de verdad» de un botón: si el mouse está encima, MUISCA la cambia por botrollover.gif y la
   * original queda en onmouseout ("this.src='…/botaceptarutv.gif'"). */
  const srcDe = (el) => {
    const src = el?.getAttribute?.("src") || "";
    const fuera = (el?.getAttribute?.("onmouseout") || "").match(/src\s*=\s*['"]([^'"]+)['"]/);
    return fuera && (/rollover|hover|over\./i.test(src) || !src) ? fuera[1] : src;
  };

  /** Texto que se lee en un botón, enlace o elemento. */
  const textoDe = (el) => {
    if (!el) return "";
    const esImagen = el.tagName === "INPUT" && el.type === "image";
    const t = el.tagName === "INPUT" ? el.value || el.getAttribute("alt") || el.getAttribute("aria-label") || el.title : el.innerText || el.textContent;
    const img = el.querySelector?.("img[alt]")?.getAttribute("alt"); // botones de MUISCA: un ícono con el texto en alt
    const deArchivo = esImagen ? textoDeImagen(srcDe(el)) : textoDeImagen(srcDe(el.querySelector?.("img")));
    return (t?.trim() || img || el.getAttribute?.("aria-label") || el.title || deArchivo || "").replace(/\s+/g, " ").trim().slice(0, 160);
  };

  /** Todo el texto visible de la página. MUISCA arma algunas páginas con dos <body> y el primero queda
   * vacío, así que document.body no sirve: se lee desde <html>. */
  const textoPagina = (max = 30000) => norm((document.documentElement?.innerText || "").slice(0, max));

  /** Texto propio de un elemento, sin el de sus hijos (la cajita con el número de la casilla). */
  const textoPropio = (el) =>
    Array.from(el.childNodes)
      .filter((n) => n.nodeType === Node.TEXT_NODE)
      .map((n) => n.textContent)
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();

  /** Para el diagnóstico: sin correos ni números largos (cédulas, cuentas, montos). */
  const enmascarar = (t) =>
    String(t ?? "")
      .replace(/[\w.+-]+@[\w-]+(\.[\w-]+)+/g, "[correo]")
      .replace(/\d[\d.,\s]{3,}\d/g, (m) => (m.replace(/\D/g, "").length >= 5 ? "#" : m))
      .slice(0, 120);

  const CAMPOS = 'input:not([type]), input[type="text"], input[type="number"], input[type="tel"], input[type="search"], textarea, select';

  const esCampo = (el) => el && el.matches && el.matches(CAMPOS) && el.type !== "hidden" && el.type !== "password";

  const bloqueado = (el) => el.disabled || el.readOnly || el.getAttribute("aria-readonly") === "true" || el.getAttribute("aria-disabled") === "true";

  /** Un id de JSF generado (j_idt45) cambia entre versiones: no sirve para recordar el campo. */
  const idEstable = (id) => !!id && !/(^|:)j_?id(t)?\d+/i.test(id) && !/^\d/.test(id);

  /** Ruta CSS corta del elemento, por si no tiene id ni name estables. */
  const rutaCss = (el) => {
    const partes = [];
    let x = el;
    while (x && x.nodeType === 1 && partes.length < 8) {
      if (x.id && idEstable(x.id)) {
        partes.unshift(`#${CSS.escape(x.id)}`);
        break;
      }
      const padre = x.parentElement;
      if (!padre) break;
      const hermanos = Array.from(padre.children).filter((h) => h.tagName === x.tagName);
      partes.unshift(hermanos.length > 1 ? `${x.tagName.toLowerCase()}:nth-of-type(${hermanos.indexOf(x) + 1})` : x.tagName.toLowerCase());
      x = padre;
    }
    return partes.join(" > ");
  };

  const selectorDe = (el) => ({ id: el.id || null, name: el.getAttribute("name") || null, css: rutaCss(el) });

  const porSelector = (s) => {
    if (!s) return null;
    const candidatos = [];
    if (s.id) candidatos.push(document.getElementById(s.id));
    if (s.name) candidatos.push(...document.getElementsByName(s.name));
    if (s.css) {
      try {
        candidatos.push(document.querySelector(s.css));
      } catch {
        /* selector viejo que ya no es válido */
      }
    }
    return candidatos.find((el) => esCampo(el)) || null;
  };

  // ---------- Buscar el campo de una casilla ----------

  /** El número de casilla que se lee en el id, name o título de un campo ("frmFormulario:cas32", "casilla_32"). */
  const numeroEnAtributos = (el) => {
    for (const v of [el.dataset?.casilla, el.dataset?.renglon]) if (v && /^\d{1,3}$/.test(v)) return Number(v);
    for (const attr of ["id", "name"]) {
      const v = el.getAttribute(attr);
      if (!v) continue;
      const cola = v.split(/[:]/).pop();
      // El 210 de MUISCA (aplicación en Angular) nombra cada campo cs_id_<casilla>: id="cs_id_32"
      const m = cola.match(/^(?:cs[_\-.]?id|cas(?:illa)?|reng(?:lon)?|ren|campo|txt|valor|val|c|r|f)[_\-.]?0*(\d{1,3})(?:[_\-.]?(?:valor|val|txt|input|campo))?$/i);
      if (m) return Number(m[1]);
    }
    for (const attr of ["title", "aria-label", "placeholder"]) {
      const v = norm(el.getAttribute(attr));
      const m = v.match(/^(?:casilla|renglon)\s*0*(\d{1,3})\b/) || v.match(/^(\d{1,3})\s*[.\-–:)]\s*\D/);
      if (m) return Number(m[1]);
    }
    return null;
  };

  const NUMERO_SOLO = /^\(?0*(\d{1,3})\)?\.?$/;

  /** Elementos de texto cuyo contenido propio es solo un número (las cajitas con el número de casilla). */
  const etiquetasNumero = (n) => {
    const salida = [];
    for (const el of document.querySelectorAll("td, th, span, div, label, b, strong, font, p, li, dt")) {
      const t = textoPropio(el);
      if (!t || t.length > 6) continue;
      const m = t.match(NUMERO_SOLO);
      if (m && Number(m[1]) === n) salida.push(el);
    }
    return salida;
  };

  const esNumeroEtiqueta = (el) => {
    const t = textoPropio(el);
    const m = t && t.length <= 6 ? t.match(NUMERO_SOLO) : null;
    return !!m && Number(m[1]) >= 1; // un "0" es un valor en pantalla, no el número de otra casilla
  };

  /** Después de la etiqueta, el primer campo antes de que aparezca otro número de casilla. */
  const campoTras = (etiqueta) => {
    const label = etiqueta.closest("label[for]");
    if (label) {
      const el = document.getElementById(label.getAttribute("for"));
      if (esCampo(el)) return el;
    }
    let contenedor = etiqueta.closest("tr") || etiqueta.parentElement;
    for (let nivel = 0; contenedor && nivel < 4; nivel++) {
      const recorrido = document.createTreeWalker(contenedor, NodeFilter.SHOW_ELEMENT);
      let visto = false;
      for (let x = recorrido.currentNode; x; x = recorrido.nextNode()) {
        if (x === etiqueta) {
          visto = true;
          continue;
        }
        if (!visto) continue;
        if (esCampo(x)) return x;
        if (x !== etiqueta && esNumeroEtiqueta(x)) break; // empezó la casilla siguiente
      }
      contenedor = contenedor.parentElement;
    }
    return null;
  };

  /** Busca el campo de la casilla n: primero lo aprendido, luego atributos, luego la etiqueta con el número. */
  const buscarCampo = (n, mapa, usados) => {
    const libre = (el) => el && !usados.has(el);
    const aprendido = porSelector(mapa?.[n]);
    if (libre(aprendido)) return { el: aprendido, como: "aprendido" };

    const campos = Array.from(document.querySelectorAll(CAMPOS)).filter(esCampo);
    const porAtributo = campos.filter((el) => numeroEnAtributos(el) === n && libre(el));
    if (porAtributo.length) return { el: porAtributo.find(visible) || porAtributo[0], como: "atributo" };

    for (const etiqueta of etiquetasNumero(n)) {
      const el = campoTras(etiqueta);
      if (libre(el)) return { el, como: "etiqueta" };
    }
    return null;
  };

  // ---------- Escribir como una persona ----------

  const ponerValor = (el, valor) => {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, valor);
  };

  /** Escribe el valor y dispara los eventos que MUISCA escucha para recalcular. */
  const escribir = (el, valor) => {
    if (el.tagName === "SELECT") {
      const objetivo = norm(valor);
      const opcion = Array.from(el.options).find((o) => norm(o.value) === objetivo || norm(o.text) === objetivo || norm(o.text).startsWith(objetivo));
      if (!opcion) return false;
      el.value = opcion.value;
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    }
    el.focus();
    el.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    ponerValor(el, "");
    ponerValor(el, String(valor));
    el.dispatchEvent(new InputEvent("input", { bubbles: true, data: String(valor), inputType: "insertText" }));
    el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: "0" }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.blur();
    return true;
  };

  /** Lo que muestra el campo, solo los dígitos ("1.234.000" → 1234000). */
  const leerNumero = (el) => {
    const v = el.tagName === "SELECT" ? el.options[el.selectedIndex]?.text : el.value;
    const d = String(v ?? "").replace(/[^\d-]/g, "");
    return d === "" || d === "-" ? null : Number(d);
  };

  const resaltar = (el, color) => {
    el.style.outline = `3px solid ${color}`;
    el.style.outlineOffset = "1px";
  };

  /** El año gravable que dice la página, si lo dice. */
  const anioDeLaPagina = () => {
    const texto = textoPagina(20000);
    const m = texto.match(/ano gravable\D{0,15}(20\d{2})/);
    if (m) return Number(m[1]);
    for (const s of document.querySelectorAll("select")) {
      const cerca = norm(s.closest("tr, div, td")?.innerText);
      if (/ano/.test(cerca)) {
        const m2 = norm(s.options[s.selectedIndex]?.text).match(/20\d{2}/);
        if (m2) return Number(m2[0]);
      }
    }
    return null;
  };

  window.DF = { norm, PELIGRO, visible, textoDe, textoDeImagen, textoPagina, textoPropio, enmascarar, CAMPOS, esCampo, bloqueado, selectorDe, porSelector, numeroEnAtributos, buscarCampo, escribir, leerNumero, resaltar, anioDeLaPagina, idEstable };
})();
