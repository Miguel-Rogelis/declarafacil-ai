import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { usarSinIa } from "./api";
import { useSesion } from "./estado";

/** Un caso completo para presentar: pregunta si declara, cuenta sus datos, calcula y ve el borrador. */
const PASOS: { tipo: "escribir" | "responder" | "resultado"; texto?: string; titulo: string }[] = [
  { tipo: "escribir", titulo: "Pregunta si tiene que declarar", texto: "Hola, ¿tengo que declarar renta?" },
  { tipo: "escribir", titulo: "Cuenta su salario y su retención", texto: "Gano 6 millones al mes como empleado y me retienen 250 mil cada mes" },
  { tipo: "escribir", titulo: "Dependientes y deducciones", texto: "Tengo una hija de 8 años y pago prepagada de 300 mil al mes" },
  { tipo: "escribir", titulo: "Su patrimonio", texto: "Tengo un apartamento de 230 millones y le debo 90 millones al banco por la hipoteca" },
  { tipo: "escribir", titulo: "Su cédula, para la fecha límite", texto: "Mi cédula termina en 37" },
  { tipo: "escribir", titulo: "Pide el cálculo", texto: "Calcula" },
  { tipo: "responder", titulo: "Responde lo que le falta", texto: "No, nada de eso" },
  { tipo: "resultado", titulo: "Ve su borrador del formulario 210" },
];

export interface EstadoDemo {
  activa: boolean;
  pausada: boolean;
  paso: number;
  total: number;
  titulo: string;
  escrito: string;
  terminada: boolean;
}

interface Demo extends EstadoDemo {
  iniciar: () => void;
  pausar: () => void;
  seguir: () => void;
  siguiente: () => void;
  tomarControl: () => void;
  cerrar: () => void;
}

const Ctx = createContext<Demo | null>(null);
const INICIAL: EstadoDemo = { activa: false, pausada: false, paso: 0, total: PASOS.length, titulo: "", escrito: "", terminada: false };

export function ProveedorDemo({ children }: { children: ReactNode }) {
  const sesion = useSesion();
  const s = useRef(sesion);
  s.current = sesion;
  const [estado, setEstado] = useState<EstadoDemo>(INICIAL);
  const control = useRef({ corriendo: false, cancelada: false, pausada: false, saltar: false });

  // Espera ms de tiempo corrido (no cuenta mientras está en pausa); «Siguiente» la corta
  const esperar = useCallback(async (ms: number) => {
    let quedan = ms;
    while (quedan > 0) {
      if (control.current.cancelada) throw new Error("cancelada");
      if (control.current.saltar) {
        control.current.saltar = false;
        return;
      }
      await new Promise((r) => setTimeout(r, 50));
      if (!control.current.pausada) quedan -= 50;
    }
  }, []);

  const libre = useCallback(async () => {
    await new Promise((r) => setTimeout(r, 150));
    while (s.current.escribiendo || s.current.calculando) {
      if (control.current.cancelada) throw new Error("cancelada");
      await new Promise((r) => setTimeout(r, 100));
    }
  }, []);

  const escribir = useCallback(
    async (texto: string) => {
      for (let i = 1; i <= texto.length; i++) {
        await esperar(i === 1 ? 250 : 28);
        setEstado((e) => ({ ...e, escrito: texto.slice(0, i) }));
      }
      await esperar(450);
      setEstado((e) => ({ ...e, escrito: "" }));
      await s.current.enviar(texto);
    },
    [esperar],
  );

  const correr = useCallback(async () => {
    if (control.current.corriendo) return;
    control.current = { corriendo: true, cancelada: false, pausada: false, saltar: false };
    usarSinIa(true);
    s.current.reiniciar();
    s.current.ir("declarar");
    try {
      for (let i = 0; i < PASOS.length; i++) {
        const p = PASOS[i];
        setEstado((e) => ({ ...e, activa: true, paso: i + 1, titulo: p.titulo, terminada: false }));
        await libre();
        if (p.tipo === "escribir" && p.texto) await escribir(p.texto);
        if (p.tipo === "responder" && p.texto && (s.current.pregunta || !s.current.resultado)) await escribir(p.texto);
        if (p.tipo === "resultado") s.current.ir("resultado");
        await libre();
        await esperar(i === PASOS.length - 1 ? 400 : 1800);
      }
      setEstado((e) => ({ ...e, terminada: true, titulo: "Fin de la demo" }));
    } catch {
      /* la cancelaron: «Tomar el control» o «Cerrar» */
    } finally {
      control.current.corriendo = false;
      usarSinIa(false);
    }
  }, [escribir, esperar, libre]);

  const valor: Demo = {
    ...estado,
    iniciar: () => void correr(),
    pausar: () => {
      control.current.pausada = true;
      setEstado((e) => ({ ...e, pausada: true }));
    },
    seguir: () => {
      control.current.pausada = false;
      setEstado((e) => ({ ...e, pausada: false }));
    },
    siguiente: () => {
      control.current.saltar = true;
      control.current.pausada = false;
      setEstado((e) => ({ ...e, pausada: false }));
    },
    tomarControl: () => {
      control.current.cancelada = true;
      usarSinIa(false);
      setEstado(INICIAL);
      s.current.ir("declarar");
      window.setTimeout(() => document.getElementById("mensaje")?.focus(), 80);
    },
    cerrar: () => {
      control.current.cancelada = true;
      usarSinIa(false);
      setEstado(INICIAL);
    },
  };

  // Si la persona cambia de pestaña o recarga, la demo no queda corriendo sin control
  useEffect(() => () => usarSinIa(false), []);

  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useDemo() {
  const d = useContext(Ctx);
  if (!d) throw new Error("useDemo fuera del proveedor");
  return d;
}
