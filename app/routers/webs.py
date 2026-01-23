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
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    # """부모 프로필 대시보드 및 리포트 섹션"""
    # if not current_user:
    #     return RedirectResponse(url="/", status_code=302)
    # 
    # # 자녀 계정인 경우
    # if current_user.parents_id is not None:
    #     # 자신의 리포트를 보는 것이 아니라면 자녀 프로필 페이지로 이동
    #     if child_id and current_user.id == child_id:
    #         return templates.TemplateResponse("profile.html", {"request": request})
    #     elif not child_id:
    #         return RedirectResponse(url="/child_profile/", status_code=302)
    #     else:
    #         # 타인의 리포트 접근 시 차단 (보안)
    #         return RedirectResponse(url="/child_profile/", status_code=302)
    #
    # return templates.TemplateResponse("profile.html", {"request": request})

    if not current_user:
        return RedirectResponse(url="/", status_code=302)
        
    # child_id가 없으면 메인(홈)으로 리다이렉트
    if not child_id:
        return RedirectResponse(url="/", status_code=302)
        
    return templates.TemplateResponse("profile.html", {"request": request})


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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """현재 세션 사용자의 프로필 페이지"""
    return templates.TemplateResponse(
        "children_profile.html",
        {"request": request, "child": current_user}
    )





# 챗봇 페이지
@router.get("/chatbot/{child_pk}/", response_class=HTMLResponse)
async def chatbot(
    request: Request,
    child_pk: int,
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
            "child_pk": child_pk
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
