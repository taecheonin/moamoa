"""
웹 페이지 라우터
Django의 webs.views를 FastAPI + Jinja2로 변환
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import settings
from ..database import get_db
from ..models.user import User
from ..dependencies import get_current_user, get_current_user_optional, decode_token

router = APIRouter(tags=["webs"])

# Jinja2 환경 설정 (Django 호환성을 위한 커스텀 설정)
def create_jinja2_env():
    """Django 템플릿 호환을 위한 Jinja2 환경 생성"""
    env = Environment(
        loader=FileSystemLoader(str(settings.TEMPLATES_DIR)),
        autoescape=select_autoescape(['html', 'xml']),
        # Django 호환 블록 태그 설정
        block_start_string='{%',
        block_end_string='%}',
        variable_start_string='{{',
        variable_end_string='}}',
        comment_start_string='{#',
        comment_end_string='#}',
    )
    
    # static 함수 추가 (Django의 {% static %} 대체)
    def static(path: str) -> str:
        return f"/static/{path}"

    
    env.globals['static'] = static
    
    return env

# 커스텀 Jinja2 환경
jinja_env = create_jinja2_env()

# Jinja2 템플릿 설정
templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))
templates.env = jinja_env


def get_base_url(request: Request) -> str:
    """기본 URL 반환"""
    return str(request.base_url).rstrip('/')


# 홈페이지
@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """메인 페이지"""
    return templates.TemplateResponse("index.html", {"request": request})


# 키즈 로그인 페이지
@router.get("/login/", response_class=HTMLResponse)
async def children_login(request: Request):
    """키즈 로그인 페이지"""
    return templates.TemplateResponse("children.html", {"request": request})


# 부모 프로필
@router.get("/profile/", response_class=HTMLResponse)
async def profile(
    request: Request,
    child_id: Optional[int] = None,
    report_type: Optional[str] = None,  # daily, monthly, yearly
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    if not current_user:
        return RedirectResponse(url="/", status_code=302)
        
    # child_id가 없으면 메인(홈)으로 리다이렉트
    if not child_id:
        return RedirectResponse(url="/", status_code=302)
        
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "report_type": report_type or "monthly",
        "child_id": child_id,
        "view_mode": "dashboard" # 기본은 대시보드 모드
    })


# 일일결산 페이지
@router.get("/profile/daily/{child_id}/", response_class=HTMLResponse)
async def profile_daily(
    request: Request,
    child_id: int,
    chat_id: Optional[int] = None,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    if not current_user:
        return RedirectResponse(url="/", status_code=302)
        
    return templates.TemplateResponse("profile_daily.html", {
        "request": request,
        "child_id": child_id,
        "chat_id": chat_id,
        "view_mode": "report"
    })


# 월말결산 페이지
@router.get("/profile/monthly/{child_id}/", response_class=HTMLResponse)
async def profile_monthly(
    request: Request,
    child_id: int,
    chat_id: Optional[int] = None,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    if not current_user:
        return RedirectResponse(url="/", status_code=302)
        
    return templates.TemplateResponse("profile_monthly.html", {
        "request": request,
        "child_id": child_id,
        "chat_id": chat_id,
        "view_mode": "report"
    })


# 연말결산 페이지
@router.get("/profile/yearly/{child_id}/", response_class=HTMLResponse)
async def profile_yearly(
    request: Request,
    child_id: int,
    chat_id: Optional[int] = None,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    if not current_user:
        return RedirectResponse(url="/", status_code=302)
        
    return templates.TemplateResponse("profile_yearly.html", {
        "request": request,
        "child_id": child_id,
        "chat_id": chat_id,
        "view_mode": "report"
    })


# 부모 프로필 상세 (레거시 리다이렉트)
@router.get("/profile/{pk}/", response_class=HTMLResponse)
async def profile_detail(
    request: Request, 
    pk: int,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """자녀 ID 경로 접근 시 쿼리 파라미터 방식으로 리다이렉트"""
    if not current_user:
        return RedirectResponse(url="/", status_code=302)
    return RedirectResponse(url=f"/profile/?child_id={pk}", status_code=301)


# 키즈 계정 생성
@router.get("/signup/", response_class=HTMLResponse)
async def signup(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """키즈 계정 회원가입 페이지"""
    # 로그인 확인
    if not current_user:
        return RedirectResponse(url="/", status_code=302)
    
    return templates.TemplateResponse("children_create.html", {"request": request})


# 키즈 프로필 (URL에 ID 노출 안 함)
@router.get("/child_profile/", response_class=HTMLResponse)
async def child_profile_index(
    request: Request,
    child_id: Optional[int] = None,
    chat_id: Optional[int] = None,  # 채팅방 ID (카카오에서 넘어올 때 사용)
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """현재 세션 사용자의 프로필 페이지 (또는 부모가 자녀 페이지 조회)"""
    target_child = current_user
    is_parent_viewing = False

    # URL에 chat_id가 있는 경우 쿠키에 저장하고 리다이렉트 (주소창 숨김 처리)
    if chat_id is not None:
        # 쿼리 파라미터 재구성 (chat_id 제외)
        redirect_url = "/child_profile/"
        if child_id:
            redirect_url += f"?child_id={child_id}"
            
        response = RedirectResponse(url=redirect_url, status_code=303)
        # chat_id 쿠키 설정 (유효기간: 브라우저 종료 시까지)
        response.set_cookie(key="chat_id", value=str(chat_id), httponly=True)
        return response

    # 쿼리 파라미터가 없는 경우 쿠키에서 chat_id 확인
    if chat_id is None:
        cookie_chat_id = request.cookies.get("chat_id")
        if cookie_chat_id:
            try:
                chat_id = int(cookie_chat_id)
            except (ValueError, TypeError):
                pass
    
    # 보안 점검: chat_id가 유효하고 현재 사용자가 해당 채팅방의 멤버인지 확인
    if chat_id:
        # KakaoChatMember 모델 import 필요 (함수 내부 import로 해결하거나 상단 추가)
        from ..models.kakao import KakaoChatMember
        
        # 현재 사용자의 Kakao Key가 존재하는지 확인 (username 필드가 kakao key라고 가정)
        # 또는 User 모델에 kakao_user_key 필드가 있는지 확인 필요.
        # 기존 로직에서 username을 사용하는 경우가 많으므로 username 시도.
        member_check = db.query(KakaoChatMember).filter(
            KakaoChatMember.chat_id == chat_id,
            KakaoChatMember.user_key == current_user.username 
        ).first()

        # 만약 멤버가 아니면 chat_id 무시 (보안상 다른 사람 거 조회 불가)
        if not member_check:
             # 부모의 경우, 자녀가 멤버인지 확인해야 함
             if current_user.is_parent:
                 # 자녀들 중 하나라도 멤버인지 확인
                 children = db.query(User).filter(User.parents_id == current_user.id).all()
                 is_child_chat = False
                 for child in children:
                     child_member = db.query(KakaoChatMember).filter(
                         KakaoChatMember.chat_id == chat_id,
                         KakaoChatMember.user_key == child.username
                     ).first()
                     if child_member:
                         is_child_chat = True
                         break
                 
                 if not is_child_chat:
                     chat_id = None # 권한 없음
             else:
                 chat_id = None # 권한 없음

    if child_id and child_id != current_user.id:
        # 자녀 조회 시도
        child_obj = db.query(User).filter(User.id == child_id).first()
        if not child_obj:
             raise HTTPException(status_code=404, detail="User not found")
        
        # 권한 확인 (부모인지)
        if child_obj.parents_id == current_user.id:
            target_child = child_obj
            is_parent_viewing = True
        else:
            return RedirectResponse(url="/access-error/", status_code=302)

    return templates.TemplateResponse(
        "children_profile.html",
        {
            "request": request, 
            "child": target_child, 
            "chat_id": chat_id,
            "is_parent_viewing": is_parent_viewing
        }
    )





# 챗봇 페이지
@router.get("/chatbot/{child_pk}/", response_class=HTMLResponse)
async def chatbot(
    request: Request,
    child_pk: int,
    chat_id: Optional[int] = None,  # 채팅방 ID 추가
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """용돈기입장 챗봇 페이지"""
    # 1. 로그인 확인
    if not current_user:
        return RedirectResponse(url="/login/", status_code=302)
    
    # 2. 아이 정보 조회
    user = db.query(User).filter(User.id == child_pk).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    
    # 3. 권한 확인 (본인이거나 부모인 경우만 허용)
    if current_user.id != user.id and user.parents_id != current_user.id:
        return RedirectResponse(url="/access-error/", status_code=302)
    
    base_url = get_base_url(request)
    user_image = f"{base_url}/media/{user.images}" if user.images else f"{base_url}/media/default_profile.png"
    
    return templates.TemplateResponse(
        "chatbot.html",
        {
            "request": request,
            "user": user,
            "user_image": user_image,
            "child_pk": child_pk,
            "chat_id": chat_id  # 템플릿에 전달
        }
    )


# 보안 토큰 검증 섹션 (Intermediary)
@router.get("/verify-token/", response_class=HTMLResponse)
async def verify_token_page(request: Request, token: str, next: Optional[str] = None):
    """토큰 검증 및 자동 로그인을 위한 중간 페이지"""
    return templates.TemplateResponse(
        "verify_token.html", 
        {"request": request, "token": token, "next": next}
    )


# 접근 오류 페이지
@router.get("/access-error/", response_class=HTMLResponse)
async def access_error(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """접근 오류 페이지"""
    return templates.TemplateResponse(
        "access_error.html",
        {"request": request, "logged_in_user": current_user}
    )
