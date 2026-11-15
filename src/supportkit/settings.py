"""Process-level settings (env vars). Per-shop settings live in clients/<shop>/config.yaml."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://supportkit:supportkit-dev@localhost:5432/supportkit"
    supportkit_model: str = "fake:rules"  # env SUPPORTKIT_MODEL; "provider:model" or "fake:rules"
    supportkit_demo_mode: bool = False  # env SUPPORTKIT_DEMO_MODE; enables demo-only /chat endpoints

    @property
    def sqlalchemy_url(self) -> str:
        """Same DSN, with the psycopg 3 driver that SQLAlchemy/Alembic need."""
        url = self.database_url
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
