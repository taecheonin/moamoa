"""
FastAPI 애플리케이션 설정
환경 변수를 사용하여 설정을 관리합니다.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # 기본 설정
    SECRET_KEY: str = "your-secret-key-change-in-production"
    DEBUG: bool = True
    
    # JWT 설정
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 1
    REFRESH_TOKEN_EXPIRE_DAYS: int = 1
    
    # OpenAI 설정
    OPENAI_API_KEY: str = ""
    
    # 카카오 OAuth 설정
    CLIENT_SECRET: str = ""
    REST_API_KEY: str = ""
    KAKAO_CALLBACK_URI: str = ""
    FRONTEND_URL: str = "http://localhost"
    
    # 데이터베이스 설정
    DATABASE_URL: str = "sqlite:///./db.sqlite3"
    
    # 파일 경로 설정
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    MEDIA_DIR: Path = BASE_DIR / "media"
    STATIC_DIR: Path = BASE_DIR / "static"
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    
    # CORS 설정
    CORS_ORIGINS: list = ["http://localhost"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """설정 싱글톤 인스턴스 반환"""
    return Settings()


settings = get_settings()
