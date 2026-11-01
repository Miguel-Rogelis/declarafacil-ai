import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { FASES_DOCUMENTO, MesaAgentes } from "../components/MesaAgentes";
import { CampoPesos, Contador, Marca, Segmentado } from "../components/piezas";
import { analizarDocumento, api, type EventoAgente, type Fila, type ItemPatrimonio, type Respuestas } from "../lib/api";
import { useSesion } from "../lib/estado";
import { GRUPOS, NOMBRES_CAMPO, pesos } from "../lib/formato";

const PASOS = [
  { id: "exogena", corto: "Exógena" },
  { id: "revisar", corto: "Confirmar" },
  { id: "dependientes", corto: "Personas a cargo" },
  { id: "gastos", corto: "Gastos" },
  { id: "otros", corto: "Otros ingresos y bienes" },
  { id: "historial", corto: "Tu historial" },
] as const;
type PasoId = (typeof PASOS)[number]["id"];

function Bot({ children }: { children: ReactNode }) {
  return (
    <motion.div className="burbuja bot" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
      <div className="quien"><Marca /> DeclaraFácil</div>
      {children}
    </motion.div>
  );
}

function Usuario({ children }: { children: ReactNode }) {
  return <div className="burbuja usuario">{children}</div>;
}

// ---------- Hoja de trabajo ----------

function HojaTrabajo({ filas, respuestas }: { filas: Fila[]; respuestas: Respuestas }) {
  const grupos = useMemo(
    () =>
      GRUPOS.map((g) => ({
        ...g,
        filas: filas.filter((f) => f.campo && g.prefijos.some((p) => f.campo!.startsWith(p)) && f.tratamiento !== "informativo"),
      })).filter((g) => g.filas.length),
    [filas],
  );
  const extras: { concepto: string; valor: number }[] = [
    ...(respuestas.dependientes ? [{ concepto: `Personas a cargo: ${respuestas.dependientes}`, valor: NaN }] : []),
    ...([
      ["Medicina prepagada", respuestas.medicina_prepagada],
      ["Intereses de vivienda", respuestas.intereses_vivienda],
      ["Aportes voluntarios y AFC", respuestas.aportes_voluntarios_afc_fpv],
      ["4x1000 pagado", respuestas.gmf_pagado],
      ["Honorarios no reportados", respuestas.honorarios_no_reportados],
      ["Arriendos", respuestas.arriendos_no_reportados],
      ["Otros ingresos", respuestas.otros_ingresos_no_reportados],
    ] as [string, number][])
      .filter(([, v]) => v > 0)
      .map(([concepto, valor]) => ({ concepto, valor })),
    ...respuestas.bienes_adicionales.map((b) => ({ concepto: `Bien: ${b.concepto}`, valor: b.valor })),
    ...respuestas.deudas_adicionales.map((b) => ({ concepto: `Deuda: ${b.concepto}`, valor: b.valor })),
  ];
  return (
    <aside className="hoja-trabajo" aria-label="Hoja de trabajo">
      <header>
        <h2 className="titular t-21">Hoja de trabajo</h2>
        <span className="chico suave">Lo que vamos a llevar a tu declaración y de dónde sale.</span>
      </header>
      {!filas.length ? (
        <p className="vacio">Cuando subas tu exógena, aquí verás cada dato encontrado, de qué entidad viene y en qué parte de la declaración va.</p>
      ) : (
        <>
          {grupos.map((g) => (
            <div className="grupo" key={g.titulo}>
              <h3>{g.titulo}</h3>
              {g.filas.map((f) => (
                <div key={f.id} className={`fila-hoja${f.tratamiento === "revisar" ? " revisar" : ""}`}>
                  <span className="concepto">{NOMBRES_CAMPO[f.campo!] ?? f.detalle}</span>
                  <span className="monto">{pesos(f.valor)}</span>
                  <span className="origen">
                    {f.informante ?? "Reportado"}
                    {f.tratamiento === "revisar" ? ", falta tu confirmación" : f.origen_mapeo === "ia" ? ", ubicado por IA" : ""}
                  </span>
                </div>
              ))}
            </div>
          ))}
          {extras.length ? (
            <div className="grupo">
              <h3>Agregado por ti</h3>
              {extras.map((e) => (
                <div key={e.concepto} className="fila-hoja">
                  <span className="concepto">{e.concepto}</span>
                  <span className="monto">{Number.isNaN(e.valor) ? "" : pesos(e.valor)}</span>
                </div>
              ))}
            </div>
          ) : null}
        </>
      )}
    </aside>
  );
}

// ---------- Paso: subir exógena ----------

function PasoExogena({ alTerminar }: { alTerminar: () => void }) {
  const { anio, extraccion, setExtraccion, setFilas, trazaDocumento, setTrazaDocumento, archivoPendiente, setArchivoPendiente, setRespuestas } = useSesion();
  const [modo, setModo] = useState<"inicio" | "cargar" | "como">("inicio");
  const [eventos, setEventos] = useState<EventoAgente[]>(trazaDocumento);
  const [procesando, setProcesando] = useState(false);
  const [error, setError] = useState("");
  const [arrastrando, setArrastrando] = useState(false);
  const [nombreArchivo, setNombreArchivo] = useState("");
  const input = useRef<HTMLInputElement>(null);

  const procesar = useCallback(
    async (archivo: File) => {
      setNombreArchivo(archivo.name);
      setProcesando(true);
      setError("");
      setEventos([]);
      const acumulado: EventoAgente[] = [];
      await analizarDocumento(archivo, anio, {
        onAgente: (e) => {
          acumulado.push(e);
          setEventos([...acumulado]);
        },
        onResultado: (r) => {
          setExtraccion(r.extraccion);
          setFilas(r.extraccion.filas);
          setTrazaDocumento(r.traza);
          setRespuestas((x) => ({
            ...x,
            ultimos_dos_digitos_nit: r.extraccion.ultimos_dos_digitos_nit,
            declaraciones_previas: r.extraccion.perfil.declaro_antes ? null : x.declaraciones_previas,
          }));
        },
        onError: (m) => setError(m),
      });
      setProcesando(false);
    },
    [anio, setExtraccion, setFilas, setTrazaDocumento, setRespuestas],
  );

  useEffect(() => {
    if (archivoPendiente && !extraccion) {
      const a = archivoPendiente;
      setArchivoPendiente(null);
      void procesar(a);
    }
  }, [archivoPendiente, extraccion, procesar, setArchivoPendiente]);

  const usarEjemplo = async () => {
    try {
      await procesar(await api.exogenaDemo());
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const total = extraccion?.filas.length ?? 0;
  const ubicados = extraccion?.filas.filter((f) => f.tratamiento === "suma").length ?? 0;
  const porRevisar = extraccion?.filas.filter((f) => f.tratamiento === "revisar").length ?? 0;
  const informativos = total - ubicados - porRevisar;

  return (
    <>
      <Bot>
        <p>Hola. Empecemos con tu reporte de información exógena del año gravable {anio}: el Excel que descargas de la DIAN con lo que bancos, empleadores y fondos reportaron sobre ti.</p>
        {!extraccion && !procesando && modo !== "cargar" ? (
          <div className="opciones">
            <button className="boton chico" onClick={() => setModo("cargar")}>Ya lo tengo</button>
            <button className="boton secundario chico" onClick={() => setModo("como")}>¿Cómo lo descargo?</button>
            <button className="boton-texto" onClick={usarEjemplo}>Usar un ejemplo ficticio</button>
          </div>
        ) : null}
      </Bot>

      {modo === "como" && !extraccion ? (
        <Bot>
          <p>Toma unos dos minutos:</p>
          <ol>
            <li>Entra a dian.gov.co y elige “Usuario registrado”.</li>
            <li>Inicia sesión en MUISCA con tu cédula y contraseña.</li>
            <li>Busca “Consultar información exógena” y elige el año {anio}.</li>
            <li>Descarga el reporte en Excel.</li>
          </ol>
          <div className="opciones">
            <button className="boton chico" onClick={() => setModo("cargar")}>Ya lo descargué</button>
            <a className="boton secundario chico" href="https://www.dian.gov.co" target="_blank" rel="noreferrer">Abrir la DIAN</a>
          </div>
        </Bot>
      ) : null}

      {(modo === "cargar" || error) && !extraccion && !procesando ? (
        <Bot>
          <p>Súbelo aquí. Lo leemos en memoria y no lo guardamos.</p>
          <div
            className={`zona-carga${arrastrando ? " activa" : ""}`}
            role="button"
            tabIndex={0}
            onClick={() => input.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setArrastrando(true);
            }}
            onDragLeave={() => setArrastrando(false)}
            onDrop={(e) => {
              e.preventDefault();
              setArrastrando(false);
              const f = e.dataTransfer.files[0];
              if (f) void procesar(f);
            }}
          >
            <strong>Arrastra tu archivo o haz clic para elegirlo</strong>
            <span className="chico suave">Excel (.xlsx) o PDF, máximo 5 MB</span>
          </div>
          <input
            ref={input}
            type="file"
            accept=".xlsx,.pdf"
            className="visualmente-oculto"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void procesar(f);
              e.target.value = "";
            }}
          />
        </Bot>
      ) : null}

      {nombreArchivo || extraccion ? <Usuario>{nombreArchivo || "Mi exógena"}</Usuario> : null}

      {procesando || eventos.length ? (
        <Bot>
          <p>{procesando ? "Trabajando en tu archivo:" : "Así se procesó tu archivo:"}</p>
          <MesaAgentes fases={FASES_DOCUMENTO} eventos={eventos} compacta />
        </Bot>
      ) : null}

      {error ? (
        <Bot>
          <p><strong>No pude leer el archivo.</strong> {error}</p>
          <p className="chico suave">Verifica que sea el reporte de exógena descargado de MUISCA y vuelve a subirlo.</p>
        </Bot>
      ) : null}

      {extraccion && !procesando ? (
        <Bot>
          <p>
            Leí {total} datos. Ubiqué {ubicados} en tu declaración, {informativos} solo sirven para saber si estás obligado a declarar
            {porRevisar ? ` y ${porRevisar} necesitan que los confirmes` : ""}.
          </p>
          <p className="chico suave">
            Quitamos {extraccion.datos_enmascarados} datos personales antes de usar IA
            {extraccion.ultimos_dos_digitos_nit ? `. Tu cédula termina en ${extraccion.ultimos_dos_digitos_nit}; con eso revisamos tu fecha límite.` : "."}
          </p>
          <div className="opciones">
            <button className="boton chico" onClick={alTerminar}>Continuar</button>
          </div>
        </Bot>
      ) : null}
    </>
  );
}

// ---------- Paso: confirmar filas dudosas ----------

const CAMPOS_ELEGIBLES = Object.entries(NOMBRES_CAMPO).filter(([k]) => !k.endsWith("salario_promedio_mensual_6m"));

function PasoRevisar({ alTerminar }: { alTerminar: () => void }) {
  const { filas, setFilas } = useSesion();
  // Se fija la lista al entrar al paso para que las tarjetas no desaparezcan al decidir
  const [ids] = useState(() => new Set(filas.filter((f) => f.tratamiento === "revisar" || f.origen_mapeo === "ia").map((f) => f.id)));
  const pendientes = filas.filter((f) => ids.has(f.id));
  const [decididas, setDecididas] = useState<Record<string, "suma" | "no">>({});
  const [destino, setDestino] = useState<Record<string, string>>({});

  const decidir = (f: Fila, d: "suma" | "no") => {
    const campo = f.campo ?? destino[f.id] ?? null;
    if (d === "suma" && !campo) return;
    setDecididas((x) => ({ ...x, [f.id]: d }));
    setFilas(filas.map((x) => (x.id === f.id ? { ...x, campo: d === "suma" ? campo : x.campo, tratamiento: d === "suma" ? "suma" : "informativo" } : x)));
  };

  if (!pendientes.length) {
    return (
      <Bot>
        <p>Todos los datos de tu exógena quedaron ubicados con reglas. No hay nada que confirmar.</p>
        <div className="opciones"><button className="boton chico" onClick={alTerminar}>Continuar</button></div>
      </Bot>
    );
  }
  return (
    <Bot>
      <p>Estos datos necesitan tu visto bueno. Solo los sumo a la declaración si me lo confirmas.</p>
      {pendientes.map((f) => (
        <div key={f.id} className={`tarjeta-revisar${decididas[f.id] ? " decidida" : ""}`}>
          <div className="monto">{pesos(f.valor)}</div>
          <div>{f.detalle}</div>
          <div className="chico suave">{f.informante}</div>
          <p className="chico" style={{ marginTop: "0.4rem" }}>{f.explicacion}</p>
          {f.origen_mapeo === "ia" && f.campo ? <p className="chico"><span className="etiqueta-ia">IA</span> Lo ubicó en: {NOMBRES_CAMPO[f.campo]}</p> : null}
          {!f.campo ? (
            <div className="campo">
              <label htmlFor={`destino-${f.id}`}>¿Dónde va?</label>
              <select id={`destino-${f.id}`} className="entrada" value={destino[f.id] ?? ""} onChange={(e) => setDestino((x) => ({ ...x, [f.id]: e.target.value }))}>
                <option value="">Elige una opción</option>
                {CAMPOS_ELEGIBLES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
          ) : null}
          <div className="acciones">
            {decididas[f.id] ? (
              <span className="chico">{decididas[f.id] === "suma" ? "Lo incluiremos." : "No lo incluiremos."}</span>
            ) : null}
            <button className="boton chico" onClick={() => decidir(f, "suma")} disabled={!f.campo && !destino[f.id]}>Incluirlo</button>
            <button className="boton secundario chico" onClick={() => decidir(f, "no")}>No incluirlo</button>
          </div>
        </div>
      ))}
      <div className="opciones">
        <button className="boton chico" onClick={alTerminar}>
          {Object.keys(decididas).length < pendientes.length ? "Seguir sin incluir los demás" : "Continuar"}
        </button>
      </div>
    </Bot>
  );
}

// ---------- Paso: dependientes ----------

function PasoDependientes({ alTerminar }: { alTerminar: () => void }) {
  const { respuestas, setRespuestas } = useSesion();
  const [verQuien, setVerQuien] = useState(false);
  return (
    <Bot>
      <p>¿Cuántas personas dependen económicamente de ti?</p>
      <div className="opciones">
        <Contador etiqueta="Personas a cargo" valor={respuestas.dependientes} max={5} onCambio={(v) => setRespuestas((r) => ({ ...r, dependientes: v }))} />
      </div>
      <button className="boton-texto" onClick={() => setVerQuien(!verQuien)} aria-expanded={verQuien}>¿Quién cuenta como dependiente?</button>
      <AnimatePresence>
        {verQuien ? (
          <motion.ul initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="chico" style={{ overflow: "hidden" }}>
            <li>Hijos menores de 18 años.</li>
            <li>Hijos de 18 a 23 años que estudian y dependen de ti.</li>
            <li>Hijos mayores de 23 con discapacidad que dependan de ti.</li>
            <li>Cónyuge, compañero, padres o hermanos con ingresos menores a 260 UVT al año.</li>
          </motion.ul>
        ) : null}
      </AnimatePresence>
      <p className="chico suave">Por el primero restas hasta el 10 % de tus ingresos de trabajo, y además 72 UVT por cada uno, hasta cuatro.</p>
      <div className="opciones"><button className="boton chico" onClick={alTerminar}>Continuar</button></div>
    </Bot>
  );
}

// ---------- Paso: gastos deducibles ----------

function PasoGastos({ alTerminar }: { alTerminar: () => void }) {
  const { respuestas, setRespuestas, extraccion } = useSesion();
  const enc = extraccion?.resumen_campos ?? {};
  const poner = (k: keyof Respuestas) => (v: number) => setRespuestas((r) => ({ ...r, [k]: v }));
  return (
    <Bot>
      <p>Estos gastos pueden bajar tu impuesto. Escribe el total del año; si no aplica, déjalo vacío.</p>
      <CampoPesos id="prepagada" etiqueta="Medicina prepagada o pólizas de salud" valor={respuestas.medicina_prepagada} onCambio={poner("medicina_prepagada")} encontrado={enc["deducciones.medicina_prepagada"]} ayuda="Está en el certificado anual de tu prepagada." />
      <CampoPesos id="vivienda" etiqueta="Intereses pagados por crédito de vivienda" valor={respuestas.intereses_vivienda} onCambio={poner("intereses_vivienda")} encontrado={enc["deducciones.intereses_vivienda"]} ayuda="Solo los intereses, no el abono a capital. Pide el certificado al banco." />
      <CampoPesos id="afc" etiqueta="Aportes voluntarios a pensión o cuentas AFC" valor={respuestas.aportes_voluntarios_afc_fpv} onCambio={poner("aportes_voluntarios_afc_fpv")} encontrado={enc["deducciones.aportes_voluntarios_afc_fpv"]} />
      <CampoPesos id="gmf" etiqueta="4x1000 que te cobraron los bancos" valor={respuestas.gmf_pagado} onCambio={poner("gmf_pagado")} encontrado={enc["deducciones.gmf_pagado"]} ayuda="Está en el certificado tributario de cada banco. Restas la mitad." />
      <div className="opciones"><button className="boton chico" onClick={alTerminar}>Continuar</button></div>
    </Bot>
  );
}

// ---------- Paso: otros ingresos y bienes ----------

function ListaItems({ titulo, items, onCambio }: { titulo: string; items: ItemPatrimonio[]; onCambio: (i: ItemPatrimonio[]) => void }) {
  return (
    <div>
      {items.map((it, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 10rem auto", gap: "0.5rem", alignItems: "end" }}>
          <div className="campo">
            <label htmlFor={`${titulo}-c-${i}`}>Qué es</label>
            <input id={`${titulo}-c-${i}`} className="entrada" value={it.concepto} placeholder="Carro Mazda 2019" onChange={(e) => onCambio(items.map((x, j) => (j === i ? { ...x, concepto: e.target.value } : x)))} />
          </div>
          <CampoPesos id={`${titulo}-v-${i}`} etiqueta="Valor" valor={it.valor} onCambio={(v) => onCambio(items.map((x, j) => (j === i ? { ...x, valor: v } : x)))} />
          <button className="boton secundario chico" onClick={() => onCambio(items.filter((_, j) => j !== i))} aria-label={`Quitar ${it.concepto || "fila"}`}>Quitar</button>
        </div>
      ))}
      <button className="boton-texto" onClick={() => onCambio([...items, { concepto: "", valor: 0 }])}>Agregar {titulo}</button>
    </div>
  );
}

function OpcionDesplegable({ abierto, onAlternar, texto, children }: { abierto: boolean; onAlternar: () => void; texto: string; children: ReactNode }) {
  return (
    <div>
      <label className="casilla">
        <input type="checkbox" checked={abierto} onChange={onAlternar} />
        <span>{texto}</span>
      </label>
      {abierto ? <div style={{ paddingLeft: "1.75rem" }}>{children}</div> : null}
    </div>
  );
}

function PasoOtros({ alTerminar }: { alTerminar: () => void }) {
  const { respuestas: r, setRespuestas, extraccion } = useSesion();
  const [abiertos, setAbiertos] = useState<Record<string, boolean>>({});
  const poner = (k: keyof Respuestas) => (v: number) => setRespuestas((x) => ({ ...x, [k]: v }));
  const go = (k: keyof Respuestas["ganancias_ocasionales"]) => (v: number) => setRespuestas((x) => ({ ...x, ganancias_ocasionales: { ...x.ganancias_ocasionales, [k]: v } }));
  const alternar = (k: string) => setAbiertos((a) => ({ ...a, [k]: !a[k] }));
  return (
    <Bot>
      <p>La exógena no trae todo. Marca lo que te aplica en {extraccion?.anio ?? "el año"}:</p>
      <OpcionDesplegable abierto={!!abiertos["ind"]} onAlternar={() => alternar("ind")} texto="Recibí pagos como independiente que no aparecen">
        <CampoPesos id="hon" etiqueta="Honorarios o servicios" valor={r.honorarios_no_reportados} onCambio={poner("honorarios_no_reportados")} />
        <CampoPesos id="costos" etiqueta="Costos y gastos de esa actividad, con factura" valor={r.costos_independiente} onCambio={poner("costos_independiente")} ayuda="Elegimos lo que más te convenga: restar costos o el 25 % exento." />
      </OpcionDesplegable>
      <OpcionDesplegable abierto={!!abiertos["arr"]} onAlternar={() => alternar("arr")} texto="Recibí arriendos">
        <CampoPesos id="arriendos" etiqueta="Arriendos del año" valor={r.arriendos_no_reportados} onCambio={poner("arriendos_no_reportados")} />
      </OpcionDesplegable>
      <OpcionDesplegable abierto={!!abiertos["pen"]} onAlternar={() => alternar("pen")} texto="Recibí una pensión que no aparece">
        <CampoPesos id="pension" etiqueta="Pensión del año" valor={r.pensiones_no_reportadas} onCambio={poner("pensiones_no_reportadas")} />
      </OpcionDesplegable>
      <OpcionDesplegable abierto={!!abiertos["otros"]} onAlternar={() => alternar("otros")} texto="Recibí otros ingresos (ventas, comisiones ocasionales)">
        <CampoPesos id="otrosing" etiqueta="Otros ingresos" valor={r.otros_ingresos_no_reportados} onCambio={poner("otros_ingresos_no_reportados")} />
      </OpcionDesplegable>
      {extraccion?.perfil.dividendos ? (
        <OpcionDesplegable abierto={!!abiertos["div"]} onAlternar={() => alternar("div")} texto="Parte de mis dividendos son gravados">
          <CampoPesos id="divg" etiqueta="Dividendos gravados según el certificado" valor={r.dividendos_gravados} onCambio={poner("dividendos_gravados")} />
        </OpcionDesplegable>
      ) : null}
      <OpcionDesplegable abierto={!!abiertos["go"]} onAlternar={() => alternar("go")} texto="Vendí una casa u otro bien, heredé o recibí una donación, un seguro de vida o un premio">
        <CampoPesos id="casa" etiqueta="Utilidad en la venta de tu casa o apartamento" valor={r.ganancias_ocasionales.utilidad_venta_casa_habitacion} onCambio={go("utilidad_venta_casa_habitacion")} ayuda="Precio de venta menos lo que te costó." />
        {r.ganancias_ocasionales.utilidad_venta_casa_habitacion ? (
          <label className="casilla">
            <input type="checkbox" checked={r.ganancias_ocasionales.cumple_requisitos_exencion_casa} onChange={(e) => setRespuestas((x) => ({ ...x, ganancias_ocasionales: { ...x.ganancias_ocasionales, cumple_requisitos_exencion_casa: e.target.checked } }))} />
            <span>El dinero fue a una cuenta AFC, a otra vivienda o al crédito hipotecario</span>
          </label>
        ) : null}
        <CampoPesos id="activos" etiqueta="Utilidad en la venta de otros bienes que tuviste dos años o más" valor={r.ganancias_ocasionales.utilidad_venta_otros_activos} onCambio={go("utilidad_venta_otros_activos")} />
        <CampoPesos id="herv" etiqueta="Herencia: vivienda de quien falleció" valor={r.ganancias_ocasionales.herencia_vivienda_causante} onCambio={go("herencia_vivienda_causante")} />
        <CampoPesos id="hero" etiqueta="Herencia: otros inmuebles" valor={r.ganancias_ocasionales.herencia_otros_inmuebles} onCambio={go("herencia_otros_inmuebles")} />
        <CampoPesos id="herp" etiqueta="Herencia o legado recibido como heredero" valor={r.ganancias_ocasionales.herencia_porcion_heredero} onCambio={go("herencia_porcion_heredero")} />
        <CampoPesos id="don" etiqueta="Donaciones recibidas" valor={r.ganancias_ocasionales.donaciones_recibidas} onCambio={go("donaciones_recibidas")} />
        <CampoPesos id="seg" etiqueta="Seguro de vida cobrado" valor={r.ganancias_ocasionales.seguros_vida} onCambio={go("seguros_vida")} />
        <CampoPesos id="lot" etiqueta="Loterías, rifas o premios" valor={r.ganancias_ocasionales.loterias_premios} onCambio={go("loterias_premios")} />
      </OpcionDesplegable>
      <OpcionDesplegable abierto={!!abiertos["bienes"]} onAlternar={() => alternar("bienes")} texto="Tengo bienes que no aparecen (carro, moto, otros)">
        <ListaItems titulo="bien" items={r.bienes_adicionales} onCambio={(i) => setRespuestas((x) => ({ ...x, bienes_adicionales: i }))} />
      </OpcionDesplegable>
      <OpcionDesplegable abierto={!!abiertos["deudas"]} onAlternar={() => alternar("deudas")} texto="Tengo deudas que no aparecen">
        <ListaItems titulo="deuda" items={r.deudas_adicionales} onCambio={(i) => setRespuestas((x) => ({ ...x, deudas_adicionales: i }))} />
      </OpcionDesplegable>
      <label className="casilla">
        <input type="checkbox" checked={r.responsable_iva} onChange={(e) => setRespuestas((x) => ({ ...x, responsable_iva: e.target.checked }))} />
        <span>Soy responsable de IVA</span>
      </label>
      <div className="opciones"><button className="boton chico" onClick={alTerminar}>Continuar</button></div>
    </Bot>
  );
}

// ---------- Paso: historial ----------

function PasoHistorial({ alCalcular }: { alCalcular: () => void }) {
  const { respuestas: r, setRespuestas, extraccion } = useSesion();
  return (
    <Bot>
      <p>Por último, tu historial con la DIAN. Define el anticipo y si hay sanción por fecha.</p>
      <div className="campo">
        <span className="rotulo">¿Cuántas veces has declarado renta antes de esta?</span>
        {extraccion?.perfil.declaro_antes ? <span className="dato-encontrado">Tu exógena muestra que declaraste el año pasado.</span> : null}
        <Segmentado
          etiqueta="Declaraciones anteriores"
          valor={r.declaraciones_previas}
          onCambio={(v) => setRespuestas((x) => ({ ...x, declaraciones_previas: v }))}
          opciones={[{ valor: 0, texto: "Ninguna" }, { valor: 1, texto: "Una" }, { valor: 2, texto: "Dos o más" }]}
        />
      </div>
      {r.declaraciones_previas ? (
        <>
          <CampoPesos id="impant" etiqueta="Impuesto neto de renta de tu declaración anterior (opcional)" valor={r.impuesto_neto_anio_anterior} onCambio={(v) => setRespuestas((x) => ({ ...x, impuesto_neto_anio_anterior: v }))} ayuda="Con este dato podemos calcular un anticipo menor." />
          <CampoPesos id="antant" etiqueta="Anticipo que liquidaste para este año en tu declaración anterior" valor={r.anticipo_anio_anterior} onCambio={(v) => setRespuestas((x) => ({ ...x, anticipo_anio_anterior: v }))} />
        </>
      ) : null}
      <div className="campo">
        <label htmlFor="digitos">Dos últimos dígitos de tu cédula</label>
        <input
          id="digitos"
          className="entrada"
          style={{ maxWidth: "6rem" }}
          inputMode="numeric"
          maxLength={2}
          value={r.ultimos_dos_digitos_nit ?? ""}
          onChange={(e) => setRespuestas((x) => ({ ...x, ultimos_dos_digitos_nit: e.target.value.replace(/\D/g, "").slice(0, 2) || null }))}
        />
      </div>
      <label className="casilla">
        <input type="checkbox" checked={r.sin_sanciones_ultimos_2_anios} onChange={(e) => setRespuestas((x) => ({ ...x, sin_sanciones_ultimos_2_anios: e.target.checked }))} />
        <span>No me han sancionado por declarar tarde en los últimos dos años</span>
      </label>
      <div className="opciones">
        <button className="boton sello" onClick={alCalcular} disabled={r.declaraciones_previas === null || (r.ultimos_dos_digitos_nit?.length ?? 0) === 1}>
          Calcular mi declaración
        </button>
      </div>
      {r.declaraciones_previas === null ? <p className="chico suave">Elige cuántas veces has declarado para continuar.</p> : null}
    </Bot>
  );
}

// ---------- Página ----------

export default function Declarar() {
  const { filas, respuestas, extraccion, ir, setResultado } = useSesion();
  const volviendo = !!extraccion && respuestas.declaraciones_previas !== null;
  const [paso, setPaso] = useState<PasoId>(volviendo ? "historial" : extraccion ? "revisar" : "exogena");
  const [alcanzado, setAlcanzado] = useState(volviendo ? PASOS.length - 1 : extraccion ? 1 : 0);
  const indice = PASOS.findIndex((p) => p.id === paso);
  const fin = useRef<HTMLDivElement>(null);

  const avanzar = (siguiente: PasoId) => {
    const i = PASOS.findIndex((p) => p.id === siguiente);
    setAlcanzado((a) => Math.max(a, i));
    setPaso(siguiente);
  };
  useEffect(() => {
    if (indice > 0) fin.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [indice]);

  const resumenUsuario: Record<PasoId, string> = {
    exogena: "",
    revisar: "Listo, revisé los datos.",
    dependientes: respuestas.dependientes ? `${respuestas.dependientes} persona(s) a cargo.` : "Nadie depende de mí.",
    gastos: "Ya puse mis gastos.",
    otros: "Listo con otros ingresos y bienes.",
    historial: "",
  };

  return (
    <div className="contenedor taller">
      <section aria-label="Conversación guiada">
        <ol className="progreso" aria-label="Pasos">
          {PASOS.map((p, i) => (
            <li key={p.id} className={i === indice ? "actual" : i <= alcanzado ? "hecho" : undefined}>
              <button disabled={i > alcanzado || (i > 0 && !extraccion)} onClick={() => setPaso(p.id)} aria-current={i === indice ? "step" : undefined}>
                <div className="barra" />
                {p.corto}
              </button>
            </li>
          ))}
        </ol>
        <div className="conversacion">
          {paso === "exogena" ? <PasoExogena alTerminar={() => avanzar("revisar")} /> : null}
          {indice >= 1 ? (
            <>
              {indice > 1 ? (
                <>
                  <Bot><p>Revisamos los datos de tu exógena.</p></Bot>
                  <Usuario>{resumenUsuario.revisar}</Usuario>
                </>
              ) : null}
              {paso === "revisar" ? <PasoRevisar alTerminar={() => avanzar("dependientes")} /> : null}
              {indice > 2 ? <Usuario>{resumenUsuario.dependientes}</Usuario> : null}
              {paso === "dependientes" ? <PasoDependientes alTerminar={() => avanzar("gastos")} /> : null}
              {indice > 3 ? <Usuario>{resumenUsuario.gastos}</Usuario> : null}
              {paso === "gastos" ? <PasoGastos alTerminar={() => avanzar("otros")} /> : null}
              {indice > 4 ? <Usuario>{resumenUsuario.otros}</Usuario> : null}
              {paso === "otros" ? <PasoOtros alTerminar={() => avanzar("historial")} /> : null}
              {paso === "historial" ? (
                <PasoHistorial
                  alCalcular={() => {
                    setResultado(null);
                    ir("resultado");
                  }}
                />
              ) : null}
            </>
          ) : null}
          <div ref={fin} />
        </div>
      </section>
      <HojaTrabajo filas={filas} respuestas={respuestas} />
    </div>
  );
}
