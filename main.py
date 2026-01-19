"""
FastAPI 메인 애플리케이션
Django에서 FastAPI로 마이그레이션된 모아모아 프로젝트
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db
from app.routers import accounts_router, diaries_router, webs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 이벤트"""
    # 시작 시
    print("🚀 모아모아 FastAPI 서버 시작...")
    
    # 미디어 디렉토리 생성
    settings.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    (settings.MEDIA_DIR / "profile_images").mkdir(parents=True, exist_ok=True)
    
    yield
    
    # 종료 시
    print("👋 모아모아 FastAPI 서버 종료...")


# FastAPI 앱 생성
app = FastAPI(
    title="모아모아 API",
    description="어린이 용돈기입장 서비스 API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 마운트
app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")
app.mount("/media", StaticFiles(directory=str(settings.MEDIA_DIR)), name="media")

# 라우터 등록
app.include_router(accounts_router)
app.include_router(diaries_router)
app.include_router(webs_router)


@app.get("/health")
async def health_check():
    """헬스 체크 엔드포인트"""
    return {"status": "healthy", "service": "moamoa"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
