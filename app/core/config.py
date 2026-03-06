from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Instagram Reel Downloader"
    app_version: str = "0.1.0"
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
