from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mount Madness API"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    database_url: str = ""
    jwt_secret_key: str
    jwt_algorithm: str

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
