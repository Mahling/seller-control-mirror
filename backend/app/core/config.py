from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., alias="DATABASE_URL")
    SECRET_KEY: str = Field(..., alias="SESSION_SECRET")
    SESSION_COOKIE_NAME: str = "session"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Backwards-compat für bestehenden Code:
    @property
    def SESSION_SECRET(self) -> str:
        return self.SECRET_KEY

_settings: Settings | None = None
def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
