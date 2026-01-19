"""
FastAPI 의존성 함수들
JWT 인증, 데이터베이스 세션 등을 관리합니다.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models.user import User

# 비밀번호 해싱
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 보안 (선택적 - 쿠키 인증도 사용)
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """비밀번호 검증"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """비밀번호 해싱"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """액세스 토큰 생성"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """리프레시 토큰 생성"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """토큰 디코딩"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def get_token_from_cookie(request: Request) -> Optional[str]:
    """쿠키에서 액세스 토큰 추출"""
    return request.cookies.get("access_token")


def get_refresh_token_from_cookie(request: Request) -> Optional[str]:
    """쿠키에서 리프레시 토큰 추출"""
    return request.cookies.get("refresh_token")


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """
    현재 인증된 사용자 반환
    쿠키에서 access_token을 추출하여 인증합니다.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 쿠키에서 토큰 추출
    token = get_token_from_cookie(request)
    if not token:
        raise credentials_exception
    
    # 토큰 디코딩
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception
    
    # 토큰 타입 확인
    if payload.get("type") != "access":
        raise credentials_exception
    
    # 사용자 ID 추출
    user_id: int = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    # 사용자 조회
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    현재 인증된 사용자 반환 (선택적)
    인증되지 않은 경우 None 반환
    """
    token = get_token_from_cookie(request)
    if not token:
        return None
    
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        return None
    
    user_id = payload.get("sub")
    if user_id is None:
        return None
    
    return db.query(User).filter(User.id == user_id).first()


async def get_parent_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    부모 사용자만 허용
    """
    if not current_user.is_parent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="부모님만 접근할 수 있습니다."
        )
    return current_user


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """
    사용자 인증
    Django의 make_password 호환 (PBKDF2 SHA256)
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    
    # Django 비밀번호 형식 확인 (pbkdf2_sha256$...)
    if user.password.startswith("pbkdf2_sha256$"):
        # Django 형식의 비밀번호 검증
        from .utils.validators import verify_django_password
        if not verify_django_password(password, user.password):
            return None
    else:
        # bcrypt 형식의 비밀번호 검증
        if not verify_password(password, user.password):
            return None
    
    return user
