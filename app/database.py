"""
SQLAlchemy 데이터베이스 설정
기존 Django SQLite 데이터베이스와 호환됩니다.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

# 데이터베이스 연결 설정
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# MariaDB/MySQL의 경우 pool_pre_ping=True 설정을 권장합니다.
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    데이터베이스 세션 의존성
    각 요청마다 새로운 세션을 생성하고, 요청 완료 후 닫습니다.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """데이터베이스 테이블 생성"""
    from .models import (
        User, FinanceDiary, MonthlySummary, YearlySummary, DailySummary, AIUsageLog,
        KakaoChat, KakaoChatMember, KakaoUtterance
    )  # noqa
    Base.metadata.create_all(bind=engine)
