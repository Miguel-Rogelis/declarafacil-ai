import { AnimatePresence, motion } from "motion/react";
import { useEffect, useId, useState } from "react";
import { api } from "../lib/api";
import { useSesion } from "../lib/estado";
import { pesos } from "../lib/formato";

const CURVA = [0.23, 1, 0.32, 1] as const;

type Topes = { patrimonio_bruto: number; ingresos_brutos: number; consumos_tarjeta_credito: number; compras_consumos: number; consignaciones_depositos_inversiones: number };

const leer = (t: string) => Number(t.replace(/\D/g, "")) || 0;
const mostrar = (n: number) => (n ? n.toLocaleString("es-CO") : "");

function CampoPesos({ nombre, etiqueta, ayuda, valor, onCambio }: { nombre: string; etiqueta: string; ayuda: string; valor: number; onCambio: (n: number) => void }) {
  const id = useId();
  return (
    <div className="campo-debo">
      <label htmlFor={id}>{etiqueta}</label>
      <div className="entrada-pesos">
        <span aria-hidden="true">$</span>
        <input id={id} name={nombre} inputMode="numeric" enterKeyHint="next" autoComplete="off" placeholder="0" value={mostrar(valor)} onChange={(e) => onCambio(leer(e.target.value))} aria-describedby={`${id}-a`} />
      </div>
      <span id={`${id}-a`} className="ayuda">{ayuda}</span>
    </div>
  );
}

/** «¿Tengo que declarar?» en cuatro cifras, con los topes del año elegido (sin IA, en el navegador). */
export function DeboDeclarar() {
  const { anio, ir } = useSesion();
  const [uvt, setUvt] = useState(0);
  const [topes, setTopes] = useState<Topes | null>(null);
  const [v, setV] = useState({ ingresos: 0, patrimonio: 0, tarjeta: 0, compras: 0 });
  const [iva, setIva] = useState(false);

  useEffect(() => {
    let vivo = true;
    api.reglas(anio).then((r) => {
      if (!vivo) return;
      setUvt(Number(r.uvt) || 0);
      setTopes(r.topes_obligacion_uvt as Topes);
    }).catch(() => {});
    return () => {
      vivo = false;
    };
  }, [anio]);

  const lim = topes && uvt
    ? { patrimonio: topes.patrimonio_bruto * uvt, ingresos: topes.ingresos_brutos * uvt, tarjeta: topes.consumos_tarjeta_credito * uvt, compras: Math.min(topes.compras_consumos, topes.consignaciones_depositos_inversiones) * uvt }
    : null;
  const razones = lim
    ? [
        v.ingresos >= lim.ingresos && `tus ingresos llegan al tope de ${pesos(lim.ingresos)}`,
        v.patrimonio > lim.patrimonio && `tu patrimonio pasa de ${pesos(lim.patrimonio)}`,
        v.tarjeta >= lim.tarjeta && `tus consumos con tarjeta llegan a ${pesos(lim.tarjeta)}`,
        v.compras >= lim.compras && `tus compras o consignaciones llegan a ${pesos(lim.compras)}`,
        iva && "eres responsable de IVA",
      ].filter(Boolean) as string[]
    : [];
  const algo = v.ingresos + v.patrimonio + v.tarjeta + v.compras > 0 || iva;
  const veredicto = !lim || !algo ? "vacio" : razones.length ? "si" : "no";

  return (
    <div className="debo-declarar">
      <div className="debo-campos">
        <CampoPesos nombre="ingresos" etiqueta={`¿Cuánto recibiste en ${anio}?`} ayuda="Salario, honorarios, arriendos, pensión: todo junto." valor={v.ingresos} onCambio={(n) => setV({ ...v, ingresos: n })} />
        <CampoPesos nombre="patrimonio" etiqueta={`¿Cuánto valía lo tuyo al 31 de diciembre?`} ayuda="Casa, carro, ahorros e inversiones, sin restar deudas." valor={v.patrimonio} onCambio={(n) => setV({ ...v, patrimonio: n })} />
        <CampoPesos nombre="tarjeta" etiqueta="¿Cuánto pagaste con tarjeta de crédito?" ayuda="Lo que consumiste en el año con tus tarjetas." valor={v.tarjeta} onCambio={(n) => setV({ ...v, tarjeta: n })} />
        <CampoPesos nombre="compras" etiqueta="¿Cuánto compraste o consignaste en tus cuentas?" ayuda="Pon el mayor de los dos: compras del año o plata que entró a tus cuentas." valor={v.compras} onCambio={(n) => setV({ ...v, compras: n })} />
        <label className="check-iva">
          <input type="checkbox" name="iva" checked={iva} onChange={(e) => setIva(e.target.checked)} />
          Soy responsable de IVA (lo dice mi RUT)
        </label>
      </div>

      <div className={`debo-veredicto ${veredicto}`} aria-live="polite">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={veredicto + razones.length}
            initial={{ opacity: 0, y: 8, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -6, filter: "blur(4px)" }}
            transition={{ duration: 0.22, ease: CURVA }}
          >
            {veredicto === "vacio" ? (
              <>
                <span className="debo-etiqueta">Año gravable {anio}</span>
                <p className="debo-titulo">Escribe tus cifras y te digo al instante.</p>
                <p className="suave">{lim ? `Los topes de ${anio}: ingresos o consumos desde ${pesos(lim.ingresos)}, o patrimonio de más de ${pesos(lim.patrimonio)}.` : "Cargando los topes del año…"}</p>
              </>
            ) : veredicto === "si" ? (
              <>
                <span className="debo-etiqueta">Sí, tienes que declarar</span>
                <p className="debo-titulo">Porque {razones.length > 1 ? razones.slice(0, -1).join(", ") + " y " + razones.at(-1) : razones[0]}.</p>
                <p className="suave">Declarar no siempre es pagar: muchas personas quedan en cero o con saldo a favor.</p>
              </>
            ) : (
              <>
                <span className="debo-etiqueta">No tienes que declarar por {anio}</span>
                <p className="debo-titulo">Ninguna de tus cifras llega a los topes.</p>
                <p className="suave">Igual puedes declarar si te retuvieron y quieres pedir esa plata de vuelta.</p>
              </>
            )}
          </motion.div>
        </AnimatePresence>
        <button className="boton" onClick={() => ir("declarar")}>{veredicto === "si" ? "Empezar mi declaración" : "Hablar con el agente"}</button>
      </div>
    </div>
  );
}
