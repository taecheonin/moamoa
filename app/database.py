"""
SQLAlchemy 데이터베이스 설정
기존 Django SQLite 데이터베이스와 호환됩니다.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

# SQLite 연결 설정 (check_same_thread=False는 FastAPI 비동기 처리를 위해 필요)
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

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
    from .models import User, FinanceDiary, MonthlySummary  # noqa
    Base.metadata.create_all(bind=engine)
