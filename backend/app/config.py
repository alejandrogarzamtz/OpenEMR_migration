from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./openemr.db"
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = 30
    refresh_token_days: int = Field(default=7, ge=1, le=90)
    password_reset_minutes: int = Field(default=30, ge=5, le=1440)
    mfa_challenge_minutes: int = Field(default=5, ge=1, le=30)
    mfa_encryption_key: SecretStr | None = None
    secure_cookies: bool = False
    portal_appointments_enabled: bool = True
    portal_results_enabled: bool = True
    portal_documents_enabled: bool = True
    portal_forms_enabled: bool = True
    public_web_url: str = "http://localhost:5173"
    jwt_issuer: str = "openemr-next"
    jwt_audience: str = "openemr-next-api"
    cors_origins: str = "http://localhost:5173"
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
