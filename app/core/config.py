from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CRM Sales App"
    app_environment: str = "development"
    database_url: str = "postgresql+psycopg://cmr:cmr@localhost:5432/cmr"
    database_runtime_role: str = "cmr_app"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    auth_cookie_secure: bool = False
    auth_expose_reset_token: bool = True
    auth_reset_token_expire_minutes: int = 30
    auth_mfa_challenge_expire_minutes: int = 5
    auth_rate_limit_window_minutes: int = 15
    auth_rate_limit_max_attempts: int = 5
    auth_smtp_host: str | None = None
    auth_smtp_port: int = 587
    auth_smtp_username: str | None = None
    auth_smtp_password: str | None = None
    auth_smtp_from_email: str | None = None
    auth_smtp_use_tls: bool = True
    dev_user_password: str | None = None
    openai_api_key: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str = "glm-5.2"
    embedding_provider: str = "local"
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_version: str = "1"
    embedding_dimensions: int = 1536
    rag_chunk_size: int = 1200
    rag_chunk_overlap: int = 180
    knowledge_upload_dir: str = "data/knowledge_uploads"
    knowledge_max_upload_bytes: int = 20_000_000
    knowledge_max_pdf_pages: int = 500
    knowledge_max_extracted_chars: int = 500_000
    knowledge_storage_backend: str = "local"
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "cmr-knowledge"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = True
    s3_server_side_encryption: str | None = None
    public_api_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    microsoft_oauth_client_id: str | None = None
    microsoft_oauth_client_secret: str | None = None
    microsoft_oauth_tenant: str = "common"
    integration_worker_batch_size: int = 20
    integration_job_max_attempts: int = 5
    integration_import_max_bytes: int = 10_000_000
    integration_import_max_rows: int = 10_000
    webhook_allow_private_networks: bool = False
    knowledge_ocr_enabled: bool = True
    knowledge_ocr_languages: str = "rus+eng"
    knowledge_ocr_dpi: int = 200
    knowledge_ocr_max_pages: int = 50
    knowledge_ocr_page_timeout_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()


def validate_security_settings() -> None:
    if settings.app_environment != "production":
        return
    errors: list[str] = []
    if settings.secret_key == "change-me-in-production" or len(settings.secret_key) < 32:
        errors.append("SECRET_KEY must be unique and at least 32 characters")
    if settings.auth_expose_reset_token:
        errors.append("AUTH_EXPOSE_RESET_TOKEN must be false")
    if not settings.auth_smtp_host or not settings.auth_smtp_from_email:
        errors.append("AUTH_SMTP_HOST and AUTH_SMTP_FROM_EMAIL are required")
    if errors:
        raise RuntimeError("Unsafe production authentication configuration: " + "; ".join(errors))
