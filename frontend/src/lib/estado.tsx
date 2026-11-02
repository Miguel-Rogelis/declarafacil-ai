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
  type Respuestas,
  type ResultadoLiquidacion,
} from "./api";

export type Ruta = "inicio" | "declarar" | "resultado" | "configuracion";

export type Widget = "subir_exogena" | "como_descargar" | "revisar" | "calcular" | "traza_documento" | "traza_calculo" | "resultado" | "anotado";

export interface Mensaje {
  id: number;
  rol: "usuario" | "asistente";
  texto?: string;
  widget?: Widget;
  anotaciones?: Anotacion[];
  antes?: { respuestas: Respuestas; temas: string[] };
  deshecho?: boolean;
  eventos?: EventoAgente[];
  fuentes?: string[];
  conIa?: boolean;
  aviso?: boolean;
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
  decidir: (id: string, incluir: boolean, campo?: string | null) => void;
  decididas: Record<string, boolean>;
  trazaDocumento: EventoAgente[];
  respuestas: Respuestas;
  temas: string[];
  resultado: ResultadoLiquidacion | null;
  setResultado: (r: ResultadoLiquidacion | null) => void;
  eventosCalculo: EventoAgente[];
  calculando: boolean;
  errorCalculo: string;
  mensajes: Mensaje[];
  sugerencias: string[];
  escribiendo: boolean;
  enviar: (texto: string) => Promise<void>;
  deshacer: (id: number) => void;
  procesarArchivo: (f: File) => Promise<void>;
  usarEjemplo: () => Promise<void>;
  calcular: () => Promise<void>;
  archivoPendiente: File | null;
  setArchivoPendiente: (f: File | null) => void;
  reiniciar: () => void;
  porRevisar: Fila[];
}

const Ctx = createContext<Sesion | null>(null);

const RUTAS: Ruta[] = ["inicio", "declarar", "resultado", "configuracion"];
const leerRuta = (): Ruta => {
  const h = window.location.hash.replace("#/", "") as Ruta;
  return RUTAS.includes(h) ? h : "inicio";
};

const BIENVENIDA: Mensaje = {
  id: 0,
  rol: "asistente",
  texto:
    "Hola, soy DeclaraFácil. Pregúntame lo que quieras sobre la declaración de renta, por básico que te parezca, o armemos la tuya paso a paso. ¿Por dónde empezamos?",
};
const SUGERENCIAS_INICIALES = ["¿Tengo que declarar renta?", "Quiero hacer mi declaración", "¿Qué es la exógena?", "Tengo mi exógena"];

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
  const [temas, setTemas] = useState<string[]>([]);
  const [resultado, setResultado] = useState<ResultadoLiquidacion | null>(null);
  const [eventosCalculo, setEventosCalculo] = useState<EventoAgente[]>([]);
  const [calculando, setCalculando] = useState(false);
  const [errorCalculo, setErrorCalculo] = useState("");
  const [mensajes, setMensajes] = useState<Mensaje[]>([BIENVENIDA]);
  const [sugerencias, setSugerencias] = useState<string[]>(SUGERENCIAS_INICIALES);
  const [escribiendo, setEscribiendo] = useState(false);
  const [archivoPendiente, setArchivoPendiente] = useState<File | null>(null);
  const contador = useRef(1);

  // Referencias para leer siempre el estado más reciente dentro de callbacks asíncronos
  const ref = useRef({ anio, extraccion, filas, decididas, respuestas, temas, resultado, ruta, mensajes });
  ref.current = { anio, extraccion, filas, decididas, respuestas, temas, resultado, ruta, mensajes };

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

  const porRevisarDe = (f: Fila[], d: Record<string, boolean>) =>
    f.filter((x) => (x.tratamiento === "revisar" || x.origen_mapeo === "ia") && !(x.id in d));

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
      respuestas: s.respuestas,
      temas_cubiertos: s.temas,
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

  /** Siguiente pregunta guiada, sin IA (después de subir la exógena o confirmar datos). */
  const preguntarSiguiente = useCallback(async () => {
    try {
      const s = await api.siguiente(estadoChat());
      if (s.texto) agregar({ rol: "asistente", texto: s.texto });
      s.widgets.forEach((w) => agregar({ rol: "asistente", widget: w as Widget }));
      setSugerencias(s.sugerencias);
    } catch {
      /* sin conexión: el usuario puede seguir escribiendo */
    }
  }, [agregar, estadoChat]);

  const calcular = useCallback(async () => {
    const s = ref.current;
    setCalculando(true);
    setErrorCalculo("");
    setEventosCalculo([]);
    const idTraza = agregar({ rol: "asistente", widget: "traza_calculo", eventos: [] });
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
          actualizar(idTraza, { eventos: [...acumulado] });
        },
        onResultado: (r) => {
          setResultado(r);
          agregar({ rol: "asistente", widget: "resultado" });
          setSugerencias(["¿Por qué me sale ese valor?", "¿Qué es el anticipo?", "¿Cómo lo presento en la DIAN?"]);
        },
        onError: (m) => {
          setErrorCalculo(m);
          agregar({ rol: "asistente", texto: `No pude calcular: ${m}` });
        },
      },
    );
    setCalculando(false);
  }, [agregar, actualizar]);

  const procesarArchivo = useCallback(
    async (archivo: File) => {
      agregar({ rol: "usuario", texto: `📎 ${archivo.name}` });
      const idTraza = agregar({ rol: "asistente", widget: "traza_documento", eventos: [] });
      setSugerencias([]);
      const acumulado: EventoAgente[] = [];
      let ok = false;
      await analizarDocumento(archivo, ref.current.anio, {
        onAgente: (e) => {
          acumulado.push(e);
          actualizar(idTraza, { eventos: [...acumulado] });
        },
        onResultado: (r) => {
          ok = true;
          setExtraccion(r.extraccion);
          setFilas(r.extraccion.filas);
          setDecididas({});
          setTrazaDocumento(r.traza);
          setResultado(null);
          setRespuestas((x) => ({ ...x, ultimos_dos_digitos_nit: x.ultimos_dos_digitos_nit ?? r.extraccion.ultimos_dos_digitos_nit }));
          setTemas((t) => [...new Set([...t, "exogena"])]);
          const total = r.extraccion.filas.length;
          const suma = r.extraccion.filas.filter((f) => f.tratamiento === "suma").length;
          const rev = r.extraccion.filas.filter((f) => f.tratamiento === "revisar").length;
          const partes = [`Leí ${total} datos de tu exógena: ubiqué ${suma} en tu declaración${rev ? ` y ${rev} necesitan que los confirmes` : ""}.`];
          partes.push(`Antes de usar IA quité ${r.extraccion.datos_enmascarados} datos personales.`);
          if (r.extraccion.anio && r.extraccion.anio !== ref.current.anio) {
            partes.push(`Ojo: el archivo es del año ${r.extraccion.anio} y tienes elegido el ${ref.current.anio}. Cambia el año arriba si lo necesitas.`);
          }
          agregar({ rol: "asistente", texto: partes.join(" ") });
        },
        onError: (m) => {
          agregar({ rol: "asistente", texto: `No pude leer el archivo: ${m}` });
          agregar({ rol: "asistente", widget: "subir_exogena" });
        },
      });
      if (ok) {
        // esperar a que React aplique el estado nuevo antes de pedir la siguiente pregunta
        setTimeout(() => void preguntarSiguiente(), 50);
      }
    },
    [agregar, actualizar, preguntarSiguiente],
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
      const historial = s.mensajes.filter((m) => m.texto).slice(-10).map((m) => ({ rol: m.rol, texto: m.texto! }));
      agregar({ rol: "usuario", texto: t });
      setSugerencias([]);
      setEscribiendo(true);
      try {
        const antes = { respuestas: s.respuestas, temas: s.temas };
        const r = await api.chat(t, historial, estadoChat());
        setRespuestas(r.respuestas);
        setTemas(r.temas_cubiertos);
        if (r.anotaciones.length) agregar({ rol: "asistente", widget: "anotado", anotaciones: r.anotaciones, antes });
        agregar({ rol: "asistente", texto: r.respuesta, fuentes: r.fuentes, conIa: r.con_ia });
        if (r.cambiar_anio && r.cambiar_anio !== ref.current.anio) cambiarAnioInterno(r.cambiar_anio);
        // No repetir un widget que ya está a la vista en los últimos mensajes
        const recientes = new Set(ref.current.mensajes.slice(-6).map((m) => m.widget));
        r.widgets.filter((w) => !recientes.has(w as Widget)).forEach((w) => agregar({ rol: "asistente", widget: w as Widget }));
        setSugerencias(r.sugerencias);
        if (r.anotaciones.length && ref.current.resultado) {
          setResultado(null);
          agregar({ rol: "asistente", texto: "Como cambiaron tus datos, vuelve a calcular para ver el resultado actualizado.", aviso: true });
          agregar({ rol: "asistente", widget: "calcular" });
        }
      } catch (e) {
        agregar({ rol: "asistente", texto: `No pude responder: ${(e as Error).message}` });
      } finally {
        setEscribiendo(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [agregar, estadoChat],
  );

  const deshacer = useCallback(
    (id: number) => {
      const m = ref.current.mensajes.find((x) => x.id === id);
      if (!m?.antes) return;
      setRespuestas(m.antes.respuestas);
      setTemas(m.antes.temas);
      actualizar(id, { deshecho: true });
    },
    [actualizar],
  );

  const decidir = useCallback(
    (id: string, incluir: boolean, campo?: string | null) => {
      const s = ref.current;
      const nuevas = s.filas.map((f) =>
        f.id === id ? { ...f, campo: incluir ? (campo ?? f.campo) : f.campo, tratamiento: incluir ? ("suma" as const) : ("informativo" as const) } : f,
      );
      const nuevasDecididas = { ...s.decididas, [id]: incluir };
      setFilas(nuevas);
      setDecididas(nuevasDecididas);
      setResultado(null);
      if (porRevisarDe(nuevas, nuevasDecididas).length === 0) {
        ref.current = { ...ref.current, filas: nuevas, decididas: nuevasDecididas };
        void preguntarSiguiente();
      }
    },
    [preguntarSiguiente],
  );

  const cambiarAnioInterno = (a: number) => {
    setAnio(a);
    setResultado(null);
    const ex = ref.current.extraccion;
    agregar({
      rol: "asistente",
      aviso: true,
      texto:
        `Ahora uso las reglas del año gravable ${a}.` +
        (ex?.anio && ex.anio !== a ? ` Tu exógena es del ${ex.anio}; para un cálculo correcto sube la del ${a}.` : ""),
    });
  };
  const cambiarAnio = useCallback((a: number) => {
    if (a !== ref.current.anio) cambiarAnioInterno(a);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reiniciar = useCallback(() => {
    setExtraccion(null);
    setFilas([]);
    setDecididas({});
    setTrazaDocumento([]);
    setRespuestas(respuestasIniciales());
    setTemas([]);
    setResultado(null);
    setEventosCalculo([]);
    setMensajes([BIENVENIDA]);
    setSugerencias(SUGERENCIAS_INICIALES);
  }, []);

  const porRevisar = useMemo(() => porRevisarDe(filas, decididas), [filas, decididas]);

  const valor: Sesion = {
    ruta, ir, anio, cambiarAnio, anios, modoLlm, extraccion, filas, decidir, decididas, trazaDocumento, respuestas, temas,
    resultado, setResultado, eventosCalculo, calculando, errorCalculo, mensajes, sugerencias, escribiendo, enviar, deshacer,
    procesarArchivo, usarEjemplo, calcular, archivoPendiente, setArchivoPendiente, reiniciar, porRevisar,
  };
  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useSesion() {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSesion fuera del proveedor");
  return s;
}
