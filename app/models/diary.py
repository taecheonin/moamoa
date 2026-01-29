"""
용돈기입장(FinanceDiary) 및 월말결산(MonthlySummary) 모델
Django의 diaries.models와 호환됩니다.
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class FinanceDiary(Base):
    """
    용돈기입장 모델
    자녀의 수입/지출을 기록합니다.
    """
    __tablename__ = "diaries_financediary"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("accounts_user.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("accounts_user.id"), nullable=False)
    diary_detail = Column(Text, nullable=False)
    category = Column(String(100), nullable=False)
    transaction_type = Column(String(7), nullable=False)  # "수입" or "지출"
    amount = Column(Numeric(10, 2), nullable=False)
    today = Column(Date, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    kakao_sync_id = Column(String(100), nullable=True, index=True)
    kakao_chat_id = Column(Integer, ForeignKey("kakao_chats.id"), nullable=True, index=True)  # 채팅방 그룹 기준 조회용
    writer_type = Column(Integer, default=1)  # 0: 부모, 1: 자녀
    
    # 관계 설정
    child = relationship("User", foreign_keys=[child_id], backref="diaries")
    parent = relationship("User", foreign_keys=[parent_id], backref="parent_diaries")
    
    def __repr__(self):
        return f"<FinanceDiary(id={self.id}, child_id={self.child_id}, detail='{self.diary_detail[:20]}...')>"


class MonthlySummary(Base):
    """
    월말결산 모델
    월별 용돈 사용 요약을 저장합니다.
    """
    __tablename__ = "diaries_monthlysummary"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("accounts_user.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("accounts_user.id"), nullable=False)
    content = Column(Text, nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    
    # 유니크 제약 조건
    __table_args__ = (
        UniqueConstraint('child_id', 'parent_id', 'year', 'month', name='unique_monthly_summary'),
    )
    
    # 관계 설정
    child = relationship("User", foreign_keys=[child_id], backref="plans")
    parent = relationship("User", foreign_keys=[parent_id], backref="parent_plans")
    
    def __repr__(self):
        return f"<MonthlySummary(id={self.id}, child_id={self.child_id}, {self.year}/{self.month})>"


class YearlySummary(Base):
    """
    연말결산 모델
    연간 용돈 사용 요약을 저장합니다.
    """
    __tablename__ = "diaries_yearlysummary"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("accounts_user.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("accounts_user.id"), nullable=False)
    content = Column(Text, nullable=False)
    year = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    
    # 유니크 제약 조건
    __table_args__ = (
        UniqueConstraint('child_id', 'parent_id', 'year', name='unique_yearly_summary'),
    )
    
    # 관계 설정
    child = relationship("User", foreign_keys=[child_id], backref="yearly_plans")
    parent = relationship("User", foreign_keys=[parent_id], backref="parent_yearly_plans")
    
    def __repr__(self):
        return f"<YearlySummary(id={self.id}, child_id={self.child_id}, {self.year})>"


class KakaoSync(Base):
    """
    카카오 상호작용 동기화 모델
    맞아요/아니요 버튼의 상태를 추적하여 중복 등록 방지 및 취소 기능을 지원합니다.
    """
    __tablename__ = "kakao_sync"
    
    id = Column(Integer, primary_key=True, index=True)
    sync_id = Column(String(100), unique=True, nullable=False, index=True)
    status = Column(String(20), nullable=False)  # "SAVED", "CANCELLED"
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DailySummary(Base):
    """
    일일결산 모델
    하루의 용돈 사용 요약을 저장합니다.
    """
    __tablename__ = "diaries_dailysummary"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("accounts_user.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("accounts_user.id"), nullable=False)
    content = Column(Text, nullable=False)
    today = Column(Date, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 유니크 제약 조건
    __table_args__ = (
        UniqueConstraint('child_id', 'parent_id', 'today', name='unique_daily_summary'),
    )
    
    # 관계 설정
    child = relationship("User", foreign_keys=[child_id], backref="daily_plans")
    parent = relationship("User", foreign_keys=[parent_id], backref="parent_daily_plans")


class AIUsageLog(Base):
    """
    AI 사용 로그 모델
    결산별 AI 호출 횟수를 기록합니다.
    """
    __tablename__ = "ai_usage_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("accounts_user.id"), nullable=False)
    report_type = Column(String(20), nullable=False)  # daily, monthly, yearly
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=True)  # daily, monthly
    day = Column(Integer, nullable=True)  # daily
    count = Column(Integer, default=0)
    last_called_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('child_id', 'report_type', 'year', 'month', 'day', name='unique_ai_usage'),
    )
