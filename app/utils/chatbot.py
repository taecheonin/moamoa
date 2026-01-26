"""
챗봇 유틸리티
Django의 diaries.utils를 FastAPI용으로 변환
OpenAI/LangChain 기반 챗봇 로직
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from sqlalchemy.orm import Session

from ..config import settings
from .chat_history import get_message_history, get_current_korea_date
from ..models.diary import FinanceDiary
from ..models.user import User


# LangChain 프롬프트 설정
chat_prompt = ChatPromptTemplate.from_messages([
    ("system", """
        Step 1
        - Conversation starts with child
        - You are an AI assistant that helps children aged 5 to 13 record their pocket money entries and record childrens were received money. 
        - You couldn't talk about other conversations except pocket money entries or recieved money.
        - Today's date is {recent_day}. The format of the date is YYYY-MM-DD.

        Step 2
        - When the child provides the details of their pocket money report, carefully read their input and extract the following:
            - Please check whether it's income or expenditure first
            - If the child provides **multiple entries in one message**, split the entries and process each one separately. Ensure that each entry has its own **date, amount, and description** and treat them as **individual transactions** and Starts '1' ordinal number next entry.
            - If transaction type is expenditure
                - The date the money was spent or received (Optional, default to today)
                - The amount of money involved (Required)
                - A brief description of how the money was used. (Required)
            - If transaction type is income
                - The date the money was received (Optional, default to today)
                - The amount of money involved (Required)
                - A brief description of how the child was received. (Required)
            - If the child provides a date in the format '10월 8일', recognize this as 'YYYY-MM-DD' format, where YYYY is the current year. Convert it to the appropriate format (e.g., '10월 8일' should become '2024-10-08').
            - If the date is not provided, assume it is today ({recent_day}).          
            - The amount of money a child can enter must not exceed 1,000,000 won. 
                - If the child mentions a number greater than 1,000,000 won in any form (e.g., '1500000', '1 million 500 thousand'), respond immediately with "{limit}". 
                - Only respond with "{limit}" when the mentioned number exceeds 1,000,000 won. 
                - For any other input or unclear messages, provide a polite response without mentioning the limit.
            - Just give user the final report
        - When the child doesn't provide the mandatory details of ther pocket money report (amount, description):
            - Tell the child that I need to fill out the contents related to the allowance entry  

        Step 3
        - Use the following categories to classify the pocket money entry. Choose the most appropriate category key based on the input:
            - 용돈(Money received regularly, or money given by parents or adults is also categorized as "용돈")
            - 기타/수입(Other types of income, such as money received on special occasions, are categorized as "기타/수입")
            - 음식
            - 음료/간식
            - 문구/완구
            - 교통
            - 문화/여가
            - 선물
            - 저축
            - 기타/지출

        - Based on the input, use the following transaction type to classify the pocket money entry:
            - 수입
            - 지출

        Step 4
        - Write a report in regular chat format, showing the child how their entry was processed, and then ask them to confirm if the report is correct:
            Report in regular chat format
            -"{chat_format}"

        Step 5
        - If child chooses "1" or positive letter, please only convert child's input to the following JSON format and Do not include any additional words! Only Json Format!:
        ```json
        [
            {{
                'diary_detail': 'Briefly describe where the child spent their pocket money, without mentioning the amount.',
                'today': 'Date of use of money in YYYY-MM-DD format',
                'category': 'The category key that best matches the child's entry',
                'transaction_type': 'The transaction_type key that best matches the child's entry',
                'amount': amount
            }},
            {{
                'diary_detail': 'Briefly describe where the child spent their pocket money, without mentioning the amount.',
                'today': 'Date of use of money in YYYY-MM-DD format',
                'category': 'The category key that best matches the child's entry',
                'transaction_type': 'The transaction_type key that best matches the child's entry',
                'amount': amount
            }}
        ]
        - If child chooses "2" or negative letter,Ask to the child about the modifications and get an answer kindly, please fill out the pocket money entry again.
        Step 6
        - if you got other conversations, you response {notice}
        - Always be gentle and speak in Korean
        - Convesation ends with child
        - If child sends 1 again, let him know to re-enter from the beginning
    """),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
])

# 프롬프트 전달 데이터
prompt_data = {
    "limit": "<strong>사용하기에는 너무 많은 금액이에요!<br> 100만원 밑으로 입력해보는게 어때요?</strong>🤗",
    "chat_format": """입력하신 내용을 바탕으로 전체 기록을 정리해 보았어요!<br>  
1. <strong>날짜</strong>: 2024-10-15
2. <strong>금액</strong>: 5000원
3. <strong>사용 내역</strong>: 탕후루를 샀음
4. <strong>분류</strong>: 음식
5. <strong>거래 유형</strong>: 지출<br>
위 내용이 맞는지 확인해 주세요!
1. 맞아요! <br> 2. 아니요, 다시 수정할래요!""",
    "notice": "<strong>용돈기입장과 관련된 정보를 입력해 주세요!<br> 금액과 어떻게 사용했는지 꼭 입력하셔야 돼요! <br> (날짜를 입력하지 않으면 오늘 날짜로 기록돼요)</strong>🥺",
}

# LangChain LLM 및 체인 설정
llm = None
with_message_history = None


def get_llm():
    """LLM 인스턴스 반환 (지연 초기화)"""
    global llm, with_message_history
    if llm is None:
        llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY)
        runnable = chat_prompt | llm | StrOutputParser()
        with_message_history = RunnableWithMessageHistory(
            runnable,
            get_message_history,
            input_messages_key="input",
            history_messages_key="chat_history",
        )
    return with_message_history


def chat_with_bot(user_input: str, user_id: int) -> str:
    """
    챗봇과 대화
    
    Args:
        user_input: 사용자 입력
        user_id: 사용자 ID
    
    Returns:
        챗봇 응답
    """
    try:
        session_id = f"user_{user_id}"
        current_date = get_current_korea_date()
        
        chain = get_llm()
        response = chain.invoke(
            {
                "limit": prompt_data.get("limit"),
                "chat_format": prompt_data.get("chat_format"),
                "notice": prompt_data.get("notice"),
                "recent_day": current_date,
                "input": user_input
            },
            config={"configurable": {"session_id": session_id}}
        )
        
        # 수입/지출 관련 영단어 한글 변환
        if isinstance(response, str):
            response = (
                response.replace("income", "수입")
                        .replace("earnings", "수입")
                        .replace("revenue", "수입")
                        .replace("profit", "수입")
                        .replace("expense", "지출")
                        .replace("expenditure", "지출")
                        .replace("spending", "지출")
                        .replace("cost", "지출")
            )
        return response
    except Exception as e:
        
        return "죄송합니다. 채팅 서비스에 일시적인 문제가 발생했습니다."


def calculate_age(birth_date: date) -> int:
    """
    생년월일로 나이 계산
    
    Args:
        birth_date: 생년월일
    
    Returns:
        나이 (만 나이)
    """
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def update_remaining_balance(db: Session, child: User) -> None:
    """
    잔액 업데이트
    
    Args:
        db: 데이터베이스 세션
        child: 자녀 사용자
    """
    # 해당 child의 모든 finance_diary 기록을 today 날짜 기준으로 정렬
    finance_entries = db.query(FinanceDiary).filter(
        FinanceDiary.child_id == child.id
    ).order_by(FinanceDiary.today).all()
    
    total_balance = Decimal('0')
    for entry in finance_entries:
        if entry.transaction_type == "수입":
            total_balance += entry.amount
        elif entry.transaction_type == "지출":
            total_balance -= entry.amount
        
        # 각 항목의 remaining 업데이트
        entry.remaining = int(total_balance)
    
    # child.total 업데이트
    child.total = int(total_balance)
    
    db.commit()
