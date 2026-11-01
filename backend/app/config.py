"""Configuración leída de variables de entorno."""

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


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
    max_upload_mb: int = 5

    @property
    def reglas_dir(self) -> Path:
        return self.data_dir / "reglas"

    @property
    def modo_llm(self) -> str:
        if self.llm_mode:
            return self.llm_mode
        return "openrouter" if self.openrouter_api_key else "simulado"


settings = Settings()
