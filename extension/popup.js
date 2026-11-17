/* DeclaraFácil — ventanita de la extensión. */
const $ = (id) => document.getElementById(id);
const pedir = (m) => chrome.runtime.sendMessage(m).catch((e) => ({ ok: false, error: String(e?.message || e) }));
const pesos = (n) => "$" + Math.round(n).toLocaleString("es-CO");

function mostrar(id, texto, clase = "") {
  const el = $(id);
  el.textContent = texto;
  el.className = `resultado ${clase}`.trim();
  el.hidden = !texto;
}

function hace(ms) {
  const min = Math.round((Date.now() - ms) / 60000);
  return min < 1 ? "hace un momento" : min === 1 ? "hace 1 minuto" : min < 60 ? `hace ${min} minutos` : `hace ${Math.round(min / 60)} h`;
}

function textoResumen(r) {
  const partes = [`Escribí ${r.llenadas.length} casilla${r.llenadas.length === 1 ? "" : "s"}.`];
  if (r.avisoAnio) partes.push(r.avisoAnio);
  if (r.noQuedaron.length) partes.push(`No quedaron bien: ${r.noQuedaron.join(", ")}.`);
  if (r.noEncontradas.length) partes.push(`No encontré: ${r.noEncontradas.join(", ")}.`);
  const distintas = r.calculadas.filter((c) => c.muisca !== c.borrador);
  if (distintas.length) partes.push("MUISCA calculó distinto: " + distintas.map((c) => `${c.n} (${pesos(c.muisca)} vs. ${pesos(c.borrador)})`).join("; ") + ".");
  else if (r.calculadas.length) partes.push(`Los ${r.calculadas.length} totales de MUISCA cuadran con tu borrador.`);
  return partes.join(" ");
}

async function refrescar() {
  const e = await pedir({ tipo: "p:estado" });
  $("version").textContent = "v" + chrome.runtime.getManifest().version;
  const sel = $("anio");
  if (!sel.options.length) {
    const actual = new Date().getFullYear();
    for (let a = actual - 1; a >= actual - 5; a--) sel.add(new Option(String(a), String(a)));
    sel.value = String(e?.borrador?.anio || actual - 1);
  }
  if (!e || e.ok === false) {
    $("borrador").textContent = "No pude leer el estado de la extensión.";
    return;
  }
  const b = e.borrador;
  $("borrador").textContent = b
    ? `Borrador del año gravable ${b.anio}: ${b.escribir} casilla${b.escribir === 1 ? "" : "s"} para escribir (recibido ${hace(b.recibido)}).`
    : "Aún no hay borrador. En DeclaraFácil, en «Presentar en la DIAN», toca «Llenar con la extensión».";
  $("llenar").disabled = !b || !e.enDian;
  $("llenar").title = !e.enDian ? "Abre el formulario 210 en MUISCA" : "";
  if (e.ultimo) mostrar("resultado", textoResumen(e.ultimo), e.ultimo.noEncontradas.length || e.ultimo.noQuedaron.length ? "" : "ok");
  $("ensenar").hidden = !(e.enDian && b && e.ultimo && (e.ultimo.noEncontradas.length || e.ultimo.noQuedaron.length));
  $("copia").checked = !!e.opciones.copia;

  if (e.flujo?.activo) mostrar("estado-exogena", `Buscando tu exógena de ${e.flujo.anio} en la pestaña de MUISCA…`);
  else if (e.pendiente) mostrar("estado-exogena", "Tengo tu exógena: abre DeclaraFácil y te la paso.", "ok");
  $("mapa").disabled = !e.aprendidas;
}

$("llenar").addEventListener("click", async () => {
  $("llenar").disabled = true;
  mostrar("resultado", "Escribiendo tus casillas…");
  const r = await pedir({ tipo: "p:llenar" });
  if (r?.ok) mostrar("resultado", textoResumen(r.resumen), r.resumen.noEncontradas.length ? "" : "ok");
  else mostrar("resultado", r?.error || "No pude llenar las casillas.", "mal");
  await refrescar();
});

$("ensenar").addEventListener("click", async () => {
  const r = await pedir({ tipo: "p:ensenar" });
  if (r?.ok) window.close(); // el panel de la página sigue con la lista
  else mostrar("resultado", r?.error || "No pude abrir la lista.", "mal");
});

$("exogena").addEventListener("click", async () => {
  const r = await pedir({ tipo: "p:exogena", anio: Number($("anio").value) });
  if (r?.ok) mostrar("estado-exogena", r.nueva ? "Abrí MUISCA. Inicia sesión y yo sigo con la consulta." : "Sigo en tu pestaña de MUISCA.", "ok");
  else mostrar("estado-exogena", r?.error || "No pude empezar.", "mal");
});

$("copia").addEventListener("change", (e) => void pedir({ tipo: "p:opciones", copia: e.target.checked }));

async function copiar(texto, nombre) {
  try {
    await navigator.clipboard.writeText(texto);
    mostrar("estado-herramientas", "Copiado. Pégalo en un mensaje al equipo de DeclaraFácil.", "ok");
  } catch {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([texto], { type: "application/json" }));
    a.download = nombre;
    a.click();
    mostrar("estado-herramientas", "Lo descargué como archivo.", "ok");
  }
}

$("diagnostico").addEventListener("click", async () => {
  const r = await pedir({ tipo: "p:diagnostico" });
  if (r?.ok) await copiar(JSON.stringify(r.diagnostico, null, 2), "diagnostico-muisca.json");
  else mostrar("estado-herramientas", r?.error || "No pude armar el diagnóstico.", "mal");
});

$("mapa").addEventListener("click", async () => {
  const r = await pedir({ tipo: "p:exportar-mapa" });
  if (r?.ok) await copiar(JSON.stringify({ formulario: "210", casillas: r.mapa }, null, 2), "casillas-muisca-210.json");
});

$("borrar").addEventListener("click", async () => {
  await pedir({ tipo: "p:borrar" });
  mostrar("resultado", "");
  mostrar("estado-exogena", "");
  await refrescar();
});

$("olvidar").addEventListener("click", async () => {
  await pedir({ tipo: "p:olvidar" });
  mostrar("estado-herramientas", "Listo, olvidé las casillas aprendidas.", "ok");
  await refrescar();
});

void refrescar();
