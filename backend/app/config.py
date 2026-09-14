from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./openemr.db"
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = 30
    jwt_issuer: str = "openemr-next"
    jwt_audience: str = "openemr-next-api"
    cors_origins: str = "http://localhost:5173"
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
