"""
용돈기입장 관련 Pydantic 스키마
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any
from datetime import date, datetime
from decimal import Decimal


# === 요청 스키마 ===

class ChatRequest(BaseModel):
    """챗봇 메시지 요청"""
    message: str = Field(..., min_length=1)
    child_pk: int


class MonthlySummaryRequest(BaseModel):
    """월말결산 요청"""
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)


class FinanceDiaryCreate(BaseModel):
    """용돈기입장 생성 요청"""
    diary_detail: str
    category: str
    transaction_type: str
    amount: Decimal
    today: Optional[date] = None
    
    @field_validator('transaction_type')
    @classmethod
    def validate_transaction_type(cls, v):
        if v not in ['수입', '지출']:
            raise ValueError("거래 유형은 '수입' 또는 '지출'이어야 합니다.")
        return v


# === 응답 스키마 ===

class FinanceDiaryResponse(BaseModel):
    """용돈기입장 응답"""
    id: int
    child_id: int
    parent_id: int
    diary_detail: str
    category: str
    transaction_type: str
    amount: Decimal
    remaining: int
    today: date
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class MonthlyDiaryResponse(BaseModel):
    """월별 용돈기입장 목록 응답"""
    diary: list[FinanceDiaryResponse]
    remaining_amount: int = 0


class AvailableMonthsResponse(BaseModel):
    """사용 가능한 월 목록 응답"""
    available_months: list[str]


class MonthlySummaryResponse(BaseModel):
    """월말결산 응답"""
    id: Optional[int] = None
    child_id: Optional[int] = None
    parent_id: Optional[int] = None
    content: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = None
    created_at: Optional[datetime] = None
    username: Optional[str] = None
    age: Optional[Any] = None
    summary: Optional[dict] = None
    message: Optional[str] = None
    
    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    """챗봇 응답"""
    response: Optional[str] = None
    message: Optional[str] = None
    plan: Optional[list[FinanceDiaryResponse]] = None
    error: Optional[str] = None


class ChatMessageResponse(BaseModel):
    """채팅 메시지 응답"""
    type: str  # "USER" or "AI"
    content: str
    timestamp: Optional[str] = None
    username: Optional[str] = None
    user_profile_image: Optional[str] = None
    ai_name: Optional[str] = None
    ai_profile_image: Optional[str] = None


class ChatHistoryResponse(BaseModel):
    """채팅 기록 응답"""
    response: list[ChatMessageResponse]
