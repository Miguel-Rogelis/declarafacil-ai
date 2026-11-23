/* DeclaraFácil — corre dentro de la página de la DIAN (mundo MAIN) desde que empieza a cargar.
 *
 * Solo hace algo cuando la persona pidió «Traer mi exógena» (la captura está armada): si en ese
 * momento se descarga un archivo (un Excel, un CSV, un PDF…), lo atrapa y se lo pasa a la
 * extensión en vez de dejarlo en la carpeta de Descargas. Para eso repite la misma petición que
 * iba a hacer la página, con la misma sesión. No lee ni toca contraseñas, no hace clic en nada y
 * no cambia ninguna otra cosa de la página.
 */
(() => {
  if (window.__dfCaptura) return;
  window.__dfCaptura = true;

  // MUISCA carga Prototype.js 1.6, que cambia Array.from por su $A (ignora la función de mapeo y no
  // entiende FormData) y le pone toJSON a los arreglos. Aquí no se usa ninguno de los dos: solo
  // ciclos for…of y copias con [...x], que siguen siendo nativos.
  const pares = (iterable, f) => {
    const out = [];
    for (const x of iterable) out.push(f(x));
    return out;
  };

  let armado = false;
  let dejarPasar = false;
  let ultimoClic = { texto: "", cuando: 0 };
  const blobs = new Map();

  // Textos de botones y enlaces que suelen descargar el reporte (o consultarlo y descargarlo de una vez)
  // (el enlace del menú «Consultar información exógena» no cuenta: ese solo abre el servicio)
  const DESCARGA = /descarg|export|excel|\bxlsx?\b|\bcsv\b|generar|archivo|^consultar$|^consultar reporte|^ver reporte|^ver archivo/i;
  const ARCHIVO = /spreadsheet|excel|octet-stream|vnd\.ms|officedocument|zip|csv|pdf/i;

  // Botones de imagen sin alt (MUISCA: botconsultar.gif): el texto sale del nombre del archivo
  const deImagen = (src) => {
    const base = String(src || "").split(/[?#;]/)[0].split("/").pop().replace(/\.(gif|png|jpe?g|svg|webp)$/i, "");
    return base.replace(/^(boton|bot|btn)[_-]?/i, "").replace(/(utv|_?es|_?on|_?off|_?activo|_?hover|\d+)$/i, "").replace(/[_-]+/g, " ").trim();
  };

  const texto = (el) => {
    if (!el) return "";
    const t = el.tagName === "INPUT" ? el.value || el.getAttribute("alt") || el.title : el.innerText || el.textContent || el.title;
    const img = el.querySelector?.("img[alt]")?.getAttribute("alt");
    const srcDe = (x) => {
      const src = x?.getAttribute?.("src") || "";
      const fuera = (x?.getAttribute?.("onmouseout") || "").match(/src\s*=\s*['"]([^'"]+)['"]/);
      return fuera && (/rollover|hover|over\./i.test(src) || !src) ? fuera[1] : src;
    };
    const archivo = el.tagName === "INPUT" && el.type === "image" ? deImagen(srcDe(el)) : deImagen(srcDe(el.querySelector?.("img")));
    return String(t?.trim() || img || el.getAttribute?.("aria-label") || archivo || "").replace(/\s+/g, " ").trim().slice(0, 120);
  };

  // En JSF un enlace de comando llena el campo oculto «…:_idcl» con su id justo antes de form.submit():
  // si ese id habla de descargar o de un reporte, el envío es la descarga (MUISCA: lnkDescargarReporteExogena)
  const enlaceJsf = (form) => {
    const campo = form?.querySelector?.('input[type="hidden"][name$="_idcl"], input[type="hidden"][name$=":_link_hidden_"]');
    return campo?.value || "";
  };

  document.addEventListener("df-armar", (e) => {
    try {
      armado = !!JSON.parse(e.detail || "{}").armado;
    } catch {
      armado = false;
    }
  });

  document.addEventListener(
    "click",
    (e) => {
      const el = e.target?.closest?.("a, button, input, [role=button], [role=menuitem], [onclick]") || e.target;
      ultimoClic = { texto: texto(el), cuando: Date.now() };
    },
    true,
  );

  const aBase64 = (buf) => {
    const bytes = new Uint8Array(buf);
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(s);
  };

  const nombreDe = (disposicion, porDefecto) => {
    const m = /filename\*=UTF-8''([^;]+)/i.exec(disposicion || "") || /filename="?([^";]+)"?/i.exec(disposicion || "");
    try {
      return m ? decodeURIComponent(m[1]).trim() : porDefecto;
    } catch {
      return m ? m[1].trim() : porDefecto;
    }
  };

  const entregar = (buf, nombre, mime) => {
    armado = false; // una sola vez por pedido
    document.dispatchEvent(new CustomEvent("df-archivo", { detail: JSON.stringify({ nombre, mime, base64: aBase64(buf), bytes: buf.byteLength }) }));
  };

  const pareceDescarga = (submitter, form) => {
    if (!armado) return false;
    if (submitter && DESCARGA.test(texto(submitter))) return true;
    if (/descarg|export|reporte|excel/i.test(enlaceJsf(form))) return true;
    return Date.now() - ultimoClic.cuando < 4000 && DESCARGA.test(ultimoClic.texto);
  };

  /** Repite la petición del formulario con fetch. Si la respuesta es un archivo, lo atrapa; si no, deja seguir a la página. */
  const interceptar = async (form, submitter, seguir) => {
    try {
      const datos = new FormData(form, submitter || undefined);
      const metodo = (form.getAttribute("method") || "get").toUpperCase();
      let url = new URL(form.getAttribute("action") || location.href, location.href);
      const opciones = { method: metodo, credentials: "include", redirect: "follow" };
      if (metodo === "GET") {
        for (const [k, v] of datos) if (typeof v === "string") url.searchParams.append(k, v);
      } else {
        opciones.body = form.enctype === "multipart/form-data" ? datos : new URLSearchParams(pares(datos, ([k, v]) => [k, typeof v === "string" ? v : ""]));
      }
      const r = await fetch(url.href, opciones);
      const tipo = r.headers.get("content-type") || "";
      const disp = r.headers.get("content-disposition") || "";
      if (r.ok && (/attachment/i.test(disp) || ARCHIVO.test(tipo))) {
        entregar(await r.arrayBuffer(), nombreDe(disp, "exogena.xlsx"), tipo);
        return;
      }
    } catch {
      /* si algo falla, la página sigue como si nada */
    }
    seguir();
  };

  // 1) Formularios que se envían con form.submit() (así lo hace JSF con los enlaces de comando).
  // JSF agrega campos ocultos justo antes de submit() y los quita justo después: si la respuesta no era
  // un archivo, se vuelven a poner para que la página reciba la misma petición.
  const submitOriginal = HTMLFormElement.prototype.submit;
  HTMLFormElement.prototype.submit = function () {
    if (!dejarPasar && pareceDescarga(null, this)) {
      const form = this;
      const ocultos = pares(form.querySelectorAll('input[type="hidden"][name]'), (i) => [i.name, i.value]);
      void interceptar(form, null, () => {
        const puestos = ocultos
          .filter(([k]) => !form.querySelector(`input[name="${CSS.escape(k)}"]`))
          .map(([k, v]) => {
            const i = document.createElement("input");
            i.type = "hidden";
            i.name = k;
            i.value = v;
            form.appendChild(i);
            return i;
          });
        submitOriginal.call(form);
        puestos.forEach((i) => i.remove());
      });
      return;
    }
    return submitOriginal.call(this);
  };

  // 2) Formularios que se envían con un botón (evento submit que la página no canceló)
  window.addEventListener("submit", (e) => {
    const form = e.target;
    if (dejarPasar || e.defaultPrevented || !(form instanceof HTMLFormElement) || !pareceDescarga(e.submitter, form)) return;
    e.preventDefault();
    const submitter = e.submitter;
    void interceptar(form, submitter, () => {
      dejarPasar = true;
      try {
        form.requestSubmit(submitter && submitter.form === form ? submitter : undefined);
      } finally {
        dejarPasar = false;
      }
    });
  });

  // 3) Enlaces normales a un archivo (GET)
  document.addEventListener("click", (e) => {
    const a = e.target?.closest?.("a[href]");
    if (!a || !armado || e.defaultPrevented || a.href.startsWith("javascript:") || a.href.startsWith("blob:")) return;
    const url = new URL(a.href, location.href);
    if (!/(^|\.)dian\.gov\.co$/.test(url.hostname) || !(DESCARGA.test(texto(a)) || /\.(xlsx?|csv|zip|pdf)(\?|$)|descarg|export/i.test(url.pathname))) return;
    e.preventDefault();
    fetch(url.href, { credentials: "include" })
      .then(async (r) => {
        const tipo = r.headers.get("content-type") || "";
        const disp = r.headers.get("content-disposition") || "";
        if (r.ok && (/attachment/i.test(disp) || ARCHIVO.test(tipo))) entregar(await r.arrayBuffer(), nombreDe(disp, url.pathname.split("/").pop() || "exogena.xlsx"), tipo);
        else location.href = url.href;
      })
      .catch(() => {
        location.href = url.href;
      });
  });

  // 3b) Reportes que se abren en una ventanita (MUISCA, años anteriores a 2023:
  //     window.open("/WebReportes/reportservlet?…&PR_renderer=xls")): se piden aquí con la misma sesión
  const abrirOriginal = window.open;
  window.open = function (url, ...resto) {
    try {
      const u = new URL(String(url || ""), location.href);
      const esReporte = /reportservlet|renderer=xls|\.(xlsx?|csv)(\?|$)|descarg|export/i.test(u.pathname + u.search);
      if (armado && /(^|\.)dian\.gov\.co$/.test(u.hostname) && esReporte) {
        fetch(u.href, { credentials: "include" })
          .then(async (r) => {
            const tipo = r.headers.get("content-type") || "";
            const disp = r.headers.get("content-disposition") || "";
            if (r.ok && (/attachment/i.test(disp) || ARCHIVO.test(tipo))) entregar(await r.arrayBuffer(), nombreDe(disp, "exogena.xls"), tipo);
            else abrirOriginal.call(window, u.href, ...resto);
          })
          .catch(() => abrirOriginal.call(window, u.href, ...resto));
        return null;
      }
    } catch {
      /* una URL rara: que la abra la página */
    }
    return abrirOriginal.call(window, url, ...resto);
  };

  // 4) Archivos que la página arma en el navegador (blob) y descarga con un enlace
  const crearOriginal = URL.createObjectURL;
  URL.createObjectURL = function (obj) {
    const url = crearOriginal.call(URL, obj);
    if (armado && obj instanceof Blob) blobs.set(url, obj);
    return url;
  };
  const tomarBlob = (a) => {
    const b = blobs.get(a.href);
    if (!b) return false;
    blobs.delete(a.href);
    void b.arrayBuffer().then((buf) => entregar(buf, a.download || "exogena.xlsx", b.type));
    return true;
  };
  const clicOriginal = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (armado && this.href.startsWith("blob:") && tomarBlob(this)) return;
    return clicOriginal.call(this);
  };
  document.addEventListener(
    "click",
    (e) => {
      const a = e.target?.closest?.('a[href^="blob:"]');
      if (a && armado && tomarBlob(a)) e.preventDefault();
    },
    true,
  );
})();
