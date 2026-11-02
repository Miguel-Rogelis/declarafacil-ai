"""Genera los archivos de reglas de los años gravables 2021 a 2024 a partir de ag2025.json.

Diferencias que se aplican:
- AG 2021 y 2022 (antes de la Ley 2277 de 2022): límite de exentas y deducciones
  de 5.040 UVT; renta exenta del 25 % hasta 2.880 UVT al año; sin deducción de 72 UVT
  por dependiente ni 1 % de factura electrónica; dividendos con tabla propia (10 %
  sobre lo que pase de 300 UVT); ganancias ocasionales al 10 % y exenciones
  anteriores (arts. 303-1, 307 y 311-1 antes de la reforma).
- AG 2023 y 2024: mismas reglas de la Ley 2277 que 2025, con su propia UVT y su
  componente inflacionario.

Calendarios de vencimiento:
- 2022 y 2023 (Decretos 1778 de 2021 y 2487 de 2022): dos dígitos por día hábil,
  del 9 de agosto al 19 de octubre.
- 2024 en adelante (Decreto 2229 de 2023): agosto del 7.º al 19.º día hábil,
  septiembre del 1.º al 20.º, octubre del 1.º al 17.º.

Uso: python scripts/generar_reglas_historicas.py
"""

import json
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data" / "reglas"


def _lunes_siguiente(d: date) -> date:
    """Ley Emiliani: el festivo se corre al lunes siguiente si no cae en lunes."""
    return d if d.weekday() == 0 else d + timedelta(days=7 - d.weekday())


def festivos_ago_oct(anio: int) -> set[date]:
    return {
        date(anio, 8, 7),  # Batalla de Boyacá (fija)
        _lunes_siguiente(date(anio, 8, 15)),  # Asunción de la Virgen
        _lunes_siguiente(date(anio, 10, 12)),  # Día de la Raza
    }


def habiles(anio: int, mes: int) -> list[date]:
    fest = festivos_ago_oct(anio)
    d, salida = date(anio, mes, 1), []
    while d.month == mes:
        if d.weekday() < 5 and d not in fest:
            salida.append(d)
        d += timedelta(days=1)
    return salida


def pares() -> list[str]:
    return [f"{i:02d}-{(i + 1) % 100:02d}" for i in range(1, 100, 2)]


def calendario_consecutivo(anio: int, inicio: date) -> dict[str, str]:
    dias = [d for m in (8, 9, 10) for d in habiles(anio, m) if d >= inicio]
    return {p: d.isoformat() for p, d in zip(pares(), dias)}


def calendario_2229(anio: int) -> dict[str, str]:
    dias = habiles(anio, 8)[6:19] + habiles(anio, 9)[0:20] + habiles(anio, 10)[0:17]
    assert len(dias) == 50
    return {p: d.isoformat() for p, d in zip(pares(), dias)}


def main() -> None:
    base = json.loads((BASE / "ag2025.json").read_text(encoding="utf-8"))

    # Verificación del método contra el calendario oficial de 2026 ya cargado
    assert calendario_2229(2026) == base["vencimientos"], "El método no reproduce el calendario 2026"

    anios = {
        2024: {"uvt": 47065, "uvt_pres": 49799, "ci": 0.5088, "cal": calendario_2229(2025), "ley": "2277",
               "fuentes": ["UVT 2024: Resolución DIAN 000187 de 2023", "Componente inflacionario: Decreto 0771 de 2025", "Calendario 2025: Decreto 2229 de 2023"]},
        2023: {"uvt": 42412, "uvt_pres": 47065, "ci": 0.6671, "cal": calendario_2229(2024), "ley": "2277",
               "fuentes": ["UVT 2023: Resolución DIAN 001264 de 2022", "Componente inflacionario: Decreto 1006 de 2024", "Calendario 2024: Decreto 2229 de 2023"]},
        2022: {"uvt": 38004, "uvt_pres": 42412, "ci": 1.0, "cal": calendario_consecutivo(2023, date(2023, 8, 9)), "ley": "2010", "tarifa_div_grav": 0.35,
               "fuentes": ["UVT 2022: Resolución DIAN 000140 de 2021", "Componente inflacionario: Decreto 0848 de 2023 (100 %)", "Calendario 2023: Decreto 2487 de 2022", "Ley 2010 de 2019 y Ley 2155 de 2021"]},
        2021: {"uvt": 36308, "uvt_pres": 38004, "ci": 1.0, "cal": calendario_consecutivo(2022, date(2022, 8, 9)), "ley": "2010", "tarifa_div_grav": 0.31,
               "fuentes": ["UVT 2021: Resolución DIAN 000111 de 2020", "Componente inflacionario: Decreto 0728 de 2022 (100 %)", "Calendario 2022: Decreto 1778 de 2021", "Ley 2010 de 2019"]},
    }

    for anio, p in anios.items():
        r = json.loads(json.dumps(base))
        r["anio_gravable"] = anio
        r["estado"] = "vigente"
        r["uvt"] = p["uvt"]
        r["uvt_anio_presentacion"] = p["uvt_pres"]
        r["cedula_general"]["componente_inflacionario_rendimientos_pct"] = p["ci"]
        r["vencimientos"] = p["cal"]
        if p["ley"] == "2277":
            r["descripcion"] = f"Año gravable {anio} (se presentó en {anio + 1}). Reglas de la Ley 2277 de 2022."
        else:
            r["descripcion"] = f"Año gravable {anio} (se presentó en {anio + 1}). Reglas anteriores a la Ley 2277: Ley 2010 de 2019."
            cg = r["cedula_general"]
            cg["limite_rentas_exentas_deducciones_uvt"] = 5040
            cg["renta_exenta_laboral_tope_uvt"] = 2880
            cg["dependiente_adicional_uvt"] = 0
            cg["dependiente_adicional_max"] = 0
            cg["factura_electronica_pct"] = 0
            cg["factura_electronica_tope_uvt"] = 0
            r["dividendos"] = {
                "regimen": "tabla_propia",
                "tarifa_subcedula_gravada": p["tarifa_div_grav"],
                "tabla_dividendos": [
                    {"desde_uvt": 0, "hasta_uvt": 300, "tarifa": 0.0},
                    {"desde_uvt": 300, "hasta_uvt": None, "tarifa": 0.10},
                ],
                "descuento_art254_1_umbral_uvt": 0,
                "descuento_art254_1_pct": 0,
            }
            r["ganancias_ocasionales"] = {
                "tarifa_general": 0.10,
                "tarifa_loterias": 0.20,
                "exencion_venta_casa_habitacion_uvt": 7500,
                "exencion_herencia_vivienda_causante_uvt": 7700,
                "exencion_herencia_otros_inmuebles_uvt": 7700,
                "exencion_herencia_porcion_heredero_uvt": 3490,
                "exencion_donaciones_pct": 0.20,
                "exencion_donaciones_tope_uvt": 2290,
                "exencion_seguros_vida_uvt": 12500,
            }
            p["fuentes"].append("Arts. 303-1, 307 y 311-1 ET antes de la Ley 2277 (seguros 12.500 UVT; vivienda del causante 7.700 UVT; venta de casa 7.500 UVT)")
        r["fuentes"] = p["fuentes"]
        (BASE / f"ag{anio}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"ag{anio}.json: UVT {p['uvt']}, vence {r['vencimientos']['01-02']} a {r['vencimientos']['99-00']}")


if __name__ == "__main__":
    main()
