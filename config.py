from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    slack_bot_token: str
    slack_signing_secret: str
    google_service_account_json: str  # file path OR raw JSON string
    google_sheet_id: str
    slack_channel_id: str = ""  # lock to specific channel (optional)
    port: int = 8001
    groq_api_key: str = ""  # empty = disabled, falls back to regex parser
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"


settings = Settings()
