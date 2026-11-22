"""Almacén persistente para lo que debe sobrevivir a un reinicio del servidor.

Guarda tres cosas, ninguna con datos personales del contribuyente:
- Configuración editable desde la pantalla de administración (reglas por año y agentes), con un
  historial de versiones (quién cambió qué y cuándo) para poder revertir.
- Eventos de métricas sin datos personales (ver app/metricas.py).
- Contadores del cupo de IA.

Tres formas de guardar, según las variables de entorno:
- «supabase»: tablas df_config, df_config_historial y df_metricas del proyecto de Supabase, con la
  clave de servicio (SUPABASE_SERVICE_ROLE_KEY). Es lo que se usa en Render, donde el disco se borra.
- «archivo»: archivos JSON en ALMACEN_DIR (para correr en local o con un disco persistente).
- «memoria»: nada sale del proceso (pruebas y demo sin configuración).

Si Supabase no responde, se sigue con lo que hay en memoria y se registra el error: la app nunca
se cae por el almacén.
"""

from __future__ import annotations

import copy
import json
import logging
import queue
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)

_TTL_CACHE = 60.0  # segundos que se confía en lo leído antes de volver a consultar Supabase
_MAX_EVENTOS_MEMORIA = 50_000
RETENCION_DIAS = 365  # las métricas se borran al año (lo promete la página de privacidad)
_CADA_PURGA = 24 * 3600.0


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _limite_retencion() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=RETENCION_DIAS)).isoformat(timespec="seconds")


class _Memoria:
    nombre = "memoria"

    def __init__(self) -> None:
        self.config: dict[str, dict[str, Any]] = {}
        self.historial_: list[dict[str, Any]] = []
        self.eventos_: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._ultima_purga = 0.0

    # --- configuración ---
    def leer(self, clave: str) -> dict[str, Any] | None:
        fila = self.config.get(clave)
        return copy.deepcopy(fila["datos"]) if fila else None

    def claves(self, prefijo: str) -> list[str]:
        return sorted(k for k in self.config if k.startswith(prefijo))

    def escribir(self, clave: str, datos: dict[str, Any], autor: str, historial: bool = True) -> int:
        with self._lock:
            ahora = _ahora()
            self.config[clave] = {"datos": copy.deepcopy(datos), "autor": autor, "actualizada": ahora}
            vid = 0
            if historial:
                vid = len(self.historial_) + 1
                self.historial_.append({"id": vid, "clave": clave, "datos": copy.deepcopy(datos), "autor": autor, "creada": ahora})
            self._persistir()
            return vid

    def borrar(self, clave: str) -> None:
        with self._lock:
            self.config.pop(clave, None)
            self._persistir()

    def historial(self, clave: str | None = None, limite: int = 50) -> list[dict[str, Any]]:
        filas = [h for h in self.historial_ if clave is None or h["clave"] == clave]
        return [{k: v for k, v in h.items() if k != "datos"} for h in reversed(filas)][:limite]

    def version(self, vid: int) -> dict[str, Any] | None:
        h = next((h for h in self.historial_ if h["id"] == vid), None)
        return copy.deepcopy(h) if h else None

    # --- eventos ---
    def agregar_eventos(self, eventos: list[dict[str, Any]]) -> None:
        with self._lock:
            self.eventos_.extend(eventos)
            if len(self.eventos_) > _MAX_EVENTOS_MEMORIA:
                del self.eventos_[: len(self.eventos_) - _MAX_EVENTOS_MEMORIA]
            self._persistir_eventos(eventos)
        if time.time() - self._ultima_purga > _CADA_PURGA:
            self._ultima_purga = time.time()
            self.purgar_eventos()

    def purgar_eventos(self, antes_de: str | None = None) -> int:
        """Borra los eventos más viejos que la retención. Devuelve cuántos quitó de memoria."""
        limite = antes_de or _limite_retencion()
        with self._lock:
            antes = len(self.eventos_)
            self.eventos_ = [e for e in self.eventos_ if e.get("creado", "") >= limite]
            quitados = antes - len(self.eventos_)
            if quitados:
                self._reescribir_eventos()
        return quitados

    def eventos(self, desde: str | None = None) -> list[dict[str, Any]]:
        return [e for e in self.eventos_ if desde is None or e["creado"] >= desde]

    # Ganchos para el almacén en archivos
    def _persistir(self) -> None:
        pass

    def _persistir_eventos(self, nuevos: list[dict[str, Any]]) -> None:
        pass

    def _reescribir_eventos(self) -> None:
        pass


class _Archivo(_Memoria):
    nombre = "archivo"

    def __init__(self, carpeta: Path) -> None:
        super().__init__()
        self.carpeta = carpeta
        carpeta.mkdir(parents=True, exist_ok=True)
        cfg = carpeta / "configuracion.json"
        if cfg.exists():
            guardado = json.loads(cfg.read_text(encoding="utf-8"))
            self.config = guardado.get("config", {})
            self.historial_ = guardado.get("historial", [])
        ev = carpeta / "eventos.jsonl"
        if ev.exists():
            self.eventos_ = [json.loads(x) for x in ev.read_text(encoding="utf-8").splitlines() if x.strip()][-_MAX_EVENTOS_MEMORIA:]

    def _persistir(self) -> None:
        (self.carpeta / "configuracion.json").write_text(
            json.dumps({"config": self.config, "historial": self.historial_}, ensure_ascii=False), encoding="utf-8")

    def _persistir_eventos(self, nuevos: list[dict[str, Any]]) -> None:
        with (self.carpeta / "eventos.jsonl").open("a", encoding="utf-8") as f:
            for e in nuevos:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    def _reescribir_eventos(self) -> None:
        (self.carpeta / "eventos.jsonl").write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in self.eventos_), encoding="utf-8")


class _Supabase(_Memoria):
    """PostgREST de Supabase con la clave de servicio. Las tablas tienen RLS sin políticas: solo el servidor las lee."""

    nombre = "supabase"

    def __init__(self, url: str, clave: str) -> None:
        super().__init__()
        self.base = url.rstrip("/") + "/rest/v1"
        self.h = {"apikey": clave, "Authorization": f"Bearer {clave}", "Content-Type": "application/json"}
        self._cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
        self._cola: queue.Queue[list[dict[str, Any]]] = queue.Queue()
        threading.Thread(target=self._escritor, daemon=True, name="almacen-eventos").start()

    def _http(self) -> httpx.Client:
        return httpx.Client(timeout=8, headers=self.h)

    def leer(self, clave: str) -> dict[str, Any] | None:
        en_cache = self._cache.get(clave)
        if en_cache and time.monotonic() - en_cache[0] < _TTL_CACHE:
            return copy.deepcopy(en_cache[1])
        try:
            with self._http() as c:
                r = c.get(f"{self.base}/df_config", params={"clave": f"eq.{clave}", "select": "datos"})
                r.raise_for_status()
                filas = r.json()
            datos = filas[0]["datos"] if filas else None
        except httpx.HTTPError as e:
            log.warning("Almacén: no pude leer %s de Supabase (%s); uso lo que tengo en memoria", clave, e)
            return super().leer(clave)
        self._cache[clave] = (time.monotonic(), datos)
        return copy.deepcopy(datos)

    def claves(self, prefijo: str) -> list[str]:
        try:
            with self._http() as c:
                r = c.get(f"{self.base}/df_config", params={"clave": f"like.{prefijo}*", "select": "clave"})
                r.raise_for_status()
                return sorted(x["clave"] for x in r.json())
        except httpx.HTTPError as e:
            log.warning("Almacén: no pude listar %s en Supabase (%s)", prefijo, e)
            return super().claves(prefijo)

    def escribir(self, clave: str, datos: dict[str, Any], autor: str, historial: bool = True) -> int:
        super().escribir(clave, datos, autor, historial=False)  # copia local por si Supabase falla después
        ahora = _ahora()
        vid = 0
        with self._http() as c:
            r = c.post(f"{self.base}/df_config", json={"clave": clave, "datos": datos, "autor": autor, "actualizada": ahora},
                       headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
            r.raise_for_status()
            if historial:
                r = c.post(f"{self.base}/df_config_historial", json={"clave": clave, "datos": datos, "autor": autor},
                           headers={"Prefer": "return=representation"})
                r.raise_for_status()
                vid = int(r.json()[0]["id"])
        self._cache[clave] = (time.monotonic(), copy.deepcopy(datos))
        return vid

    def borrar(self, clave: str) -> None:
        super().borrar(clave)
        with self._http() as c:
            c.delete(f"{self.base}/df_config", params={"clave": f"eq.{clave}"}).raise_for_status()
        self._cache[clave] = (time.monotonic(), None)

    def historial(self, clave: str | None = None, limite: int = 50) -> list[dict[str, Any]]:
        params = {"select": "id,clave,autor,creada", "order": "id.desc", "limit": str(limite)}
        if clave:
            params["clave"] = f"eq.{clave}"
        try:
            with self._http() as c:
                r = c.get(f"{self.base}/df_config_historial", params=params)
                r.raise_for_status()
                return r.json()
        except httpx.HTTPError as e:
            log.warning("Almacén: no pude leer el historial (%s)", e)
            return super().historial(clave, limite)

    def version(self, vid: int) -> dict[str, Any] | None:
        try:
            with self._http() as c:
                r = c.get(f"{self.base}/df_config_historial", params={"id": f"eq.{vid}", "select": "*"})
                r.raise_for_status()
                filas = r.json()
            return filas[0] if filas else None
        except httpx.HTTPError as e:
            log.warning("Almacén: no pude leer la versión %s (%s)", vid, e)
            return super().version(vid)

    def agregar_eventos(self, eventos: list[dict[str, Any]]) -> None:
        super().agregar_eventos(eventos)
        self._cola.put(eventos)  # se escriben en segundo plano: una métrica nunca demora una respuesta

    def _escritor(self) -> None:
        while True:
            lote = self._cola.get()
            try:
                while not self._cola.empty() and len(lote) < 500:
                    lote += self._cola.get_nowait()
                filas = [{"sesion": e.get("sesion"), "tipo": e["tipo"], "datos": e, "creado": e["creado"]} for e in lote]
                with self._http() as c:
                    c.post(f"{self.base}/df_metricas", json=filas, headers={"Prefer": "return=minimal"}).raise_for_status()
            except Exception as e:  # noqa: BLE001 - las métricas no pueden tumbar el servidor
                log.warning("Almacén: no pude guardar %d eventos en Supabase (%s)", len(lote), e)

    def purgar_eventos(self, antes_de: str | None = None) -> int:
        limite = antes_de or _limite_retencion()
        quitados = super().purgar_eventos(limite)

        def borrar() -> None:
            try:
                with self._http() as c:
                    c.delete(f"{self.base}/df_metricas", params={"creado": f"lt.{limite}"}).raise_for_status()
            except httpx.HTTPError as e:
                log.warning("Almacén: no pude borrar las métricas viejas (%s)", e)

        threading.Thread(target=borrar, daemon=True).start()  # no demora la respuesta que disparó la purga
        return quitados

    def eventos(self, desde: str | None = None) -> list[dict[str, Any]]:
        params = {"select": "datos", "order": "id.asc", "limit": "50000"}
        if desde:
            params["creado"] = f"gte.{desde}"
        try:
            with self._http() as c:
                r = c.get(f"{self.base}/df_metricas", params=params)
                r.raise_for_status()
                return [x["datos"] for x in r.json()]
        except httpx.HTTPError as e:
            log.warning("Almacén: no pude leer las métricas (%s); uso las de memoria", e)
            return super().eventos(desde)


_almacen: _Memoria | None = None


def obtener() -> _Memoria:
    global _almacen
    if _almacen is None:
        _almacen = _crear()
        log.info("Almacén: %s", _almacen.nombre)
    return _almacen


def _crear() -> _Memoria:
    modo = settings.almacen_modo
    if modo == "supabase":
        return _Supabase(settings.supabase_url, settings.supabase_service_key)
    if modo == "archivo":
        return _Archivo(settings.almacen_dir)
    return _Memoria()


def reiniciar(nuevo: _Memoria | None = None) -> _Memoria:
    """Para las pruebas: empieza con un almacén limpio."""
    global _almacen
    _almacen = nuevo or _Memoria()
    return _almacen
