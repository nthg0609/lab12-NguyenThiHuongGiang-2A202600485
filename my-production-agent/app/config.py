from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "My Production Agent"
    environment: str = "development"
    redis_url: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"

settings = Settings()