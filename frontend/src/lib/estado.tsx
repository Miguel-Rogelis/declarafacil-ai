import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  analizarDocumento,
  api,
  liquidar,
  respuestasIniciales,
  type Anotacion,
  type AnioDisponible,
  type EstadoChat,
  type EventoAgente,
  type Extraccion,
  type Fila,
  type PreguntaPendiente,
  type Respuestas,
  type ResultadoLiquidacion,
  type Simulacion,
} from "./api";

export type Ruta = "inicio" | "declarar" | "resultado" | "configuracion";

export type Widget = "subir_exogena" | "revisar" | "traza_documento" | "traza_calculo" | "resultado" | "anotado" | "simulacion";

export interface Mensaje {
  id: number;
  rol: "usuario" | "asistente";
  texto?: string;
  widget?: Widget;
  anotaciones?: Anotacion[];
  quitadas?: string[];
  antes?: Respuestas;
  /** El agente pidió un dato que le falta. */
  pregunta?: boolean;
  /** Texto completo para el historial que va al agente (incluye la pregunta que se muestra en el cuadro). */
  historial?: string;
  /** Solo va en el historial; no se dibuja (la pregunta ya está en el cuadro). */
  oculto?: boolean;
  simulacion?: Simulacion;
  deshecho?: boolean;
  eventos?: EventoAgente[];
  fuentes?: string[];
  conIa?: boolean;
  aviso?: boolean;
  /** Foto del resultado cuando se calculó (los mensajes viejos no cambian si se recalcula). */
  resultado?: ResultadoLiquidacion;
}

interface Sesion {
  ruta: Ruta;
  ir: (r: Ruta) => void;
  anio: number;
  cambiarAnio: (a: number) => void;
  anios: AnioDisponible[];
  modoLlm: string;
  extraccion: Extraccion | null;
  filas: Fila[];
  decidir: (id: string, incluir: boolean, campo?: string | null, texto?: string) => void;
  cambiarDecision: (id: string) => void;
  elecciones: Record<string, string>;
  pregunta: PreguntaPendiente | null;
  cerrarPregunta: () => void;
  decididas: Record<string, boolean>;
  trazaDocumento: EventoAgente[];
  respuestas: Respuestas;
  resultado: ResultadoLiquidacion | null;
  eventosCalculo: EventoAgente[];
  calculando: boolean;
  errorCalculo: string;
  mensajes: Mensaje[];
  escribiendo: boolean;
  enviar: (texto: string) => Promise<void>;
  deshacer: (id: number) => void;
  procesarArchivo: (f: File) => Promise<void>;
  usarEjemplo: () => Promise<void>;
  calcular: (opciones?: { silencioso?: boolean }) => Promise<void>;
  archivoPendiente: File | null;
  setArchivoPendiente: (f: File | null) => void;
  reiniciar: () => void;
  porRevisar: Fila[];
  hayDatos: boolean;
}

const Ctx = createContext<Sesion | null>(null);

const RUTAS: Ruta[] = ["inicio", "declarar", "resultado", "configuracion"];
const leerRuta = (): Ruta => {
  const h = window.location.hash.replace("#/", "") as Ruta;
  return RUTAS.includes(h) ? h : "inicio";
};

const porRevisarDe = (f: Fila[], d: Record<string, boolean>) =>
  f.filter((x) => (x.tratamiento === "revisar" || x.origen_mapeo === "ia") && !(x.id in d));

const tieneDatos = (ex: Extraccion | null, r: Respuestas) =>
  !!ex ||
  r.salarios_no_reportados + r.honorarios_no_reportados + r.pensiones_no_reportadas + r.otros_ingresos_no_reportados + r.arriendos_no_reportados + r.dividendos_no_reportados > 0 ||
  r.bienes_adicionales.length > 0;

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [ruta, setRuta] = useState<Ruta>(leerRuta);
  const [anio, setAnio] = useState(2025);
  const [anios, setAnios] = useState<AnioDisponible[]>([]);
  const [modoLlm, setModoLlm] = useState("");
  const [extraccion, setExtraccion] = useState<Extraccion | null>(null);
  const [filas, setFilas] = useState<Fila[]>([]);
  const [decididas, setDecididas] = useState<Record<string, boolean>>({});
  const [trazaDocumento, setTrazaDocumento] = useState<EventoAgente[]>([]);
  const [respuestas, setRespuestas] = useState<Respuestas>(respuestasIniciales);
  const [resultado, setResultado] = useState<ResultadoLiquidacion | null>(null);
  const [eventosCalculo, setEventosCalculo] = useState<EventoAgente[]>([]);
  const [calculando, setCalculando] = useState(false);
  const [errorCalculo, setErrorCalculo] = useState("");
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [escribiendo, setEscribiendo] = useState(false);
  const [archivoPendiente, setArchivoPendiente] = useState<File | null>(null);
  const contador = useRef(1);
  const conversacion = useRef<{ pregunta: PreguntaPendiente | null; ya: string[] }>({ pregunta: null, ya: [] });
  const [pregunta, setPregunta] = useState<PreguntaPendiente | null>(null);
  const [elecciones, setElecciones] = useState<Record<string, string>>({});
  const ponerPregunta = useCallback((p: PreguntaPendiente | null, ya: string[]) => {
    conversacion.current = { pregunta: p, ya };
    setPregunta(p?.partes?.length ? p : null);
  }, []);
  const cerrarPregunta = useCallback(() => setPregunta(null), []);

  // Estado más reciente para los callbacks asíncronos. Se actualiza a mano cuando una
  // acción depende de un cambio que React todavía no ha aplicado (p. ej. cambiar de año y calcular).
  const ref = useRef({ anio, extraccion, filas, decididas, respuestas, resultado, ruta, mensajes });
  ref.current = { ...ref.current, anio, extraccion, filas, decididas, respuestas, resultado, ruta, mensajes };

  useEffect(() => {
    const alCambiar = () => setRuta(leerRuta());
    window.addEventListener("hashchange", alCambiar);
    api
      .estado()
      .then((e) => {
        setAnios(e.anios);
        setModoLlm(e.modo_llm);
      })
      .catch(() => setAnios([{ anio_gravable: 2025, estado: "vigente", uvt: 49799, descripcion: "" }]));
    return () => window.removeEventListener("hashchange", alCambiar);
  }, []);

  const ir = useCallback((r: Ruta) => {
    window.location.hash = `#/${r}`;
    window.scrollTo({ top: 0 });
  }, []);

  const agregar = useCallback((m: Omit<Mensaje, "id">) => {
    const id = contador.current++;
    setMensajes((x) => [...x, { ...m, id }]);
    return id;
  }, []);
  const actualizar = useCallback((id: number, cambios: Partial<Mensaje>) => {
    setMensajes((x) => x.map((m) => (m.id === id ? { ...m, ...cambios } : m)));
  }, []);

  const estadoChat = useCallback((): EstadoChat => {
    const s = ref.current;
    const r = s.resultado?.liquidacion;
    return {
      pantalla: s.ruta,
      anio_gravable: s.anio,
      tiene_exogena: !!s.extraccion,
      anio_exogena: s.extraccion?.anio ?? null,
      perfil: s.extraccion?.perfil ?? {},
      resumen_exogena: s.extraccion?.resumen_campos ?? {},
      por_revisar: porRevisarDe(s.filas, s.decididas).map((f) => f.detalle),
      filas: s.filas,
      topes: s.extraccion?.topes ?? {},
      respuestas: s.respuestas,
      pregunta_pendiente: conversacion.current.pregunta,
      ya_preguntado: conversacion.current.ya,
      resultado: r
        ? {
            anio_gravable: r.anio_gravable,
            obligado: r.obligacion.obligado,
            ...r.resumen,
            vencimiento: r.vencimiento?.fecha ?? null,
            alertas: r.alertas.slice(0, 6).map((a) => a.titulo),
          }
        : null,
    };
  }, []);

  /** Liquida con lo que haya. "silencioso" = recálculo automático: sin la traza de agentes. */
  const calcular = useCallback(
    async (opciones?: { silencioso?: boolean }) => {
      const s = ref.current;
      setCalculando(true);
      setErrorCalculo("");
      setEventosCalculo([]);
      const idTraza = opciones?.silencioso ? null : agregar({ rol: "asistente", widget: "traza_calculo", eventos: [] });
      const acumulado: EventoAgente[] = [];
      await liquidar(
        {
          anio_gravable: s.anio,
          filas: s.filas,
          topes: s.extraccion?.topes ?? {},
          ultimos_dos_digitos_nit: s.respuestas.ultimos_dos_digitos_nit ?? s.extraccion?.ultimos_dos_digitos_nit ?? null,
          respuestas: s.respuestas,
        },
        {
          onAgente: (e) => {
            acumulado.push(e);
            setEventosCalculo([...acumulado]);
            if (idTraza !== null) actualizar(idTraza, { eventos: [...acumulado] });
          },
          onResultado: (r) => {
            setResultado(r);
            ref.current.resultado = r;
            agregar({ rol: "asistente", widget: "resultado", resultado: r, aviso: opciones?.silencioso });
          },
          onError: (m) => {
            setErrorCalculo(m);
            agregar({ rol: "asistente", texto: `No pude calcular: ${m}` });
          },
        },
      );
      setCalculando(false);
    },
    [agregar, actualizar],
  );

  /** Si ya había un resultado y cambian los datos, el agente lo actualiza solo. */
  const recalcularSiHabia = useCallback(
    (habia: boolean) => {
      setResultado(null);
      ref.current.resultado = null;
      if (habia && tieneDatos(ref.current.extraccion, ref.current.respuestas)) void calcular({ silencioso: true });
    },
    [calcular],
  );

  const ponerAnio = useCallback((a: number) => {
    setAnio(a);
    ref.current.anio = a;
  }, []);

  const procesarArchivo = useCallback(
    async (archivo: File) => {
      agregar({ rol: "usuario", texto: `📎 ${archivo.name}` });
      const idTraza = agregar({ rol: "asistente", widget: "traza_documento", eventos: [] });
      const acumulado: EventoAgente[] = [];
      let leida = false;
      await analizarDocumento(archivo, ref.current.anio, {
        onAgente: (e) => {
          acumulado.push(e);
          actualizar(idTraza, { eventos: [...acumulado] });
        },
        onResultado: (r) => {
          const ex = r.extraccion;
          setExtraccion(ex);
          setFilas(ex.filas);
          setDecididas({});
          setTrazaDocumento(r.traza);
          setResultado(null);
          ref.current = { ...ref.current, extraccion: ex, filas: ex.filas, decididas: {}, resultado: null };
          const conDigitos = { ...ref.current.respuestas, ultimos_dos_digitos_nit: ref.current.respuestas.ultimos_dos_digitos_nit ?? ex.ultimos_dos_digitos_nit };
          setRespuestas(conDigitos);
          ref.current.respuestas = conDigitos;
          leida = true;
          const suma = ex.filas.filter((f) => f.tratamiento === "suma").length;
          const rev = porRevisarDe(ex.filas, {}).length;
          const partes = [`Leí ${ex.filas.length} datos de tu exógena: ubiqué ${suma} en tu declaración${rev ? ` y ${rev} necesitan tu confirmación` : ""}.`];
          partes.push(`Antes de usar IA quité ${ex.datos_enmascarados} datos personales.`);
          const vigentes = anios.filter((a) => a.estado === "vigente").map((a) => a.anio_gravable);
          if (ex.anio && ex.anio !== ref.current.anio) {
            if (vigentes.includes(ex.anio)) {
              ponerAnio(ex.anio);
              partes.push(`Como es del año ${ex.anio}, cambié a las reglas de ese año.`);
            } else {
              partes.push(`Ojo: el archivo es del año ${ex.anio} y no tengo reglas vigentes para ese año; sigo con ${ref.current.anio}.`);
            }
          }
          agregar({ rol: "asistente", texto: partes.join(" ") });
        },
        onError: (m) => {
          agregar({ rol: "asistente", texto: `No pude leer el archivo: ${m}` });
        },
      });
      if (!leida) return;
      // El agente dice qué dedujo de la exógena y pregunta lo que ella no muestra
      setEscribiendo(true);
      try {
        const d = await api.diagnostico(estadoChat());
        ponerPregunta(d.pregunta, d.ya_preguntado);
        const visible = d.texto_visible ?? d.respuesta;
        agregar({ rol: "asistente", texto: visible || undefined, historial: d.respuesta, oculto: !visible });
        d.widgets.forEach((w) => agregar({ rol: "asistente", widget: w as Widget }));
      } catch {
        if (porRevisarDe(ref.current.filas, {}).length) agregar({ rol: "asistente", widget: "revisar" });
      } finally {
        setEscribiendo(false);
      }
    },
    [agregar, actualizar, anios, ponerAnio, estadoChat, ponerPregunta],
  );

  const usarEjemplo = useCallback(async () => {
    try {
      await procesarArchivo(await api.exogenaDemo());
    } catch (e) {
      agregar({ rol: "asistente", texto: (e as Error).message });
    }
  }, [procesarArchivo, agregar]);

  const enviar = useCallback(
    async (texto: string) => {
      const t = texto.trim();
      if (!t) return;
      const s = ref.current;
      const historial = s.mensajes.filter((m) => m.historial || m.texto).slice(-10).map((m) => ({ rol: m.rol, texto: (m.historial ?? m.texto)! }));
      agregar({ rol: "usuario", texto: t });
      setEscribiendo(true);
      try {
        const antes = s.respuestas;
        const habia = !!s.resultado;
        const r = await api.chat(t, historial, estadoChat());
        setRespuestas(r.respuestas);
        ref.current.respuestas = r.respuestas;
        ponerPregunta(r.pregunta, r.ya_preguntado);
        const cambiaron = r.anotaciones.length > 0 || r.quitadas.length > 0;
        if (cambiaron) agregar({ rol: "asistente", widget: "anotado", anotaciones: r.anotaciones, quitadas: r.quitadas, antes });
        // La pregunta va en su propio cuadro arriba de la barra; en el hilo queda el resto de la respuesta
        const visible = r.texto_visible ?? r.respuesta;
        agregar({ rol: "asistente", texto: visible || undefined, historial: r.respuesta, oculto: !visible, fuentes: r.fuentes, conIa: r.con_ia });
        if (r.simulacion) agregar({ rol: "asistente", widget: "simulacion", simulacion: r.simulacion });
        if (r.cambiar_anio && r.cambiar_anio !== ref.current.anio) ponerAnio(r.cambiar_anio);
        r.widgets.forEach((w) => agregar({ rol: "asistente", widget: w as Widget }));
        setEscribiendo(false);
        if (r.calcular) {
          setResultado(null);
          ref.current.resultado = null;
          await calcular();
        } else if (habia && (cambiaron || r.cambiar_anio)) {
          recalcularSiHabia(true);
        }
      } catch (e) {
        agregar({ rol: "asistente", texto: `No pude responder: ${(e as Error).message}` });
      } finally {
        setEscribiendo(false);
      }
    },
    [agregar, estadoChat, calcular, recalcularSiHabia, ponerAnio, ponerPregunta],
  );

  const deshacer = useCallback(
    (id: number) => {
      const m = ref.current.mensajes.find((x) => x.id === id);
      if (!m?.antes) return;
      const habia = !!ref.current.resultado;
      setRespuestas(m.antes);
      ref.current.respuestas = m.antes;
      actualizar(id, { deshecho: true });
      if (habia) recalcularSiHabia(true);
    },
    [actualizar, recalcularSiHabia],
  );

  const decidir = useCallback(
    (id: string, incluir: boolean, campo?: string | null, texto?: string) => {
      const s = ref.current;
      if (texto) setElecciones((x) => ({ ...x, [id]: texto }));
      const nuevas = s.filas.map((f) =>
        f.id === id ? { ...f, campo: incluir ? (campo ?? f.campo) : f.campo, tratamiento: incluir ? ("suma" as const) : ("informativo" as const) } : f,
      );
      const nuevasDecididas = { ...s.decididas, [id]: incluir };
      setFilas(nuevas);
      setDecididas(nuevasDecididas);
      ref.current = { ...ref.current, filas: nuevas, decididas: nuevasDecididas };
      const habia = !!s.resultado;
      if (habia && porRevisarDe(nuevas, nuevasDecididas).length === 0) recalcularSiHabia(true);
      else if (habia) {
        setResultado(null);
        ref.current.resultado = null;
      }
    },
    [recalcularSiHabia],
  );

  /** Vuelve a dejar pendiente un dato que ya se confirmó (botón "Cambiar"). */
  const cambiarDecision = useCallback(
    (id: string) => {
      const s = ref.current;
      const original = s.extraccion?.filas.find((f) => f.id === id);
      if (!original) return;
      const nuevas = s.filas.map((f) => (f.id === id ? original : f));
      const nuevasDecididas = { ...s.decididas };
      delete nuevasDecididas[id];
      setFilas(nuevas);
      setDecididas(nuevasDecididas);
      ref.current = { ...ref.current, filas: nuevas, decididas: nuevasDecididas };
      if (s.resultado) {
        setResultado(null);
        ref.current.resultado = null;
      }
    },
    [],
  );

  /** Cambio desde el selector del encabezado. */
  const cambiarAnio = useCallback(
    (a: number) => {
      if (a === ref.current.anio) return;
      const habia = !!ref.current.resultado;
      ponerAnio(a);
      const ex = ref.current.extraccion;
      if (ref.current.mensajes.length) {
        agregar({
          rol: "asistente",
          aviso: true,
          texto: `Ahora uso las reglas del año gravable ${a}.` + (ex?.anio && ex.anio !== a ? ` Tu exógena es del ${ex.anio}; para un cálculo correcto necesitas la del ${a}.` : ""),
        });
      }
      recalcularSiHabia(habia);
    },
    [agregar, ponerAnio, recalcularSiHabia],
  );

  const reiniciar = useCallback(() => {
    setExtraccion(null);
    setFilas([]);
    setDecididas({});
    setTrazaDocumento([]);
    setRespuestas(respuestasIniciales());
    setResultado(null);
    setEventosCalculo([]);
    setMensajes([]);
    conversacion.current = { pregunta: null, ya: [] };
    setPregunta(null);
    setElecciones({});
    ref.current = { ...ref.current, extraccion: null, filas: [], decididas: {}, respuestas: respuestasIniciales(), resultado: null, mensajes: [] };
  }, []);

  const porRevisar = useMemo(() => porRevisarDe(filas, decididas), [filas, decididas]);
  const hayDatos = tieneDatos(extraccion, respuestas);

  const valor: Sesion = {
    ruta, ir, anio, cambiarAnio, anios, modoLlm, extraccion, filas, decidir, cambiarDecision, elecciones, pregunta, cerrarPregunta, decididas, trazaDocumento, respuestas,
    resultado, eventosCalculo, calculando, errorCalculo, mensajes, escribiendo, enviar, deshacer,
    procesarArchivo, usarEjemplo, calcular, archivoPendiente, setArchivoPendiente, reiniciar, porRevisar, hayDatos,
  };
  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useSesion() {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSesion fuera del proveedor");
  return s;
}
