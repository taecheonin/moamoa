from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base

class KakaoChat(Base):
    """
    카카오톡 채팅방 정보 저장 모델
    """
    __tablename__ = "kakao_chats"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    
    # 멤버들과의 관계 설정
    members = relationship("KakaoChatMember", back_populates="chat", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<KakaoChat(id={self.id}, chat_id='{self.chat_id}')>"

class KakaoChatMember(Base):
    """
    카카오톡 채팅방 멤버 정보 저장 모델
    user_type: 0 (부모), 1 (자녀)
    """
    __tablename__ = "kakao_chat_members"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("kakao_chats.id"), nullable=False, index=True)
    user_key = Column(String(255), nullable=False, index=True)
    user_type = Column(Integer, default=0)  # 0: 부모, 1: 자녀
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 채팅방 정보와의 관계 설정
    chat = relationship("KakaoChat", back_populates="members")

class KakaoUtterance(Base):
    """
    카카오톡 발화문 모니터링 저장 모델
    """
    __tablename__ = "kakao_utterances"
    
    id = Column(Integer, primary_key=True, index=True)
    user_key = Column(String(255), nullable=True, index=True)
    chat_id = Column(String(255), nullable=True, index=True)
    utterance = Column(Text, nullable=True)
    block_id = Column(String(255), nullable=True, index=True)
    params = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<KakaoUtterance(id={self.id}, user_key='{self.user_key}', utterance='{self.utterance[:20]}...')>"
