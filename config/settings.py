from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    discord_bot_token: str
    deepseek_api_key: str
    database_url: str
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    summary_default_time: str = "22:00"
    memory_top_n: int = 10
    memory_compression_threshold: int = 500

    class Config:
        env_file = ".env"


settings = Settings()
