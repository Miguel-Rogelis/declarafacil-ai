import { useEffect, useState } from "react";
import { api, type AgenteConfig, type Kpi, type ResumenMetricas, type VersionHistorial } from "../lib/api";
import { FadeIn } from "../components/Movimiento";
import { Pestanas } from "../components/piezas";
import { useSesion } from "../lib/estado";

type Reglas = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const CAMPOS_REGLAS: { ruta: string; etiqueta: string; tipo: "pesos" | "uvt" | "pct" }[] = [
  { ruta: "uvt", etiqueta: "UVT del año gravable", tipo: "pesos" },
  { ruta: "uvt_anio_presentacion", etiqueta: "UVT del año en que se declara (sanciones)", tipo: "pesos" },
  { ruta: "topes_obligacion_uvt.patrimonio_bruto", etiqueta: "Tope de patrimonio bruto", tipo: "uvt" },
  { ruta: "topes_obligacion_uvt.ingresos_brutos", etiqueta: "Tope de ingresos brutos", tipo: "uvt" },
  { ruta: "topes_obligacion_uvt.consumos_tarjeta_credito", etiqueta: "Tope de consumos con tarjeta", tipo: "uvt" },
  { ruta: "cedula_general.limite_rentas_exentas_deducciones_pct", etiqueta: "Límite de exentas y deducciones", tipo: "pct" },
  { ruta: "cedula_general.limite_rentas_exentas_deducciones_uvt", etiqueta: "Límite de exentas y deducciones", tipo: "uvt" },
  { ruta: "cedula_general.renta_exenta_laboral_pct", etiqueta: "Renta exenta laboral", tipo: "pct" },
  { ruta: "cedula_general.renta_exenta_laboral_tope_uvt", etiqueta: "Tope renta exenta laboral", tipo: "uvt" },
  { ruta: "cedula_general.dependiente_adicional_uvt", etiqueta: "Deducción adicional por dependiente", tipo: "uvt" },
  { ruta: "cedula_general.medicina_prepagada_tope_uvt", etiqueta: "Tope medicina prepagada (anual)", tipo: "uvt" },
  { ruta: "cedula_general.intereses_vivienda_tope_uvt", etiqueta: "Tope intereses de vivienda", tipo: "uvt" },
  { ruta: "cedula_general.factura_electronica_pct", etiqueta: "Deducción por factura electrónica", tipo: "pct" },
  { ruta: "cedula_general.componente_inflacionario_rendimientos_pct", etiqueta: "Componente inflacionario de rendimientos", tipo: "pct" },
  { ruta: "cedula_pensiones.renta_exenta_mensual_uvt", etiqueta: "Pensión exenta mensual", tipo: "uvt" },
  { ruta: "dividendos.tarifa_subcedula_gravada", etiqueta: "Tarifa dividendos gravados", tipo: "pct" },
  { ruta: "ganancias_ocasionales.tarifa_general", etiqueta: "Tarifa ganancias ocasionales", tipo: "pct" },
  { ruta: "ganancias_ocasionales.tarifa_loterias", etiqueta: "Tarifa loterías y premios", tipo: "pct" },
  { ruta: "sanciones.extemporaneidad_pct_mes_impuesto", etiqueta: "Sanción por mes de retraso", tipo: "pct" },
  { ruta: "sanciones.sancion_minima_uvt", etiqueta: "Sanción mínima", tipo: "uvt" },
];

const leer = (o: Reglas, ruta: string) => ruta.split(".").reduce((a, k) => (a == null ? a : a[k]), o);
const escribir = (o: Reglas, ruta: string, v: unknown): Reglas => {
  const copia = structuredClone(o);
  const partes = ruta.split(".");
  let cur = copia;
  for (const p of partes.slice(0, -1)) cur = cur[p];
  cur[partes.at(-1)!] = v;
  return copia;
};

function useToken() {
  const [token, setToken] = useState(() => sessionStorage.getItem("df-admin") ?? "");
  useEffect(() => {
    try {
      sessionStorage.setItem("df-admin", token);
    } catch {
      /* almacenamiento no disponible */
    }
  }, [token]);
  return [token, setToken] as const;
}

let almacenServidor: Promise<string | undefined> | null = null;
/** Dónde guarda el servidor lo que se edita aquí: «supabase» o «archivo» sobreviven a un reinicio; «memoria», no. */
function useAlmacen() {
  const [almacen, setAlmacen] = useState<string | undefined>();
  useEffect(() => {
    almacenServidor ??= api.estado().then((e) => e.almacen).catch(() => undefined);
    void almacenServidor.then(setAlmacen);
  }, []);
  return { almacen, persiste: almacen === "supabase" || almacen === "archivo" };
}

/** Versiones guardadas (quién cambió qué y cuándo) con botón para volver a una o al archivo del repositorio. */
function Historial({ cargar, revertir, cambio }: {
  cargar: () => Promise<VersionHistorial[]>;
  revertir: (version: number | null) => Promise<unknown>;
  cambio: number;
}) {
  const [versiones, setVersiones] = useState<VersionHistorial[] | null>(null);
  const [msg, setMsg] = useState<{ texto: string; error?: boolean } | null>(null);
  const { persiste } = useAlmacen();
  const recargar = () => cargar().then(setVersiones).catch((e) => setMsg({ texto: (e as Error).message, error: true }));
  useEffect(() => {
    void recargar();
  }, [cambio]); // eslint-disable-line react-hooks/exhaustive-deps
  const volver = async (v: number | null) => {
    try {
      await revertir(v);
      setMsg({ texto: v === null ? "Restauré los valores del repositorio." : `Volví a la versión ${v}.` });
      void recargar();
    } catch (e) {
      setMsg({ texto: (e as Error).message, error: true });
    }
  };
  return (
    <section className="mt-3">
      <h3 className="titular t-21">Historial de cambios</h3>
      <p className="chico suave">
        {persiste
          ? "Cada cambio queda guardado con su autor y sobrevive a los reinicios del servidor."
          : "Cada cambio queda con su autor, pero este servidor guarda en memoria: se pierde al reiniciar (configura SUPABASE_SERVICE_ROLE_KEY o ALMACEN_DIR)."}
      </p>
      {versiones?.length ? (
        <ul className="lista-historial chico">
          {versiones.map((v) => (
            <li key={v.id}>
              <span>Versión {v.id} · {new Date(v.creada).toLocaleString("es-CO")} · {v.autor ?? "sin autor"}</span>
              <button className="boton-texto chico" onClick={() => void volver(v.id)}>Volver a esta</button>
            </li>
          ))}
        </ul>
      ) : versiones ? <p className="chico suave">Sin cambios guardados: se usan los valores del repositorio.</p> : null}
      <button className="boton secundario chico mt-1" onClick={() => void volver(null)}>Restaurar los valores del repositorio</button>
      {msg ? <p className={`mensaje-estado${msg.error ? " error" : ""}`} role="status">{msg.texto}</p> : null}
    </section>
  );
}

function PanelReglas({ token }: { token: string }) {
  const { anios } = useSesion();
  const [anio, setAnio] = useState(2025);
  const [reglas, setReglas] = useState<Reglas | null>(null);
  const [msg, setMsg] = useState<{ texto: string; error?: boolean } | null>(null);
  const [destino, setDestino] = useState("");
  const { persiste } = useAlmacen();
  const [uvtNueva, setUvtNueva] = useState("");

  const [errorCarga, setErrorCarga] = useState("");
  const [cambio, setCambio] = useState(0);

  useEffect(() => {
    setReglas(null);
    setErrorCarga("");
    api.reglas(anio).then(setReglas).catch((e) => setErrorCarga(`No pude cargar las reglas de ${anio}. ${e.message}`));
  }, [anio]);

  const guardar = async () => {
    if (!reglas) return;
    try {
      setReglas(await api.guardarReglas(anio, reglas, token));
      setMsg({ texto: `Reglas del año ${anio} guardadas.` });
      setCambio((c) => c + 1);
    } catch (e) {
      setMsg({ texto: (e as Error).message, error: true });
    }
  };
  const clonar = async () => {
    try {
      await api.clonarReglas(anio, Number(destino), uvtNueva ? Number(uvtNueva) : null, token);
      setMsg({ texto: `Creado el borrador del año ${destino}. Recarga la página para verlo en el selector.` });
    } catch (e) {
      setMsg({ texto: (e as Error).message, error: true });
    }
  };

  return (
    <div>
      <div className="campo campo-angosto">
        <label htmlFor="anio-reglas">Año gravable</label>
        <select id="anio-reglas" className="entrada" value={anio} onChange={(e) => setAnio(Number(e.target.value))}>
          {anios.map((a) => <option key={a.anio_gravable} value={a.anio_gravable}>{a.anio_gravable} ({a.estado})</option>)}
        </select>
      </div>
      {reglas ? (
        <>
          <p className="suave">{reglas.descripcion}</p>
          <div className="rejilla-reglas">
            {CAMPOS_REGLAS.map((c) => {
              const v = leer(reglas, c.ruta) as unknown as number | null;
              const mostrado = v == null ? "" : c.tipo === "pct" ? +(v * 100).toFixed(4) : v;
              return (
                <div className="campo" key={c.ruta}>
                  <label htmlFor={c.ruta}>{c.etiqueta} {c.tipo === "pct" ? "(%)" : c.tipo === "uvt" ? "(UVT)" : "($)"}</label>
                  <input
                    id={c.ruta}
                    className="entrada"
                    type="number"
                    step="any"
                    value={mostrado}
                    onChange={(e) => {
                      const n = e.target.value === "" ? null : Number(e.target.value);
                      setReglas(escribir(reglas, c.ruta, n == null ? null : c.tipo === "pct" ? n / 100 : n));
                    }}
                  />
                </div>
              );
            })}
          </div>

          <h3 className="titular t-21 mt-3">Tabla del artículo 241</h3>
          <div className="tabla-scroll mt-1">
          <table className="tabla tabla-241">
            <thead><tr><th>Desde (UVT)</th><th>Hasta (UVT)</th><th>Tarifa (%)</th><th>Impuesto fijo (UVT)</th></tr></thead>
            <tbody>
              {(reglas.tabla_renta_art241 as Reglas[]).map((t, i) => (
                <tr key={i}>
                  <td>{t.desde_uvt}</td>
                  <td>{t.hasta_uvt ?? "En adelante"}</td>
                  <td><input type="number" step="any" aria-label={`Tarifa tramo ${i + 1}`} value={+(t.tarifa * 100).toFixed(2)} onChange={(e) => setReglas(escribir(reglas, `tabla_renta_art241.${i}.tarifa`, Number(e.target.value) / 100))} /></td>
                  <td><input type="number" step="any" aria-label={`Impuesto fijo tramo ${i + 1}`} value={t.impuesto_fijo_uvt} onChange={(e) => setReglas(escribir(reglas, `tabla_renta_art241.${i}.impuesto_fijo_uvt`, Number(e.target.value)))} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <p className="chico suave">
            {persiste
              ? "Los cambios guardados aquí quedan en el almacén del servidor con su historial. Para llevarlos al repositorio, descarga el JSON y reemplaza "
              : "Este servidor guarda en memoria: los cambios duran hasta que se reinicie. Para dejarlos fijos, descarga el JSON y reemplaza "}
            backend/data/reglas/ag{anio}.json.
          </p>
          <p className="chico suave">
            Calendario de vencimientos: {Object.keys(reglas.vencimientos ?? {}).length ? `${Object.keys(reglas.vencimientos).length} fechas cargadas` : "sin cargar"}. Fuentes: {(reglas.fuentes ?? []).join("; ")}.
          </p>
          <div className="acciones-resultado">
            <button className="boton" onClick={guardar}>Guardar reglas de {anio}</button>
            <button
              className="boton secundario"
              onClick={() => {
                const url = URL.createObjectURL(new Blob([JSON.stringify(reglas, null, 2)], { type: "application/json" }));
                const a = document.createElement("a");
                a.href = url;
                a.download = `ag${anio}.json`;
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              Descargar JSON
            </button>
          </div>

          <h3 className="titular t-21 mt-3">Preparar un año nuevo</h3>
          <p className="suave">Copia las reglas de {anio} como borrador para otro año y ajusta lo que cambie.</p>
          <div className="fila-campos">
            <div className="campo"><label htmlFor="destino">Año nuevo</label><input id="destino" className="entrada" type="number" value={destino} onChange={(e) => setDestino(e.target.value)} placeholder={String(anio + 1)} /></div>
            <div className="campo"><label htmlFor="uvtn">UVT de ese año</label><input id="uvtn" className="entrada" type="number" value={uvtNueva} onChange={(e) => setUvtNueva(e.target.value)} /></div>
            <button className="boton secundario" onClick={clonar} disabled={!destino}>Crear borrador</button>
          </div>
        </>
      ) : errorCarga ? (
        <p className="mensaje-estado error" role="alert">{errorCarga}</p>
      ) : <p className="suave" role="status">Cargando reglas…</p>}
      {msg ? <p className={`mensaje-estado${msg.error ? " error" : ""}`} role="status">{msg.texto}</p> : null}
      {token ? (
        <Historial
          cambio={cambio + anio}
          cargar={() => api.historialReglas(anio, token)}
          revertir={async (v) => setReglas(await api.revertirReglas(anio, v, token))}
        />
      ) : null}
    </div>
  );
}

function TarjetaAgente({ id, cfg, token }: { id: string; cfg: AgenteConfig; token: string }) {
  const [modelos, setModelos] = useState((cfg.modelos ?? []).join("\n"));
  const [temp, setTemp] = useState(cfg.temperatura ?? 0);
  const [activo, setActivo] = useState(cfg.activo);
  const [msg, setMsg] = useState<{ texto: string; error?: boolean } | null>(null);

  const guardar = async () => {
    try {
      const cambios: Partial<AgenteConfig> = cfg.usa_ia ? { modelos: modelos.split("\n").map((m) => m.trim()).filter(Boolean), temperatura: temp, activo } : { activo };
      await api.guardarAgente(id, cambios, token);
      setMsg({ texto: "Guardado." });
    } catch (e) {
      setMsg({ texto: (e as Error).message, error: true });
    }
  };
  const probar = async () => {
    setMsg({ texto: "Probando…" });
    const r = await api.probarAgente(id).catch((e) => ({ ok: false, detalle: (e as Error).message }) as { ok: boolean; detalle?: string; modelo?: string });
    setMsg(r.ok ? { texto: `Respondió ${r.modelo}.` } : { texto: r.detalle ?? "No respondió.", error: true });
  };

  return (
    <article className="tarjeta-agente">
      <header>
        <strong className="t-21">{cfg.nombre}</strong>
        {cfg.usa_ia ? <span className="etiqueta-ia">IA</span> : <span className="etiqueta-reglas">Reglas</span>}
      </header>
      <p className="suave sin-margen mt-1">{cfg.responsabilidad}</p>
      {cfg.usa_ia ? (
        <div className="rejilla-agente">
          <div className="campo">
            <label htmlFor={`m-${id}`}>Modelos de OpenRouter, en orden de preferencia</label>
            <textarea id={`m-${id}`} className="entrada" rows={3} value={modelos} onChange={(e) => setModelos(e.target.value)} />
            <span className="ayuda">Si el primero falla o llega al límite, pasa al siguiente. openrouter/free elige uno gratis disponible.</span>
          </div>
          <div className="campo">
            <label htmlFor={`t-${id}`}>Temperatura</label>
            <input id={`t-${id}`} className="entrada" type="number" min={0} max={1.5} step={0.1} value={temp} onChange={(e) => setTemp(Number(e.target.value))} />
          </div>
        </div>
      ) : null}
      {cfg.usa_ia ? (
        <>
          <label className="casilla">
            <input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} />
            <span>Usar IA en este agente (si lo apagas, usa su ruta sin modelo)</span>
          </label>
          <div className="opciones">
            <button className="boton chico" onClick={guardar}>Guardar</button>
            <button className="boton secundario chico" onClick={probar}>Probar conexión</button>
          </div>
        </>
      ) : null}
      {msg ? <p className={`mensaje-estado${msg.error ? " error" : ""}`} role="status">{msg.texto}</p> : null}
    </article>
  );
}

function PanelAgentes({ token }: { token: string }) {
  const [agentes, setAgentes] = useState<Record<string, AgenteConfig> | null>(null);
  const [gratis, setGratis] = useState<{ id: string; nombre: string; contexto: number }[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.agentes().then(setAgentes).catch((e) => setError(e.message));
  }, []);
  const verGratis = () => {
    setError("");
    api.modelosGratis().then(setGratis).catch((e) => setError(e.message));
  };
  return (
    <div className="panel-agentes">
      <div>{agentes ? Object.entries(agentes).map(([id, cfg]) => <TarjetaAgente key={id} id={id} cfg={cfg} token={token} />) : (error ? null : <p className="suave" role="status">Cargando agentes…</p>)}</div>
      <aside>
        <h3 className="titular t-21">Modelos gratis de hoy</h3>
        <p className="chico suave">OpenRouter cambia su lista de modelos gratuitos casi cada semana. Consulta la lista actual y copia los identificadores que quieras usar.</p>
        <button className="boton secundario chico" onClick={verGratis}>Consultar OpenRouter</button>
        {error ? <p className="mensaje-estado error" role="alert">{error}</p> : null}
        {gratis ? (
          <ul className="chico lista-modelos">
            {gratis.map((m) => <li key={m.id}><code>{m.id}</code></li>)}
          </ul>
        ) : null}
        {token ? <Historial cambio={0} cargar={() => api.historialAgentes(token)} revertir={async (v) => setAgentes(await api.revertirAgentes(v, token))} /> : null}
      </aside>
    </div>
  );
}

const FORMATO_KPI = (k: Kpi) => {
  if (k.valor === null) return "—";
  const n = k.unidad === "USD" ? k.valor.toLocaleString("es-CO", { maximumFractionDigits: 3 }) : k.valor.toLocaleString("es-CO", { maximumFractionDigits: 1 });
  return `${k.unidad === "USD" ? "USD " : ""}${n}${k.unidad === "%" ? " %" : k.unidad === "USD" ? "" : ` ${k.unidad}`}`;
};
const ESTADO_KPI: Record<Kpi["estado"], string> = { cumple: "Cumple", no_cumple: "No cumple", sin_datos: "Sin datos", muestra_pequena: "Muestra pequeña" };

/** KPI con su meta y su criterio de aceptación (HU-41). Ningún evento lleva datos personales. */
function PanelMetricas({ token }: { token: string }) {
  const [dias, setDias] = useState(30);
  const [datos, setDatos] = useState<ResumenMetricas | null>(null);
  const [error, setError] = useState("");
  const [manual, setManual] = useState({ kpi: "KPI-14", valor: "", n: "", nota: "" });
  const [servidor, setServidor] = useState<{ perfil?: string; almacen?: string }>({});
  useEffect(() => {
    api.estado().then((e) => setServidor({ perfil: e.perfil_modelos, almacen: e.almacen })).catch(() => {});
  }, []);
  const cargar = () => {
    setError("");
    api.metricas(dias, token).then(setDatos).catch((e) => setError((e as Error).message));
  };
  useEffect(() => {
    if (token) cargar();
  }, [dias, token]); // eslint-disable-line react-hooks/exhaustive-deps
  const guardarManual = async () => {
    try {
      await api.guardarKpiManual(manual.kpi, Number(manual.valor), Number(manual.n), manual.nota, token);
      setManual({ ...manual, valor: "", n: "", nota: "" });
      cargar();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  if (!token) return <p className="suave">Escribe la clave de administrador para ver las métricas.</p>;
  return (
    <div>
      <div className="fila-campos">
        <div className="campo">
          <label htmlFor="dias">Periodo</label>
          <select id="dias" className="entrada" value={dias} onChange={(e) => setDias(Number(e.target.value))}>
            {[1, 7, 30, 90, 365].map((d) => <option key={d} value={d}>Últimos {d} {d === 1 ? "día" : "días"}</option>)}
          </select>
        </div>
        <button className="boton secundario chico" onClick={cargar}>Actualizar</button>
        <button className="boton secundario chico" onClick={() => api.descargarMetricas(dias, token).catch((e) => setError((e as Error).message))}>Descargar CSV</button>
      </div>
      {error ? <p className="mensaje-estado error" role="alert">{error}</p> : null}
      {datos ? (
        <>
          {servidor.perfil ? (
            <p className="chico suave">
              Modelos: {servidor.perfil === "pago" ? "de pago (Claude Haiku 4.5, sin retención de datos)" : "gratis de OpenRouter"} · Métricas guardadas en{" "}
              {servidor.almacen === "supabase" ? "Supabase" : servidor.almacen === "archivo" ? "un archivo del servidor" : "memoria (se pierden al reiniciar)"}
            </p>
          ) : null}
          <p className="chico suave">
            {datos.sesiones} sesiones · {datos.sesiones_con_documentos} con documentos · {datos.sesiones_con_borrador} con borrador · {datos.llamadas_ia.ok} llamadas de IA
            ({datos.llamadas_ia.cache} desde caché, {datos.llamadas_ia.error} con error). Los eventos no llevan cédulas, nombres, montos ni texto del chat.
          </p>
          <table className="tabla-kpi">
            <thead><tr><th>KPI</th><th>Meta</th><th className="num">Valor</th><th>Estado</th></tr></thead>
            <tbody>
              {datos.kpis.map((k) => (
                <tr key={k.id}>
                  <td><strong>{k.id}</strong> {k.nombre}<br /><span className="chico suave">{k.criterio}</span></td>
                  <td className="chico">{k.comparacion === "<=" ? "≤" : k.comparacion === ">=" ? "≥" : "="} {k.unidad === "USD" ? `USD ${k.meta}` : `${k.meta.toLocaleString("es-CO")} ${k.unidad}`}{k.fuente === "piloto" ? " · piloto" : ""}</td>
                  <td className="num">{FORMATO_KPI(k)}<br /><span className="chico suave">n = {k.n}</span></td>
                  <td><span className={`estado-kpi ${k.estado}`}>{ESTADO_KPI[k.estado]}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3 className="titular t-21 mt-3">Resultados del piloto</h3>
          <p className="chico suave">La exactitud frente al contador y el SUS se miden fuera de la app; regístralos aquí para verlos junto a los demás KPI.</p>
          <div className="fila-campos">
            <div className="campo">
              <label htmlFor="kpi-manual">KPI</label>
              <select id="kpi-manual" className="entrada" value={manual.kpi} onChange={(e) => setManual({ ...manual, kpi: e.target.value })}>
                {datos.kpis.filter((k) => k.fuente === "piloto").map((k) => <option key={k.id} value={k.id}>{k.id} · {k.nombre}</option>)}
              </select>
            </div>
            <div className="campo"><label htmlFor="kpi-valor">Valor</label><input id="kpi-valor" className="entrada" type="number" value={manual.valor} onChange={(e) => setManual({ ...manual, valor: e.target.value })} /></div>
            <div className="campo"><label htmlFor="kpi-n">Casos (n)</label><input id="kpi-n" className="entrada" type="number" value={manual.n} onChange={(e) => setManual({ ...manual, n: e.target.value })} /></div>
            <div className="campo"><label htmlFor="kpi-nota">Nota</label><input id="kpi-nota" className="entrada" value={manual.nota} onChange={(e) => setManual({ ...manual, nota: e.target.value })} /></div>
            <button className="boton chico" onClick={guardarManual} disabled={!manual.valor || !manual.n}>Guardar</button>
          </div>
        </>
      ) : !error ? <p className="suave" role="status">Cargando métricas…</p> : null}
    </div>
  );
}

export default function Configuracion() {
  const [pestana, setPestana] = useState<"reglas" | "agentes" | "metricas">("reglas");
  const [token, setToken] = useToken();
  const { modoLlm } = useSesion();
  return (
    <div className="contenedor pagina">
      <FadeIn>
        <h1 className="titular t-48">Reglas, agentes y métricas</h1>
        <p className="lead">Cambia los valores tributarios de cada año sin tocar código, elige qué modelo usa cada agente y revisa los KPI.</p>
      </FadeIn>
      <p className="chico suave">
        {modoLlm === "openrouter" ? "Conectado a OpenRouter." : "Modo simulado: falta la variable OPENROUTER_API_KEY en el servidor, así que los agentes con IA usan su ruta sin modelo."}
      </p>
      <div className="campo campo-angosto">
        <label htmlFor="token">Clave de administrador</label>
        <input id="token" className="entrada" type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" />
        <span className="ayuda">Necesaria para guardar cambios y ver métricas. Es la variable ADMIN_TOKEN del servidor (o entra con una cuenta de ADMIN_EMAILS).</span>
      </div>
      <Pestanas
        etiqueta="Qué configurar"
        idPanel="panel-config"
        valor={pestana}
        onCambio={setPestana}
        opciones={[
          { valor: "reglas", texto: "Reglas por año" },
          { valor: "agentes", texto: "Agentes" },
          { valor: "metricas", texto: "Métricas y KPI" },
        ]}
      />
      <div id="panel-config" role="tabpanel" aria-labelledby={`pestana-panel-config-${pestana}`}>
        {pestana === "reglas" ? <PanelReglas token={token} /> : pestana === "agentes" ? <PanelAgentes token={token} /> : <PanelMetricas token={token} />}
      </div>
    </div>
  );
}
