"""
사용자(User) 모델
Django의 accounts.models.User와 호환됩니다.
"""
from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from ..database import Base


class User(Base):
    """
    사용자 모델
    - 부모: parents_id가 None
    - 자녀: parents_id에 부모의 id가 설정됨
    """
    __tablename__ = "accounts_user"
    
    id = Column(Integer, primary_key=True, index=True)
    password = Column(String(128), nullable=False)
    last_login = Column(String(50), nullable=True)
    is_superuser = Column(Boolean, default=False)
    username = Column(String(150), unique=True, nullable=False, index=True)
    first_name = Column(String(150), default="")
    last_name = Column(String(150), default="")
    email = Column(String(254), default="")
    is_staff = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    date_joined = Column(String(50), nullable=True)
    
    # 커스텀 필드
    parents_id = Column(Integer, ForeignKey("accounts_user.id"), nullable=True)
    birthday = Column(Date, nullable=True)
    images = Column(String(200), nullable=True, default="default_profile.png")
    encouragement = Column(Text, nullable=True)
    total = Column(Integer, default=0)
    
    # 관계 설정
    parent = relationship("User", remote_side=[id], backref="children", foreign_keys=[parents_id])
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"
    
    @property
    def is_parent(self) -> bool:
        """부모인지 확인"""
        return self.parents_id is None
    
    @property
    def is_child(self) -> bool:
        """자녀인지 확인"""
        return self.parents_id is not None
