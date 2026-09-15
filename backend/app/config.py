from urllib.parse import urlparse

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    deployment_environment: str = Field(default="development", pattern="^(development|test|production)$")
    database_url: str = "sqlite:///./openemr.db"
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = 30
    refresh_token_days: int = Field(default=7, ge=1, le=90)
    password_reset_minutes: int = Field(default=30, ge=5, le=1440)
    password_reset_request_cooldown_seconds: int = Field(default=60, ge=10, le=3600)
    mfa_challenge_minutes: int = Field(default=5, ge=1, le=30)
    ip_max_failed_logins: int = Field(default=5, ge=1, le=100)
    ip_failure_window_minutes: int = Field(default=15, ge=1, le=1440)
    mfa_encryption_key: SecretStr | None = None
    secure_cookies: bool = False
    portal_appointments_enabled: bool = True
    portal_results_enabled: bool = True
    portal_documents_enabled: bool = True
    portal_forms_enabled: bool = True
    portal_billing_enabled: bool = True
    portal_questionnaires_enabled: bool = True
    portal_notifications_enabled: bool = True
    notification_delivery_mode: str = Field(default="disabled", pattern="^(disabled|test)$")
    payment_provider: str = Field(default="disabled", pattern="^(disabled|test)$")
    billing_currency: str = Field(default="USD", min_length=3, max_length=3)
    simplified_demographics: bool = False
    ippf_specific: bool = False
    public_web_url: str = "http://localhost:5173"
    api_public_url: str = "http://localhost:8000"
    smart_oidc_private_key_path: str | None = None
    smart_oidc_key_id: str = "openrm-smart-oidc"
    jwt_issuer: str = "openemr-next"
    jwt_audience: str = "openemr-next-api"
    cors_origins: str = "http://localhost:5173"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    max_request_body_bytes: int = Field(default=25 * 1024 * 1024, ge=65536, le=100 * 1024 * 1024)
    release: str = "development"
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip().rstrip("/") for item in self.cors_origins.split(",") if item.strip()]

    @property
    def allowed_host_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    @model_validator(mode="after")
    def production_contract(self):
        if self.deployment_environment != "production": return self
        errors=[];jwt_value=self.jwt_secret.get_secret_value()
        weak={"replace-with-at-least-32-random-characters","local-development-secret-change-me","test-only-secret-that-is-at-least-32-bytes"}
        if not self.database_url.startswith(("postgresql://","postgresql+psycopg://")):errors.append("DATABASE_URL must use PostgreSQL")
        if len(jwt_value)<48 or jwt_value in weak:errors.append("JWT_SECRET must be a unique secret of at least 48 characters")
        if not self.mfa_encryption_key:errors.append("MFA_ENCRYPTION_KEY is required")
        else:
            try:Fernet(self.mfa_encryption_key.get_secret_value().encode("ascii"))
            except Exception:errors.append("MFA_ENCRYPTION_KEY must be a valid Fernet key")
        if not self.secure_cookies:errors.append("SECURE_COOKIES must be true")
        for name,value in (("PUBLIC_WEB_URL",self.public_web_url),("API_PUBLIC_URL",self.api_public_url)):
            if urlparse(value).scheme!="https" or not urlparse(value).hostname:errors.append(f"{name} must be an HTTPS URL")
        if not self.cors_origin_list or any(origin=="*" or urlparse(origin).scheme!="https" or not urlparse(origin).hostname for origin in self.cors_origin_list):errors.append("CORS_ORIGINS must contain explicit HTTPS origins")
        public_hosts={urlparse(self.public_web_url).hostname,urlparse(self.api_public_url).hostname}
        if not self.allowed_host_list or "*" in self.allowed_host_list or not public_hosts.issubset(set(self.allowed_host_list)):errors.append("ALLOWED_HOSTS must explicitly include public web and API hosts")
        if self.bootstrap_admin_email or self.bootstrap_admin_password:errors.append("bootstrap administrator credentials are forbidden")
        if not self.smart_oidc_private_key_path:errors.append("SMART_OIDC_PRIVATE_KEY_PATH is required")
        if self.notification_delivery_mode=="test" or self.payment_provider=="test":errors.append("test delivery/payment adapters are forbidden")
        if errors:raise ValueError("Invalid production configuration: "+"; ".join(errors))
        return self


settings = Settings()
