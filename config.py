from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # API Security
    api_key: str = "change-me-in-env"

    # Rate Limiting
    rate_limit: str = "10/minute"

    # Scraping Delays (seconds)
    min_delay: float = 2.0
    max_delay: float = 5.0

    # Maximum pages to scrape (each page = 10 reviews)
    max_pages: int = 10

    # Amazon Base Domain
    base_domain: str = "https://www.amazon.in"

    # Amazon Login Credentials
    amazon_email: str = ""
    amazon_password: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — loaded once from .env."""
    return Settings()
