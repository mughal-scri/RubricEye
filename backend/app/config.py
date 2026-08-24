from pathlib import Path

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

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"


settings = Settings()
