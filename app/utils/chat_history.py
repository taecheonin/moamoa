"""
Redis 채팅 기록 유틸리티
Django의 diaries.chat_history를 FastAPI용으로 변환
"""
import pytz
from datetime import datetime, date
from langchain_core.chat_history import InMemoryChatMessageHistory, BaseChatMessageHistory


# 한국 시간대 설정
KOREA_TZ = pytz.timezone("Asia/Seoul")


def get_current_korea_time() -> datetime:
    """현재 한국 시간 반환"""
    return datetime.now(KOREA_TZ)


def get_current_korea_date() -> date:
    """현재 한국 날짜 반환"""
    return get_current_korea_time().date()


class CustomInMemoryChatMessageHistory(InMemoryChatMessageHistory):
    """커스탬 메모리 내 채팅 기록 클래스"""
    
    def add_message(self, message):
        """메시지에 타임스탬프 추가"""
        korea_time = get_current_korea_time()
        message.additional_kwargs['time_stamp'] = korea_time.isoformat()
        return super().add_message(message)


# 메모리 내 채팅 기록 저장소
store = {}


def get_message_history(session_id: str) -> BaseChatMessageHistory:
    """
    세션 ID를 기반으로 메모리 내 채팅 기록 반환
    
    Args:
        session_id: 세션 식별자 (예: "user_123")
    
    Returns:
        BaseChatMessageHistory 인스턴스
    """
    if session_id not in store:
        store[session_id] = CustomInMemoryChatMessageHistory()
    return store[session_id]


