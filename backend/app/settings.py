from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    APP_PORT: int = 8088
    DATABASE_URL: str = "postgresql+psycopg2://seller:changeme@db:5432/sellercontrol"
    SP_REGION: str = "eu"
    LWA_CLIENT_ID: str | None = None
    LWA_CLIENT_SECRET: str | None = None
    AWS_ACCESS_KEY: str | None = None
    AWS_SECRET_KEY: str | None = None
    ROLE_ARN: str | None = None
    class Config:
        env_file = ".env"
settings = Settings()
