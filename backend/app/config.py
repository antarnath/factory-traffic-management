"""
Application configuration loaded from environment variables / .env file.

Switch databases by changing DB_URL in `.env`:
  - PostgreSQL:  postgresql+psycopg://user:pass@host:port/dbname
  - MySQL:       mysql+pymysql://user:pass@host:port/dbname?charset=utf8mb4
  - SQLite:      sqlite:///./factory_traffic.db
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "factory-traffic"
    debug: bool = False
    secret_key: str = "insecure-default-change-me"

    # Single connection string — see file header for examples.
    db_url: str = "sqlite:///./factory_traffic.db"


# A single shared instance.
settings = Settings()
