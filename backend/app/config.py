"""Configuración leída de variables de entorno."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _solo_dominio(url: str) -> str:
    """«https://x.supabase.co/rest/v1/» → «https://x.supabase.co»: el cliente necesita la raíz del proyecto."""
    m = re.match(r"\s*(https?://[^/\s]+)", url)
    return m.group(1) if m else ""


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", BASE_DIR / "data")))
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_base_url: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )
    # "openrouter" usa modelos reales; "simulado" responde sin red (pruebas y demo sin llave)
    llm_mode: str = field(default_factory=lambda: os.getenv("LLM_MODE", ""))
    admin_token: str = field(default_factory=lambda: os.getenv("ADMIN_TOKEN", ""))
    app_url: str = field(default_factory=lambda: os.getenv("APP_URL", "https://declarafacil.onrender.com"))
    frontend_dir: Path = field(
        default_factory=lambda: Path(os.getenv("FRONTEND_DIR", BASE_DIR.parent / "frontend" / "dist"))
    )
    # Orígenes que pueden llamar la API desde otro dominio (la demo en GitHub Pages), separados por coma
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip() for o in os.getenv("CORS_ORIGINS", "https://suntzz.github.io,https://miguel-rogelis.github.io").split(",") if o.strip()
        ]
    )
    # Cuentas (opcional): proyecto de Supabase. La clave «anon» es pública: la usa el navegador para iniciar sesión
    supabase_url: str = field(default_factory=lambda: _solo_dominio(os.getenv("SUPABASE_URL", "")))
    supabase_anon_key: str = field(default_factory=lambda: os.getenv("SUPABASE_ANON_KEY", ""))
    # ID de cliente de Google (público): con él, el botón de Google dice «DeclaraFácil» y no la dirección de Supabase
    google_client_id: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_ID", "").strip())
    # Clave de servicio de Supabase (secreta, solo en el servidor): guarda reglas, agentes, métricas y cupo
    supabase_service_key: str = field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip())
    almacen: str = field(default_factory=lambda: os.getenv("ALMACEN", "").strip().lower())
    almacen_dir: Path = field(default_factory=lambda: Path(os.getenv("ALMACEN_DIR", BASE_DIR / "estado")))
    # Correos que pueden administrar reglas y agentes iniciando sesión (además de ADMIN_TOKEN)
    admin_emails: list[str] = field(
        default_factory=lambda: [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]
    )
    # Perfil de modelos: «gratis» (agentes.json) o «pago» (agentes_pago.json, para el piloto)
    perfil_modelos: str = field(default_factory=lambda: os.getenv("PERFIL_MODELOS", "gratis").strip().lower())
    # Pide a OpenRouter solo proveedores que no guardan ni entrenan con los datos
    sin_retencion: bool = field(default_factory=lambda: os.getenv("OPENROUTER_SIN_RETENCION", "") in ("1", "true", "si"))
    max_upload_mb: int = 8

    @property
    def almacen_modo(self) -> str:
        if self.almacen in ("memoria", "archivo", "supabase"):
            return self.almacen
        if self.supabase_url and self.supabase_service_key:
            return "supabase"
        if os.getenv("ALMACEN_DIR"):
            return "archivo"
        return "memoria"

    @property
    def reglas_dir(self) -> Path:
        return self.data_dir / "reglas"

    @property
    def modo_llm(self) -> str:
        if self.llm_mode:
            return self.llm_mode
        return "openrouter" if self.openrouter_api_key else "simulado"


settings = Settings()
