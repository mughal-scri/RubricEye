from pathlib import Path
import secrets
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RUBRICEYE_", env_file=".env")

    data_dir: Path = Path.home() / "rubriceye_data"
    db_filename: str = "rubriceye.db"
    pdf_dpi: int = 200
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    dashscope_api_key: str | None = None

    # --- Phase 2 additions ---
    grading_model: str = "qwen-vl-max"
    # Studio reads graphical/scanned question papers, so it uses a separately
    # configurable multimodal model rather than inheriting the grading model.
    studio_model: str = "qwen3.7-plus"
    dashscope_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    image_max_width: int = 1200
    studio_max_text_chars: int = 40000
    studio_max_pages: int = 12
    max_pdf_bytes: int = 15 * 1024 * 1024
    max_pdf_pages: int = 100
    ink_density_blank_threshold: float = 0.02
    ink_density_ambiguous_threshold: float = 0.04

    # --- Phase 2: security boundaries ---
    api_token: str | None = None
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    def ensure_token(self) -> str:
        """Auto-generate or load the persistent API token.

        Called once during app startup. If RUBRICEYE_API_TOKEN is already
        set, uses that value. Otherwise reads from <data_dir>/.api_token
        or generates a new one, persists it, and prints it once.
        """
        if self.api_token:
            return self.api_token

        token_file = self.data_dir / ".api_token"
        if token_file.exists():
            token = token_file.read_text().strip()
            if token:
                self.api_token = token
                return token

        # Generate a new token and persist it.
        token = secrets.token_urlsafe(32)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        token_file.write_text(token)
        token_file.chmod(0o600)
        print(
            f"\n[RubricEye] API token generated and saved to {token_file}\n"
            f"            The frontend fetches this automatically from /config.\n",
            file=sys.stderr,
        )
        self.api_token = token
        return token

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"


settings = Settings()
