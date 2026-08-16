"""Runtime configuration with environment-variable overrides."""

from functools import cached_property
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """EEA settings loaded from the ``EEA_`` environment namespace."""

    model_config = SettingsConfigDict(env_prefix="EEA_", extra="ignore")

    env: str = "development"
    log_level: str = "INFO"
    data_dir: Path = Path(".eea")
    db_url: str | None = None
    session_token: SecretStr | None = None
    local_auth_required: bool = False
    insecure_local_dev: bool = False
    capacity_profile: str = "foc-dev"
    ai_provider_enabled: bool = False
    requirements_model: str | None = None
    ai_api_key_reference: str | None = None
    stm32cube_g4_source: Path | None = None

    @cached_property
    def database_url(self) -> str:
        """Return the configured database URL or a local SQLite default."""

        if self.db_url:
            return self.db_url
        database_path = (self.data_dir / "eea.db").resolve()
        return f"sqlite:///{database_path.as_posix()}"
