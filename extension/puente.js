/* DeclaraFácil — puente entre la página de DeclaraFácil y la extensión.
 *
 * Solo corre en las direcciones de DeclaraFácil. La página le habla con window.postMessage
 * (origen "declarafacil-app") y el puente responde con origen "declarafacil-extension".
 * Mensajes de la página: hola, formulario (el borrador del 210), pedir-exogena (año).
 * Mensajes hacia la página: lista (la extensión está instalada), respuesta, exogena (el archivo).
 */
(() => {
  if (window.__dfPuente) return;
  window.__dfPuente = true;
  const VERSION = chrome.runtime.getManifest().version;
  const decir = (m) => window.postMessage({ origen: "declarafacil-extension", ...m }, location.origin);
  const anunciar = () => decir({ tipo: "lista", version: VERSION });

  document.documentElement.dataset.declarafacilExtension = VERSION;

  // La página confirma que recibió el archivo; si no confirma, la extensión lo guarda para el próximo «hola»
  let alRecibir = null;
  const pasarArchivo = (a) =>
    new Promise((listo) => {
      if (!a?.base64) return listo(false);
      const espera = setTimeout(() => {
        alRecibir = null;
        listo(false);
      }, 3000);
      alRecibir = () => {
        clearTimeout(espera);
        alRecibir = null;
        listo(true);
      };
      decir({ tipo: "exogena", nombre: a.nombre, mime: a.mime, base64: a.base64 });
    });

  window.addEventListener("message", async (e) => {
    if (e.source !== window || e.origin !== location.origin) return;
    const m = e.data;
    if (!m || m.origen !== "declarafacil-app" || typeof m.tipo !== "string") return;
    const responder = (r) => decir({ tipo: "respuesta", id: m.id, ...(r || { ok: false, error: "La extensión no respondió." }) });
    if (m.tipo === "exogena-recibida") {
      alRecibir?.();
      return;
    }
    try {
      if (m.tipo === "hola") {
        anunciar();
        const r = await chrome.runtime.sendMessage({ tipo: "df:hola" });
        const { archivo, ...resto } = r || {};
        responder(resto);
        void pasarArchivo(archivo); // una exógena que llegó cuando DeclaraFácil estaba cerrado
      } else if (m.tipo === "formulario") {
        responder(await chrome.runtime.sendMessage({ tipo: "df:formulario", datos: m.datos }));
      } else if (m.tipo === "pedir-exogena") {
        responder(await chrome.runtime.sendMessage({ tipo: "df:pedir-exogena", anio: m.anio }));
      }
    } catch (err) {
      responder({ ok: false, error: "La extensión no está disponible. Recarga la página." });
    }
  });

  chrome.runtime.onMessage.addListener((m, _s, responder) => {
    if (m?.tipo === "app:exogena") {
      void pasarArchivo(m).then((ok) => responder({ ok }));
      return true; // la respuesta llega cuando la página confirma
    } else if (m?.tipo === "app:exogena-en-descargas") {
      decir({ tipo: "exogena-en-descargas" });
      responder({ ok: true });
    }
  });

  anunciar();
})();
