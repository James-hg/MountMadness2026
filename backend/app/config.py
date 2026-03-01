from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mount Madness API"
    gemini_api_key: str = ""
    # default model used for receipt parsing; must support generateContent
    # choose a model that is available in your Gemini API account. if unsure,
    # run "ListModels" or check provider docs. 1.5 is widely supported.
    gemini_model: str = "gemini-2.5-pro"  # override via GEMINI_MODEL in .env if needed
    database_url: str = ""
    # Comma-separated origins for CORS. Use "*" only for hackathon/demo environments.
    cors_allow_origins: str = "*"
    jwt_secret_key: str
    jwt_algorithm: str

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
