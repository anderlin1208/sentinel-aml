from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = 'sqlite:///./sentinel_local.db'
    supabase_url: str = ''
    supabase_anon_key: str = ''
    admin_email: str = ''
    cors_origins: str = 'http://localhost:5173'
    env: str = 'development'
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

@lru_cache
def settings() -> Settings:
    return Settings()
