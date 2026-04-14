from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://pn_user:pn_secret@localhost:5433/plan_naryad"
    
    # App
    app_title: str = "План-наряд API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Autogeneration limits
    max_items_per_contractor: int = 10
    
    class Config:
        env_file = ".env"


settings = Settings()