"""
용돈기입장 관련 API 라우터
Django의 diaries.views를 FastAPI용으로 변환
"""
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from openai import OpenAI
from langchain_core.messages.human import HumanMessage
from langchain_core.messages.ai import AIMessage

from ..config import settings
from ..database import get_db
from ..models.user import User
from ..models.diary import FinanceDiary, MonthlySummary
from ..schemas.diary import (
    ChatRequest, ChatResponse, ChatHistoryResponse, ChatMessageResponse,
    FinanceDiaryResponse, MonthlyDiaryResponse, AvailableMonthsResponse,
    MonthlySummaryRequest, MonthlySummaryResponse
)
from ..dependencies import get_current_user, decode_token
from ..utils.chatbot import chat_with_bot, calculate_age, update_remaining_balance
from ..utils.chat_history import get_message_history

router = APIRouter(prefix="/api/v1/diary", tags=["diaries"])


# === 토큰 확인 ===
@router.get("/check_token/")
async def check_token(request: Request):
    """유저 토큰 확인"""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="")
    
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="")
    
    return {}


# === 챗봇 처리 ===
@router.post("/chat/", response_model=ChatResponse)
async def process_chatbot(
    chat_request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """아이들 용돈기입장 챗봇 처리"""
    user_input = chat_request.message
    child_pk = chat_request.child_pk
    
    # 자녀 확인
    child = db.query(User).filter(User.id == child_pk).first()
    if not child:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="다른 유저는 이 기능을 사용할 수 없습니다."
        )
    
    # 챗봇 응답 받기
    response = chat_with_bot(user_input, child_pk)
    
    # JSON 응답 처리 (1 또는 2 입력)
    if "json" in response.lower():
        try:
            # JSON 파싱
            json_part = response.split("```json")[-1].split("```")[0].strip().replace("'", '"')
            plan_json = json.loads(json_part)
            
            saved_diaries = []
            
            # 여러 항목 처리
            if isinstance(plan_json, list):
                for item in plan_json:
                    today_str = item.get('today')
                    if today_str:
                        today_date = datetime.strptime(today_str, '%Y-%m-%d').date()
                    else:
                        today_date = datetime.now().date()
                    
                    finance_diary = FinanceDiary(
                        diary_detail=item.get('diary_detail'),
                        today=today_date,
                        category=item.get('category'),
                        transaction_type=item.get('transaction_type'),
                        amount=Decimal(str(item.get('amount'))),
                        remaining=child.total,
                        child_id=child.id,
                        parent_id=current_user.parents_id or current_user.id
                    )
                    db.add(finance_diary)
                    saved_diaries.append(finance_diary)
            else:
                # 단일 항목 처리
                today_str = plan_json.get('today')
                if today_str:
                    today_date = datetime.strptime(today_str, '%Y-%m-%d').date()
                else:
                    today_date = datetime.now().date()
                
                finance_diary = FinanceDiary(
                    diary_detail=plan_json.get('diary_detail'),
                    today=today_date,
                    category=plan_json.get('category'),
                    transaction_type=plan_json.get('transaction_type'),
                    amount=Decimal(str(plan_json.get('amount'))),
                    remaining=child.total,
                    child_id=child.id,
                    parent_id=current_user.parents_id or current_user.id
                )
                db.add(finance_diary)
                saved_diaries.append(finance_diary)
            
            db.commit()
            
            # 잔액 업데이트
            update_remaining_balance(db, child)
            
            # 저장된 항목 새로고침
            for diary in saved_diaries:
                db.refresh(diary)
            
            return ChatResponse(
                message="용돈기입장이 성공적으로 저장되었습니다.",
                plan=[FinanceDiaryResponse.model_validate(d) for d in saved_diaries]
            )
            
        except json.JSONDecodeError as e:
            return ChatResponse(
                message="JSON 파싱 오류가 발생했습니다.",
                error=str(e)
            )
        except Exception as e:
            return ChatResponse(
                message="처리 중 오류가 발생했습니다.",
                error=str(e)
            )
    
    return ChatResponse(response=response)


# === 채팅 기록 조회 ===
@router.get("/chat/messages/{child_pk}/", response_model=ChatHistoryResponse)
async def get_chat_messages(
    child_pk: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """채팅 메시지 기록 조회"""
    if current_user.id != child_pk:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="자신의 정보만 조회할 수 있습니다."
        )
    
    child = db.query(User).filter(User.id == child_pk).first()
    if not child:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="다른 유저는 볼 권한이 없습니다."
        )
    
    # 채팅 기록 조회
    session_id = f"user_{child.id}"
    chat_histories = get_message_history(session_id).messages
    message_history = []
    
    # 기본 URL 생성
    base_url = str(request.base_url).rstrip('/')
    
    for chat_history in chat_histories:
        message = ChatMessageResponse(
            timestamp=chat_history.additional_kwargs.get('time_stamp'),
            content=chat_history.content,
            type="USER" if isinstance(chat_history, HumanMessage) else "AI"
        )
        
        if isinstance(chat_history, HumanMessage):
            message.username = child.first_name
            if child.images:
                message.user_profile_image = f"{base_url}/media/{child.images}"
        elif isinstance(chat_history, AIMessage):
            message.ai_name = "모아모아"
            message.ai_profile_image = f"{base_url}/media/default_profile.png"
        
        message_history.append(message)
    
    return ChatHistoryResponse(response=message_history)


# === 기입장 항목 삭제 ===
@router.delete("/chat/{pk}/delete/")
async def delete_diary_entry(
    pk: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """용돈기입장 항목 삭제"""
    child = current_user
    
    diary_entry = db.query(FinanceDiary).filter(
        FinanceDiary.id == pk,
        FinanceDiary.child_id == child.id
    ).first()
    
    if not diary_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="항목을 찾을 수 없습니다."
        )
    
    # 잔액 조정
    if diary_entry.transaction_type == '수입':
        child.total -= int(diary_entry.amount)
    elif diary_entry.transaction_type == '지출':
        child.total += int(diary_entry.amount)
    
    # 삭제
    db.delete(diary_entry)
    db.commit()
    
    # 잔액 업데이트
    update_remaining_balance(db, child)
    
    return {"message": "성공적으로 삭제되었습니다."}


# === 월별 용돈기입장 조회 ===
@router.get("/{child_pk}/{year}/{month}/", response_model=MonthlyDiaryResponse)
async def get_monthly_diary(
    child_pk: int,
    year: int,
    month: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """월별 용돈기입장 리스트 조회"""
    child = db.query(User).filter(User.id == child_pk).first()
    if not child:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="다른 유저는 볼 권한이 없습니다."
        )
    
    # 해당 월의 기입장 조회
    from sqlalchemy import extract
    
    diaries = db.query(FinanceDiary).filter(
        FinanceDiary.child_id == child_pk,
        extract('year', FinanceDiary.today) == year,
        extract('month', FinanceDiary.today) == month
    ).order_by(FinanceDiary.created_at.desc(), FinanceDiary.id.desc()).all()
    
    remaining_amount = diaries[-1].remaining if diaries else 0
    
    return MonthlyDiaryResponse(
        diary=[FinanceDiaryResponse.model_validate(d) for d in diaries],
        remaining_amount=remaining_amount
    )


# === 사용 가능한 월 조회 ===
@router.get("/{child_pk}/available-months/", response_model=AvailableMonthsResponse)
async def get_available_months(
    child_pk: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """키즈 프로필 콤보박스용 사용 가능한 월 조회"""
    from sqlalchemy import distinct, extract
    
    # 해당 자녀의 기입장이 있는 월 조회 (MySQL DATE_FORMAT 사용)
    results = db.query(
        distinct(func.date_format(FinanceDiary.today, '%Y-%m'))
    ).filter(
        FinanceDiary.child_id == child_pk
    ).all()
    
    available_months = [r[0] for r in results if r[0]]
    
    return AvailableMonthsResponse(available_months=available_months)


# === 월말 결산 ===
@router.post("/monthly/{child_id}/")
async def create_monthly_summary(
    child_id: int,
    summary_request: MonthlySummaryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """월말 결산 생성/조회"""
    year = summary_request.year
    month = summary_request.month
    
    parent = current_user
    
    # 자녀 조회
    child = db.query(User).filter(
        User.id == child_id,
        User.parents_id == parent.id
    ).first()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당하는 자녀를 찾을 수 없습니다."
        )
    
    current_date = datetime.now()
    current_year = current_date.year
    current_month = current_date.month
    
    if year == current_year and month == current_month:
        # 현재 월인 경우 데이터 업데이트
        summary_content = _create_summary_content(db, child, year, month)
        
        # 저장 또는 업데이트
        existing = db.query(MonthlySummary).filter(
            MonthlySummary.child_id == child.id,
            MonthlySummary.parent_id == parent.id,
            MonthlySummary.year == year,
            MonthlySummary.month == month
        ).first()
        
        if existing:
            existing.content = json.dumps(summary_content, ensure_ascii=False)
        else:
            new_summary = MonthlySummary(
                child_id=child.id,
                parent_id=parent.id,
                year=year,
                month=month,
                content=json.dumps(summary_content, ensure_ascii=False)
            )
            db.add(new_summary)
        
        db.commit()
        return summary_content
    else:
        # 이전 월인 경우 기존 데이터 조회
        summary = db.query(MonthlySummary).filter(
            MonthlySummary.child_id == child.id,
            MonthlySummary.parent_id == parent.id,
            MonthlySummary.year == year,
            MonthlySummary.month == month
        ).first()
        
        if summary:
            return json.loads(summary.content) if isinstance(summary.content, str) else summary.content
        else:
            # 새로 생성
            summary_content = _create_summary_content(db, child, year, month)
            
            if not summary_content.get("message"):
                new_summary = MonthlySummary(
                    child_id=child.id,
                    parent_id=parent.id,
                    year=year,
                    month=month,
                    content=json.dumps(summary_content, ensure_ascii=False)
                )
                db.add(new_summary)
                db.commit()
            
            return summary_content


def _create_summary_content(db: Session, child: User, year: int, month: int) -> dict:
    """월말 결산 내용 생성"""
    child_name = child.first_name
    child_age = calculate_age(child.birthday) if child.birthday else "Unknown"
    
    # 해당 월의 기입장 조회
    from sqlalchemy import extract
    
    diaries = db.query(FinanceDiary).filter(
        FinanceDiary.child_id == child.id,
        extract('year', FinanceDiary.today) == year,
        extract('month', FinanceDiary.today) == month
    ).all()
    
    if not diaries:
        return {
            "username": child_name,
            "age": child_age,
            # "message": f"{child_name}님의 {year}년 {month}월 용돈기입장 기록이 없습니다."
            "message": f"{year}년 {month}월 용돈기입장 기록이 없습니다."
        }
    
    # 총 수입/지출 계산
    total_income = sum(float(d.amount) for d in diaries if d.transaction_type == '수입')
    total_expenditure = sum(float(d.amount) for d in diaries if d.transaction_type == '지출')
    
    # 카테고리별 지출
    category_expenditure = {}
    for diary in diaries:
        if diary.transaction_type == '지출':
            category = diary.category
            if category not in category_expenditure:
                category_expenditure[category] = 0
            category_expenditure[category] += float(diary.amount)
    
    # OpenAI 요약 생성
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    messages = [
        {
            "role": "system",
            "content": (
                f"You are a financial advisor for children. You are given pocket money records for {child_name}, a {child_age}-year-old child. "
                f"Each record has a transaction_type field, which indicates whether the transaction is an '수입' (income) or '지출' (expense). "
                f"Ensure that only records with transaction_type set to '지출' are considered in the expense calculation. "
                f"Respond entirely in Korean. "
                f"Here are the records categorized by transaction type and amount:\n"
                f"{[f'{diary.diary_detail} ({diary.transaction_type}): {diary.amount} KRW' for diary in diaries]}\n\n"
                f"Please provide the following information in JSON format, using the provided data:\n"
                f"1. 총_수입 (Total income): {total_income}\n"
                f"2. 총_지출 (Total expenditure): {total_expenditure}\n"
                f"3. 남은_금액 (Remaining amount): {total_income - total_expenditure}\n"
                f"4. 카테고리별_지출 (Expenditure by category): {category_expenditure}\n"
                f"5. 가장_많이_지출한_카테고리 (Category with the highest expenditure)\n"
                f"6. 지출_패턴_평가 (Don't say kid's name. Say just kid and Evaluation of the spending pattern and Friendly advice for improvement to parent, within 400 characters)\n"
            )
        }
    ]
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=2444,
        temperature=0.7,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )
    
    chat_response = response.choices[0].message.content
    
    # JSON 파싱
    json_str = chat_response.strip().strip('`').strip()
    if json_str.startswith('json'):
        json_str = json_str[4:].strip()
    
    try:
        summary_data = json.loads(json_str)
    except json.JSONDecodeError:
        summary_data = {"raw_response": chat_response}
    
    return {
        "username": child_name,
        "age": child_age,
        "summary": summary_data
    }
