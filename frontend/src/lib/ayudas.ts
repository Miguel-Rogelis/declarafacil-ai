import type { Liquidacion } from "./api";

/** Enlaces oficiales que usa la app (solo la DIAN). */
export const DIAN = {
  muisca: "https://muisca.dian.gov.co/WebIdentidadLogin/",
  facturas: "https://catalogo-vpfe.dian.gov.co/User/Login",
  portal: "https://www.dian.gov.co",
};

export interface Documento {
  clave: string;
  nombre: string;
  donde: string;
  enlace?: string;
}

type Datos = Record<string, Record<string, unknown> | undefined>;
const num = (d: Datos, ruta: string) => {
  const [a, b] = ruta.split(".");
  const v = d[a]?.[b];
  return typeof v === "number" ? v : 0;
};

/** Los documentos que debe tener a mano, según lo que trae su declaración. */
export function documentosDe(datos: Record<string, unknown>): Documento[] {
  const d = datos as Datos;
  const bienes = ((d.patrimonio?.bienes as { concepto: string }[] | undefined) ?? []).map((b) => b.concepto.toLowerCase());
  const tiene = (...p: string[]) => bienes.some((b) => p.some((x) => b.includes(x)));
  const salida: Documento[] = [
    { clave: "exogena", nombre: "Reporte de información exógena", donde: "En MUISCA, menú «Consultar información exógena» del año.", enlace: DIAN.muisca },
    { clave: "rut", nombre: "RUT actualizado", donde: "En MUISCA; si cambiaste de correo o de actividad, actualízalo antes de declarar.", enlace: DIAN.muisca },
  ];
  const poner = (cond: unknown, doc: Documento) => cond && salida.push(doc);
  poner(num(d, "laboral.salarios_y_pagos_laborales"), { clave: "220", nombre: "Certificado de ingresos y retenciones (formulario 220)", donde: "Te lo da tu empleador: pídelo a nómina o descárgalo de su portal de empleados." });
  poner(num(d, "independiente.honorarios_y_servicios"), { clave: "honorarios", nombre: "Certificados de retención de quienes te pagaron", donde: "Cada cliente que te retuvo te da el suyo; pídelo por correo." });
  poner(num(d, "independiente.aportes_obligatorios_salud") || num(d, "independiente.aportes_obligatorios_pension"), { clave: "pila", nombre: "Planillas PILA pagadas", donde: "En el operador donde pagas (Mi Planilla, SOI, Aportes en Línea…), sección de planillas pagadas." });
  poner(num(d, "pensiones.pensiones_nacionales"), { clave: "pension", nombre: "Certificado de ingresos de tu pensión", donde: "Te lo da tu fondo de pensiones o Colpensiones en su portal." });
  poner(num(d, "capital.rendimientos_financieros") || tiene("cdt", "ahorro", "cuenta", "inversion", "banco"), { clave: "banco", nombre: "Certificado tributario de cada banco", donde: "En la banca virtual, opción «Certificados» o «Certificado tributario»: trae saldos al 31 de diciembre e intereses." });
  poner(num(d, "capital.arrendamientos"), { clave: "arriendo", nombre: "Soportes de los arriendos y sus gastos", donde: "Contratos de arriendo, recibo del predial, administración y facturas de mantenimiento." });
  poner(num(d, "deducciones.intereses_vivienda"), { clave: "vivienda", nombre: "Certificado de intereses del crédito de vivienda", donde: "Lo da tu banco en la banca virtual (certificado tributario del crédito)." });
  poner(num(d, "deducciones.medicina_prepagada"), { clave: "prepagada", nombre: "Certificado de la medicina prepagada", donde: "En el portal de tu prepagada o pídelo a servicio al cliente." });
  poner(num(d, "deducciones.intereses_icetex"), { clave: "icetex", nombre: "Certificado de intereses del ICETEX", donde: "En el portal del ICETEX, sección de certificados tributarios." });
  poner(num(d, "deducciones.aportes_voluntarios_afc_fpv"), { clave: "afc", nombre: "Certificado de aportes voluntarios o AFC", donde: "Te lo da el fondo de pensiones o el banco de la cuenta AFC." });
  poner(num(d, "deducciones.compras_factura_electronica"), { clave: "factura", nombre: "Facturas electrónicas a tu nombre", donde: "En el portal de facturación de la DIAN ves todas, con su total del año.", enlace: DIAN.facturas });
  poner(num(d, "deducciones.dependientes"), { clave: "dependientes", nombre: "Soportes de tus dependientes", donde: "Registro civil de tus hijos; certificado de estudio si tienen entre 18 y 23 años; para padres, prueba de que dependen de ti." });
  poner(tiene("carro", "moto", "vehiculo", "vehículo", "camioneta"), { clave: "vehiculo", nombre: "Factura o avalúo de tu vehículo", donde: "La factura de compra, o el avalúo del impuesto vehicular del año." });
  poner(tiene("casa", "apartamento", "lote", "finca", "local"), { clave: "predial", nombre: "Recibo del impuesto predial", donde: "Trae el avalúo catastral de cada inmueble; lo descargas en la página de tu alcaldía." });
  poner(tiene("exterior", "cripto"), { clave: "exterior", nombre: "Extractos de cuentas afuera o de cripto al 31 de diciembre", donde: "Descárgalos de la plataforma o el banco; se pasan a pesos con la TRM del 31 de diciembre." });
  return salida;
}

/** Un evento de calendario (.ics) con la fecha límite y un aviso tres días antes. */
export function archivoCalendario(liq: Liquidacion): Blob | null {
  if (!liq.vencimiento) return null;
  const dia = liq.vencimiento.fecha.replaceAll("-", "");
  const siguiente = new Date(liq.vencimiento.fecha + "T12:00:00");
  siguiente.setDate(siguiente.getDate() + 1);
  const fin = siguiente.toISOString().slice(0, 10).replaceAll("-", "");
  const ahora = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+/, "");
  const texto = (t: string) => t.replace(/[,;\\]/g, (c) => "\\" + c).replace(/\n/g, "\\n");
  const lineas = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//DeclaraFacil//ES",
    "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT",
    `UID:declarafacil-${liq.anio_gravable}-${dia}@declarafacil`,
    `DTSTAMP:${ahora}`,
    `DTSTART;VALUE=DATE:${dia}`,
    `DTEND;VALUE=DATE:${fin}`,
    `SUMMARY:${texto(`Último día para declarar renta (año gravable ${liq.anio_gravable})`)}`,
    `DESCRIPTION:${texto(`Presenta tu declaración en MUISCA: ${DIAN.muisca}\nSi te pasas de la fecha hay sanción: mínimo 10 UVT y sube cada mes de retraso.`)}`,
    `URL:${DIAN.muisca}`,
    "BEGIN:VALARM",
    "ACTION:DISPLAY",
    "DESCRIPTION:Faltan 3 días para declarar renta",
    "TRIGGER:-P3D",
    "END:VALARM",
    "END:VEVENT",
    "END:VCALENDAR",
  ];
  return new Blob([lineas.join("\r\n")], { type: "text/calendar;charset=utf-8" });
}

export function descargar(blob: Blob, nombre: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
