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

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"


settings = Settings()
