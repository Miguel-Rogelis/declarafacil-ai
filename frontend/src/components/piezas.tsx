import { useEffect, useState, type ReactNode } from "react";
import { aNumero, pesos } from "../lib/formato";

export function Marca() {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="28" fill="none" stroke="var(--sello)" strokeWidth="5" />
      <circle cx="32" cy="32" r="19" fill="none" stroke="var(--sello)" strokeWidth="2.5" />
      <path d="M23 33l6 6 12-14" fill="none" stroke="var(--sello)" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
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
