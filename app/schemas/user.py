"""
사용자 관련 Pydantic 스키마
요청/응답 데이터 검증을 담당합니다.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import date


# === 요청 스키마 ===

class LoginRequest(BaseModel):
    """로그인 요청"""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class UserCreate(BaseModel):
    """자녀 계정 생성 요청"""
    username: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=8)
    password2: str = Field(..., min_length=8)
    email: Optional[EmailStr] = None
    first_name: str = Field(..., min_length=1)
    birthday: date


class UserUpdate(BaseModel):
    """사용자 정보 수정 요청"""
    firstname: Optional[str] = None
    password: Optional[str] = None
    birthday: Optional[date] = None
    encouragement: Optional[str] = None


class TokenRefreshRequest(BaseModel):
    """토큰 갱신 요청"""
    refresh_token: Optional[str] = None


# === 응답 스키마 ===

class UserResponse(BaseModel):
    """사용자 정보 응답"""
    id: int
    username: str
    first_name: str
    birthday: Optional[date] = None
    email: Optional[str] = None
    parents_id: Optional[int] = None
    encouragement: Optional[str] = None
    images: Optional[str] = None
    total: int = 0
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """토큰 응답"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserWithTokenResponse(BaseModel):
    """사용자 정보 + 토큰 응답"""
    user: UserResponse
    tokens: TokenResponse


class ParentWithChildrenResponse(BaseModel):
    """부모와 자녀 목록 응답"""
    parent: UserResponse
    children: list[UserResponse]


class ChildWithParentResponse(BaseModel):
    """자녀와 부모 정보 응답"""
    child: UserResponse
    parent: Optional[UserResponse] = None
