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
    remaining = Column(Integer, default=0)
    today = Column(Date, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
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
