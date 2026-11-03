import { useEffect, useState, type KeyboardEvent, type ReactNode } from "react";
import { aNumero, pesos } from "../lib/formato";

/** Símbolo d-chulo: la d de DeclaraFácil escrita de un trazo que remata en chulo.
 *  `chico` usa el corte para tamaños pequeños (trazo más grueso), el que va en el encabezado y el favicon. */
export function Marca({ chico = false }: { chico?: boolean }) {
  return (
    <svg viewBox="0 0 256 256" aria-hidden="true">
      <g transform={chico ? "translate(-30.7 -18.7) scale(1.146)" : "translate(-22.5 -11.1) scale(1.087)"}>
        <path
          d="M184 124 C 166 110, 148 104, 126 104 C 94 104, 66 126, 66 157 C 66 188, 92 208, 120 208 C 128 208, 136 205, 142 200 L 162 220 L 211 36"
          fill="none"
          stroke="var(--sello)"
          strokeWidth={chico ? 38 : 30}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
    </svg>
  );
}

/** El símbolo usado como letra: recortado a su caja para que se siente en la línea base junto al texto.
 *  Usa el corte grueso, que a tamaño de texto se lee mejor. */
export function LetraD({ className = "" }: { className?: string }) {
  return (
    <svg className={`letra-d ${className}`.trim()} viewBox="47 17 183 222" aria-hidden="true">
      <path
        d="M184 124 C 166 110, 148 104, 126 104 C 94 104, 66 126, 66 157 C 66 188, 92 208, 120 208 C 128 208, 136 205, 142 200 L 162 220 L 211 36"
        fill="none"
        stroke="currentColor"
        strokeWidth={38}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Candado() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="4" y="10" width="16" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

/** Campo de pesos con separador de miles mientras se escribe. */
export function CampoPesos({ id, etiqueta, ayuda, valor, onCambio, encontrado }: {
  id: string;
  etiqueta: string;
  ayuda?: ReactNode;
  valor: number;
  onCambio: (v: number) => void;
  encontrado?: number;
}) {
  const [texto, setTexto] = useState(valor ? new Intl.NumberFormat("es-CO").format(valor) : "");
  useEffect(() => {
    setTexto(valor ? new Intl.NumberFormat("es-CO").format(valor) : "");
  }, [valor]);
  return (
    <div className="campo">
      <label htmlFor={id}>{etiqueta}</label>
      {encontrado ? <span className="dato-encontrado">Ya está en tu exógena: {pesos(encontrado)}. Escribe solo lo que falte.</span> : null}
      <div className="entrada-pesos">
        <input
          id={id}
          className="entrada"
          inputMode="numeric"
          autoComplete="off"
          placeholder="0"
          value={texto}
          onChange={(e) => {
            const n = aNumero(e.target.value);
            setTexto(n ? new Intl.NumberFormat("es-CO").format(n) : "");
            onCambio(n);
          }}
        />
      </div>
      {ayuda ? <span className="ayuda">{ayuda}</span> : null}
    </div>
  );
}

export function Contador({ valor, onCambio, min = 0, max = 10, etiqueta }: { valor: number; onCambio: (v: number) => void; min?: number; max?: number; etiqueta: string }) {
  return (
    <div className="contador" role="group" aria-label={etiqueta}>
      <button type="button" aria-label="Quitar uno" onClick={() => onCambio(Math.max(min, valor - 1))}>−</button>
      <output aria-live="polite">{valor}</output>
      <button type="button" aria-label="Agregar uno" onClick={() => onCambio(Math.min(max, valor + 1))}>+</button>
    </div>
  );
}

export function Segmentado<T extends string | number>({ opciones, valor, onCambio, etiqueta }: {
  opciones: { valor: T; texto: string }[];
  valor: T | null;
  onCambio: (v: T) => void;
  etiqueta: string;
}) {
  return (
    <div className="segmentado" role="group" aria-label={etiqueta}>
      {opciones.map((o) => (
        <button key={String(o.valor)} type="button" aria-pressed={valor === o.valor} onClick={() => onCambio(o.valor)}>
          {o.texto}
        </button>
      ))}
    </div>
  );
}

/** Pestañas accesibles: flechas, Inicio y Fin mueven la selección; solo la elegida entra en el orden de Tab. */
export function Pestanas<T extends string>({ opciones, valor, onCambio, etiqueta, idPanel, pegadas = false, className = "" }: {
  opciones: { valor: T; texto: string }[];
  valor: T;
  onCambio: (v: T) => void;
  etiqueta: string;
  idPanel: string;
  pegadas?: boolean;
  className?: string;
}) {
  const mover = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = opciones.findIndex((o) => o.valor === valor);
    const destino = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: opciones.length - 1 }[e.key];
    if (destino === undefined) return;
    e.preventDefault();
    const nueva = opciones[(destino + opciones.length) % opciones.length];
    onCambio(nueva.valor);
    e.currentTarget.querySelector<HTMLButtonElement>(`#pestana-${idPanel}-${nueva.valor}`)?.focus();
  };
  return (
    <div className={`pestanas${pegadas ? " pegadas" : ""} ${className}`} role="tablist" aria-label={etiqueta} onKeyDown={mover}>
      {opciones.map((o) => (
        <button
          key={o.valor}
          id={`pestana-${idPanel}-${o.valor}`}
          type="button"
          role="tab"
          aria-selected={o.valor === valor}
          aria-controls={idPanel}
          tabIndex={o.valor === valor ? 0 : -1}
          onClick={() => onCambio(o.valor)}
        >
          {o.texto}
        </button>
      ))}
    </div>
  );
}
