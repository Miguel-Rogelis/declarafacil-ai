import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, respuestasIniciales, type AnioDisponible, type EventoAgente, type Extraccion, type Fila, type Respuestas, type ResultadoLiquidacion } from "./api";

export type Ruta = "inicio" | "declarar" | "resultado" | "configuracion";

interface Sesion {
  ruta: Ruta;
  ir: (r: Ruta) => void;
  anio: number;
  setAnio: (a: number) => void;
  anios: AnioDisponible[];
  modoLlm: string;
  extraccion: Extraccion | null;
  setExtraccion: (e: Extraccion | null) => void;
  filas: Fila[];
  setFilas: (f: Fila[]) => void;
  trazaDocumento: EventoAgente[];
  setTrazaDocumento: (t: EventoAgente[]) => void;
  respuestas: Respuestas;
  setRespuestas: (fn: (r: Respuestas) => Respuestas) => void;
  resultado: ResultadoLiquidacion | null;
  setResultado: (r: ResultadoLiquidacion | null) => void;
  archivoPendiente: File | null;
  setArchivoPendiente: (f: File | null) => void;
  reiniciar: () => void;
}

const Ctx = createContext<Sesion | null>(null);

const leerRuta = (): Ruta => {
  const h = window.location.hash.replace("#/", "");
  return (["inicio", "declarar", "resultado", "configuracion"] as Ruta[]).includes(h as Ruta) ? (h as Ruta) : "inicio";
};

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [ruta, setRuta] = useState<Ruta>(leerRuta);
  const [anio, setAnio] = useState(2025);
  const [anios, setAnios] = useState<AnioDisponible[]>([]);
  const [modoLlm, setModoLlm] = useState("");
  const [extraccion, setExtraccion] = useState<Extraccion | null>(null);
  const [filas, setFilas] = useState<Fila[]>([]);
  const [trazaDocumento, setTrazaDocumento] = useState<EventoAgente[]>([]);
  const [respuestas, setRespuestasState] = useState<Respuestas>(respuestasIniciales);
  const [resultado, setResultado] = useState<ResultadoLiquidacion | null>(null);
  const [archivoPendiente, setArchivoPendiente] = useState<File | null>(null);

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

  const setRespuestas = useCallback((fn: (r: Respuestas) => Respuestas) => setRespuestasState(fn), []);

  const reiniciar = useCallback(() => {
    setExtraccion(null);
    setFilas([]);
    setTrazaDocumento([]);
    setRespuestasState(respuestasIniciales());
    setResultado(null);
  }, []);

  const valor = useMemo(
    () => ({
      ruta, ir, anio, setAnio, anios, modoLlm, extraccion, setExtraccion, filas, setFilas, trazaDocumento, setTrazaDocumento,
      respuestas, setRespuestas, resultado, setResultado, archivoPendiente, setArchivoPendiente, reiniciar,
    }),
    [ruta, ir, anio, anios, modoLlm, extraccion, filas, trazaDocumento, respuestas, setRespuestas, resultado, archivoPendiente, reiniciar],
  );
  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useSesion() {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSesion fuera del proveedor");
  return s;
}
