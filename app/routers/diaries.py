"""
용돈기입장 관련 API 라우터
Django의 diaries.views를 FastAPI용으로 변환
"""
import json
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import func
from openai import OpenAI, RateLimitError
from ..utils.logger import log_rate_limit_error
from langchain_core.messages.human import HumanMessage
from langchain_core.messages.ai import AIMessage

from ..config import settings
from ..database import get_db
from ..models.user import User
from ..models.diary import FinanceDiary, MonthlySummary, YearlySummary, DailySummary, AIUsageLog
from ..schemas.diary import (
    ChatRequest, ChatResponse, ChatHistoryResponse, ChatMessageResponse,
    FinanceDiaryResponse, MonthlyDiaryResponse, AvailableMonthsResponse,
    MonthlySummaryRequest, MonthlySummaryResponse,
    YearlySummaryRequest, YearlySummaryResponse,
    DailySummaryRequest, DailySummaryResponse
)
from ..dependencies import get_current_user, decode_token
from ..utils.chatbot import chat_with_bot, calculate_age
from ..utils.chat_history import get_message_history

router = APIRouter(prefix="/api/v1/diary", tags=["diaries"])


def _check_ai_called_today(db: Session, child_id: int, report_type: str, year: int, month: Optional[int] = None, day: Optional[int] = None) -> bool:
    """오늘 AI를 이미 호출했는지 확인"""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    log = db.query(AIUsageLog).filter(
        AIUsageLog.child_id == child_id,
        AIUsageLog.report_type == report_type,
        AIUsageLog.year == year,
        AIUsageLog.month == month,
        AIUsageLog.day == day,
        AIUsageLog.last_called_at >= today_start
    ).first()
    
    return log is not None


def _increment_ai_usage(db: Session, child_id: int, report_type: str, year: int, month: Optional[int] = None, day: Optional[int] = None):
    """AI 사용 횟수 증가"""
    log = db.query(AIUsageLog).filter(
        AIUsageLog.child_id == child_id,
        AIUsageLog.report_type == report_type,
        AIUsageLog.year == year,
        AIUsageLog.month == month,
        AIUsageLog.day == day
    ).first()
    
    if log:
        log.count += 1
        log.last_called_at = datetime.now()
    else:
        log = AIUsageLog(
            child_id=child_id,
            report_type=report_type,
            year=year,
            month=month,
            day=day,
            count=1,
            last_called_at=datetime.now()
        )
        db.add(log)
    
    db.commit()


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
            
            # 작성자 타입 결정 (0: 부모, 1: 자녀)
            writer_type = 1 if current_user.id == child.id else 0
            chat_id = chat_request.chat_id
            
            # 데이터를 리스트로 통일
            items = plan_json if isinstance(plan_json, list) else [plan_json]
            
            for item in items:
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
                    child_id=child.id,
                    parent_id=current_user.parents_id or current_user.id,
                    kakao_chat_id=chat_id,
                    writer_type=writer_type
                )
                db.add(finance_diary)
                saved_diaries.append(finance_diary)
            
            db.commit()
            
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
    diary_entry = db.query(FinanceDiary).filter(FinanceDiary.id == pk).first()
    
    if not diary_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="항목을 찾을 수 없습니다."
        )
    
    # 해당 기입장의 주인(자녀) 조회
    child = db.query(User).filter(User.id == diary_entry.child_id).first()
    if not child:
         raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # 권한 확인
    is_owner = (current_user.id == child.id)
    is_parent = (child.parents_id == current_user.id)
    
    if not (is_owner or is_parent):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="삭제 권한이 없습니다."
        )
        
    # 권한 및 정책 확인
    # 1. 부모는 모든 항목 삭제 가능
    if is_parent:
        pass # OK

    # 2. 자녀(부모가 있는 경우)는 삭제 불가
    elif is_owner and child.parents_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="자녀는 항목을 삭제할 수 없습니다. 부모님께 요청하세요."
        )

    # 3. 독립 성인(부모 없음)은 본인 항목 삭제 가능
    elif is_owner and not child.parents_id:
        pass # OK

    else:
        # 그 외 (제3자 등)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="삭제 권한이 없습니다."
        )
    
    # 삭제
    db.delete(diary_entry)
    db.commit()
    
    return {"message": "성공적으로 삭제되었습니다."}


# === 월별 용돈기입장 조회 ===
@router.get("/{child_pk}/{year}/{month}/", response_model=MonthlyDiaryResponse)
async def get_monthly_diary(
    child_pk: int,
    year: int,
    month: int,
    chat_id: Optional[int] = None,  # 채팅방 ID (있으면 그룹 기준 조회)
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
    
    # chat_id가 있으면 채팅방 그룹 기준으로 조회
    if chat_id:
        diaries = db.query(FinanceDiary).filter(
            FinanceDiary.kakao_chat_id == chat_id,
            extract('year', FinanceDiary.today) == year,
            extract('month', FinanceDiary.today) == month
        ).order_by(FinanceDiary.created_at.desc(), FinanceDiary.id.desc()).all()
        print(f"DEBUG get_monthly_diary - Chat ID {chat_id}: Found {len(diaries)} diaries")
    else:
        # 기존 방식: child_id 기준 조회
        diaries = db.query(FinanceDiary).filter(
            FinanceDiary.child_id == child_pk,
            extract('year', FinanceDiary.today) == year,
            extract('month', FinanceDiary.today) == month
        ).order_by(FinanceDiary.created_at.desc(), FinanceDiary.id.desc()).all()
        print(f"DEBUG get_monthly_diary - Child ID {child_pk}: Found {len(diaries)} diaries")
    
    if diaries:
        print(f"DEBUG get_monthly_diary - Sample diary: {[(d.diary_detail, d.transaction_type, d.amount, d.category) for d in diaries[:3]]}")
    
    return MonthlyDiaryResponse(
        diary=[FinanceDiaryResponse.model_validate(d) for d in diaries]
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



# === 일일 결산 ===
@router.post("/daily/{child_id}/")
async def create_daily_summary(
    child_id: int,
    summary_request: DailySummaryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """일일 결산 생성/조회"""
    date = summary_request.date
    chat_id = summary_request.chat_id
    
    if chat_id:
        return _create_daily_summary_content(db, child_id, date, chat_id)
    
    parent = current_user
    if child_id == parent.id:
        child = db.query(User).filter(User.id == child_id).first()
    else:
        child = db.query(User).filter(
            User.id == child_id,
            User.parents_id == parent.id
        ).first()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당하는 자녀를 찾을 수 없습니다."
        )
    
    today = datetime.now().date()
    
    existing = db.query(DailySummary).filter(
        DailySummary.child_id == child.id,
        DailySummary.parent_id == parent.id,
        DailySummary.today == date
    ).first()
    
    should_refresh = True
    
    if existing and date < today:
        should_refresh = False
        
    if existing and date == today:
        if _check_ai_called_today(db, child.id, 'daily', date.year, date.month, date.day):
            should_refresh = False

    if not should_refresh and existing:
        return json.loads(existing.content) if isinstance(existing.content, str) else existing.content
    
    summary_content = _create_daily_summary_content(db, child.id, date, None)
    
    if summary_content and "message" not in summary_content:
        _increment_ai_usage(db, child.id, 'daily', date.year, date.month, date.day)
        
    if existing:
        existing.content = json.dumps(summary_content, ensure_ascii=False)
        existing.updated_at = datetime.now()
    else:
        new_summary = DailySummary(
            child_id=child.id,
            parent_id=parent.id,
            today=date,
            content=json.dumps(summary_content, ensure_ascii=False)
        )
        db.add(new_summary)
        
    db.commit()
    return summary_content


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
    chat_id = summary_request.chat_id
    
    # chat_id가 있으면 해당 채팅방의 모든 데이터 조회 (단순 조회이므로 저장/제한 로직 제외 가능하나 일단 적용)
    if chat_id:
        summary_content = _create_summary_content(db, child_id, year, month, chat_id)
        return summary_content
    
    # chat_id가 없으면 기존 로직 (자녀 개인 데이터)
    parent = current_user
    
    # 자녀 조회
    if child_id == parent.id:
        # 본인(부모/독립 사용자)인 경우
        child = db.query(User).filter(User.id == child_id).first()
    else:
        # 자녀인 경우
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
    
    # 기존 데이터 조회
    existing = db.query(MonthlySummary).filter(
        MonthlySummary.child_id == child.id,
        MonthlySummary.parent_id == parent.id,
        MonthlySummary.year == year,
        MonthlySummary.month == month
    ).first()

    # 로직 변경:
    # 1. 이미 저장된 데이터가 있고, (오늘 AI를 호출했거나 OR 과거 월 데이터인 경우) -> 저장된 데이터 반환
    # 2. 그렇지 않으면 -> 새로 생성 -> 카운팅 -> 저장
    
    should_refresh = True
    
    # 과거 월 데이터가 이미 존재하면 새로고침 안 함 (원하면 강제 새로고침 API 별도 필요)
    if existing and (year < current_year or (year == current_year and month < current_month)):
        should_refresh = False
        
    # 현재 월 데이터가 있고, 오늘 이미 AI를 호출했다면 새로고침 안 함
    if existing and (year == current_year and month == current_month):
        if _check_ai_called_today(db, child.id, 'monthly', year, month):
            should_refresh = False

    if not should_refresh and existing:
        return json.loads(existing.content) if isinstance(existing.content, str) else existing.content
        
    # 새로 생성
    summary_content = _create_summary_content(db, child.id, year, month, None, child.first_name)
    
    # AI 사용 카운트 증가 (메시지가 없거나 에러가 아닌 경우)
    if summary_content and "message" not in summary_content: # TODO: 에러 체크 더 정교하게?
         _increment_ai_usage(db, child.id, 'monthly', year, month)
    
    # 저장 또는 업데이트
    if existing:
        existing.content = json.dumps(summary_content, ensure_ascii=False)
        existing.updated_at = datetime.now() # 수동 업데이트
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



def _create_daily_summary_content(db: Session, child_id_or_user_id: int, date_obj: date, chat_id: Optional[int] = None) -> dict:
    """일일 결산 내용 생성"""
    user = db.query(User).filter(User.id == child_id_or_user_id).first()
    if not user:
        return {"message": "사용자를 찾을 수 없습니다."}
    
    child_name = user.first_name
    child_age = calculate_age(user.birthday) if user.birthday else "Unknown"
    is_adult = user.parents_id is None
    target_audience = "adults" if is_adult else "children"
    
    # 기입장 조회
    if chat_id:
        diaries = db.query(FinanceDiary).filter(
            FinanceDiary.kakao_chat_id == chat_id,
            FinanceDiary.today == date_obj
        ).all()
    else:
        diaries = db.query(FinanceDiary).filter(
            FinanceDiary.child_id == child_id_or_user_id,
            FinanceDiary.today == date_obj
        ).all()
        
    if not diaries:
        return {
            "username": child_name,
            "age": child_age,
            "message": f"{date_obj} 기록된 내역이 없습니다."
        }
        
    total_income = sum(float(d.amount) for d in diaries if d.transaction_type == '수입')
    total_expenditure = sum(float(d.amount) for d in diaries if d.transaction_type == '지출')
    
    category_expenditure = {}
    for diary in diaries:
        if diary.transaction_type == '지출':
            cat = diary.category
            category_expenditure[cat] = category_expenditure.get(cat, 0) + float(diary.amount)
            
    # OpenAI 요약 생성
    client = OpenAI(
        base_url=settings.OPENAI_ENDPOINT,
        api_key=settings.GITHUB_TOKEN,
    )
    
    system_content = (
        f"You are a financial advisor for {target_audience}. "
        f"Here are the daily financial records for {child_name} ({child_age} years old) on {date_obj}:\n"
        f"{[f'{d.diary_detail} ({d.transaction_type}): {d.amount} KRW' for d in diaries]}\n\n"
        f"Respond entirely in Korean. Provide JSON:\n"
        f"1. 총_수입: {total_income}\n"
        f"2. 총_지출: {total_expenditure}\n"
        f"3. 남은_금액: {total_income - total_expenditure}\n"
        f"4. 카테고리별_지출: {category_expenditure}\n"
        f"5. 가장_많이_지출한_카테고리\n"
    )
    
    if is_adult:
        system_content += "6. 일일_평가 (Evaluation and friendly advice, within 300 characters)\n"
    else:
        system_content += "6. 일일_평가 (Friendly advice for parent about child's spending, within 300 characters)\n"
        
    messages = [{"role": "system", "content": system_content}]
    
    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL_NAME,
            messages=messages,
            max_tokens=1500,
            temperature=0.7
        )
        chat_response = response.choices[0].message.content
        json_str = chat_response.strip().strip('`').strip()
        if json_str.startswith('json'):
            json_str = json_str[4:].strip()
        if json_str.startswith('json'):
            json_str = json_str[4:].strip()
        summary_data = json.loads(json_str)
    except RateLimitError as e:
        log_rate_limit_error(str(e))
        most_expensive = max(category_expenditure.items(), key=lambda x:x[1])[0] if category_expenditure else "없음"
        summary_data = {
            "총_수입": total_income,
            "총_지출": total_expenditure,
            "남은_금액": total_income - total_expenditure,
            "카테고리별_지출": category_expenditure,
            "가장_많이_지출한_카테고리": most_expensive,
            "일일_평가": f"AI 서비스 지연으로 기본 요약만 제공됩니다. 오늘 총 {total_expenditure}원을 사용했습니다."
        }
    except Exception as e:
        print(f"DEBUG - Daily Summary Error: {e}")
        most_expensive = max(category_expenditure.items(), key=lambda x:x[1])[0] if category_expenditure else "없음"
        summary_data = {
            "총_수입": total_income,
            "총_지출": total_expenditure,
            "남은_금액": total_income - total_expenditure,
            "카테고리별_지출": category_expenditure,
            "가장_많이_지출한_카테고리": most_expensive,
            "일일_평가": f"오늘 하루 총 {total_expenditure}원을 사용했습니다."
        }
        
    return {
        "username": child_name,
        "age": child_age,
        "summary": summary_data
    }


def _create_summary_content(db: Session, child_id_or_user_id: int, year: int, month: int, chat_id: Optional[int] = None, child_name: Optional[str] = None) -> dict:
    """월말 결산 내용 생성"""
    from sqlalchemy import extract
    
    # 자녀 정보 먼저 조회
    user = db.query(User).filter(User.id == child_id_or_user_id).first()
    if not user:
        return {"message": f"사용자를 찾을 수 없습니다."}
    
    child_name = child_name or user.first_name
    child_age = calculate_age(user.birthday) if user.birthday else "Unknown"
    is_adult = user.parents_id is None
    target_audience = "adults" if is_adult else "children"
    
    # 기입장 조회
    if chat_id:
        # 채팅방 기준 조회: 해당 채팅방의 모든 멤버 데이터
        diaries = db.query(FinanceDiary).filter(
            FinanceDiary.kakao_chat_id == chat_id,
            extract('year', FinanceDiary.today) == year,
            extract('month', FinanceDiary.today) == month
        ).all()
        print(f"DEBUG - Chat ID {chat_id}: Found {len(diaries)} diaries")
    else:
        # 자녀 개인 기준 조회
        diaries = db.query(FinanceDiary).filter(
            FinanceDiary.child_id == child_id_or_user_id,
            extract('year', FinanceDiary.today) == year,
            extract('month', FinanceDiary.today) == month
        ).all()
        print(f"DEBUG - Child ID {child_id_or_user_id}: Found {len(diaries)} diaries")
    
    if not diaries:
        return {
            "username": child_name,
            "age": child_age,
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
    
    print(f"DEBUG - Total income: {total_income}, Total expense: {total_expenditure}")
    print(f"DEBUG - Category expenses: {category_expenditure}")
    print(f"DEBUG - Diaries detail: {[(d.diary_detail, d.transaction_type, float(d.amount)) for d in diaries]}")
    
    # OpenAI 요약 생성
    client = OpenAI(
        base_url=settings.OPENAI_ENDPOINT,
        api_key=settings.GITHUB_TOKEN,
    )
    
    system_content = (
        f"You are a financial advisor for {target_audience}. You are given financial records for {child_name}, a {child_age}-year-old. "
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
    )

    if is_adult:
        system_content += f"6. 지출_패턴_평가 (Evaluation of the spending pattern and Friendly advice for improvement, within 400 characters)\n"
    else:
        system_content += f"6. 지출_패턴_평가 (Don't say kid's name. Say just kid and Evaluation of the spending pattern and Friendly advice for improvement to parent, within 400 characters)\n"

    messages = [
        {
            "role": "system",
            "content": system_content
        }
    ]
    
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL_NAME,
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
    except RateLimitError as e:
        log_rate_limit_error(str(e))
        most_expensive = max(category_expenditure.items(), key=lambda x: x[1])[0] if category_expenditure else "없음"
        summary_data = {
            "총_수입": total_income,
            "총_지출": total_expenditure,
            "남은_금액": total_income - total_expenditure,
            "카테고리별_지출": category_expenditure,
            "가장_많이_지출한_카테고리": most_expensive,
            "지출_패턴_평가": f"AI 서비스 지연으로 기본 요약만 제공됩니다. 이번 달 {total_expenditure}원을 지출했습니다."
        }
    except json.JSONDecodeError as e:
        print(f"DEBUG - JSON Parse Error in _create_summary_content: {e}")
        print(f"DEBUG - Raw response: {chat_response[:500]}...")
        # JSON 파싱 실패시 기본값으로 데이터 생성
        most_expensive = max(category_expenditure.items(), key=lambda x: x[1])[0] if category_expenditure else "없음"
        summary_data = {
            "총_수입": total_income,
            "총_지출": total_expenditure,
            "남은_금액": total_income - total_expenditure,
            "카테고리별_지출": category_expenditure,
            "가장_많이_지출한_카테고리": most_expensive,
            "지출_패턴_평가": f"이번 달 총 {total_income}원의 수입이 있었고, {total_expenditure}원을 지출했습니다."
        }
    
    return {
        "username": child_name,
        "age": child_age,
        "summary": summary_data
    }


# === 연말 결산 ===
@router.post("/yearly/{child_id}/")
async def create_yearly_summary(
    child_id: int,
    summary_request: YearlySummaryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """연말 결산 생성/조회"""
    year = summary_request.year
    chat_id = summary_request.chat_id
    
    # chat_id가 있으면 해당 채팅방의 모든 데이터 조회
    if chat_id:
        summary_content = _create_yearly_summary_content(db, child_id, year, chat_id)
        return summary_content
    
    parent = current_user
    
    # 자녀 조회
    if child_id == parent.id:
        child = db.query(User).filter(User.id == child_id).first()
    else:
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
    
    # 기존 데이터 조회
    existing = db.query(YearlySummary).filter(
        YearlySummary.child_id == child.id,
        YearlySummary.parent_id == parent.id,
        YearlySummary.year == year
    ).first()
    
    should_refresh = True
    
    # 과거 연도 데이터가 이미 존재하면 새로고침 안 함
    if existing and year < current_year:
        should_refresh = False
        
    # 현재 연도 데이터가 있고, 오늘 이미 AI를 호출했다면 새로고침 안 함
    if existing and year == current_year:
        if _check_ai_called_today(db, child.id, 'yearly', year):
            should_refresh = False

    if not should_refresh and existing:
         return json.loads(existing.content) if isinstance(existing.content, str) else existing.content
         
    # 새로 생성
    summary_content = _create_yearly_summary_content(db, child.id, year, None)
    
    # AI 사용 카운트 증가
    if summary_content and "message" not in summary_content:
        _increment_ai_usage(db, child.id, 'yearly', year)
    
    # 저장 또는 업데이트
    if existing:
        existing.content = json.dumps(summary_content, ensure_ascii=False)
        existing.updated_at = datetime.now()
    else:
        new_summary = YearlySummary(
            child_id=child.id,
            parent_id=parent.id,
            year=year,
            content=json.dumps(summary_content, ensure_ascii=False)
        )
        db.add(new_summary)
    
    db.commit()
    return summary_content


def _create_yearly_summary_content(db: Session, child_id_or_user_id: int, year: int, chat_id: Optional[int] = None) -> dict:
    """연말 결산 내용 생성"""
    from sqlalchemy import extract
    
    # 자녀 정보 먼저 조회
    user = db.query(User).filter(User.id == child_id_or_user_id).first()
    if not user:
        return {"message": f"사용자를 찾을 수 없습니다."}
    
    child_name = user.first_name
    child_age = calculate_age(user.birthday) if user.birthday else "Unknown"
    is_adult = user.parents_id is None
    target_audience = "adults" if is_adult else "children"
    
    # 기입장 조회
    if chat_id:
        # 채팅방 기준 조회: 해당 채팅방의 모든 멤버 데이터
        diaries = db.query(FinanceDiary).filter(
            FinanceDiary.kakao_chat_id == chat_id,
            extract('year', FinanceDiary.today) == year
        ).all()
    else:
        # 자녀 개인 기준 조회
        diaries = db.query(FinanceDiary).filter(
            FinanceDiary.child_id == child_id_or_user_id,
            extract('year', FinanceDiary.today) == year
        ).all()
    
    if not diaries:
        return {
            "username": child_name,
            "age": child_age,
            "message": f"{year}년 용돈기입장 기록이 없습니다."
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
    
    # 월별 데이터 집계
    monthly_data = {}
    for diary in diaries:
        month = diary.today.month
        if month not in monthly_data:
            monthly_data[month] = {"income": 0, "expense": 0}
        if diary.transaction_type == '수입':
            monthly_data[month]["income"] += float(diary.amount)
        else:
            monthly_data[month]["expense"] += float(diary.amount)
    
    # 가장 지출이 많은 달
    max_expense_month = max(monthly_data.items(), key=lambda x: x[1]["expense"], default=(0, {"expense": 0}))
    
    # OpenAI 요약 생성
    client = OpenAI(
        base_url=settings.OPENAI_ENDPOINT,
        api_key=settings.GITHUB_TOKEN,
    )
    
    is_adult = child.parents_id is None
    target_audience = "adults" if is_adult else "children"
    
    system_content = (
        f"You are a financial advisor for {target_audience}. You are given a full year's financial records for {child_name}, a {child_age}-year-old. "
        f"Each record has a transaction_type field, which indicates whether the transaction is an '수입' (income) or '지출' (expense). "
        f"Respond entirely in Korean. "
        f"Here is the annual summary:\n"
        f"- 총 기록 수: {len(diaries)}건\n"
        f"- 연간 총 수입: {total_income:,.0f}원\n"
        f"- 연간 총 지출: {total_expenditure:,.0f}원\n"
        f"- 연간 잔액: {total_income - total_expenditure:,.0f}원\n"
        f"- 카테고리별 지출: {category_expenditure}\n"
        f"- 월별 데이터: {monthly_data}\n\n"
        f"Please provide the following information in JSON format:\n"
        f"1. 총_수입 (Total annual income): {total_income}\n"
        f"2. 총_지출 (Total annual expenditure): {total_expenditure}\n"
        f"3. 남은_금액 (Remaining amount): {total_income - total_expenditure}\n"
        f"4. 카테고리별_지출 (Expenditure by category): {category_expenditure}\n"
        f"5. 가장_많이_지출한_카테고리 (Category with the highest expenditure)\n"
        f"6. 가장_지출이_많은_달 (Month with the highest expenditure): {max_expense_month[0]}월\n"
        f"7. 월별_데이터 (Monthly data): {monthly_data}\n"
    )

    if is_adult:
        system_content += f"8. 연간_평가 (Annual evaluation and friendly advice for improvement, within 500 characters)\n"
    else:
        system_content += f"8. 연간_평가 (Don't say kid's name. Say just kid and Annual evaluation and friendly advice for parents, within 500 characters)\n"

    messages = [
        {
            "role": "system",
            "content": system_content
        }
    ]
    
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL_NAME,
        messages=messages,
        max_tokens=3000,
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
    except RateLimitError as e:
        log_rate_limit_error(str(e))
        most_expensive = max(category_expenditure.items(), key=lambda x: x[1])[0] if category_expenditure else "없음"
        summary_data = {
            "총_수입": total_income,
            "총_지출": total_expenditure,
            "남은_금액": total_income - total_expenditure,
            "카테고리별_지출": category_expenditure,
            "가장_많이_지출한_카테고리": most_expensive,
            "연간_평가": f"AI 서비스 지연으로 기본 요약만 제공됩니다. 올 한해 {total_expenditure}원을 지출했습니다."
        }
    except json.JSONDecodeError as e:
        print(f"DEBUG - JSON Parse Error in _create_yearly_summary_content: {e}")
        print(f"DEBUG - Raw response: {chat_response[:500]}...")
        # JSON 파싱 실패시 기본값으로 데이터 생성
        most_expensive = max(category_expenditure.items(), key=lambda x: x[1])[0] if category_expenditure else "없음"
        summary_data = {
            "총_수입": total_income,
            "총_지출": total_expenditure,
            "남은_금액": total_income - total_expenditure,
            "카테고리별_지출": category_expenditure,
            "가장_많이_지출한_카테고리": most_expensive,
            "연간_평가": f"올 한해 총 {total_income}원의 수입이 있었고, {total_expenditure}원을 지출했습니다."
        }
    
    return {
        "username": child_name,
        "age": child_age,
        "summary": summary_data
    }
