"""
계정 관련 API 라우터
Django의 accounts.views를 FastAPI용으로 변환
"""
import hashlib
import requests
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.user import User
from ..schemas.user import (
    LoginRequest, UserCreate, UserUpdate, UserResponse,
    TokenResponse, ParentWithChildrenResponse, ChildWithParentResponse
)
from ..dependencies import (
    get_current_user, get_parent_user, authenticate_user,
    create_access_token, create_refresh_token, decode_token,
    get_refresh_token_from_cookie, decode_magic_token
)
from ..utils.validators import validate_signup, custom_validate_password, hash_password_django

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


# 쿠키 설정 헬퍼 함수
def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """인증 쿠키 설정"""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=False  # 프로덕션에서는 True로 변경
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=False
    )


def delete_auth_cookies(response: Response):
    """인증 쿠키 삭제"""
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    response.delete_cookie("sessionid")


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


# === 카카오 OAuth 콜백 ===
@router.get("/auth/kakao/callback/")
async def kakao_callback(
    request: Request,
    code: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """카카오 OAuth 콜백 처리 (부모 회원가입/로그인)"""
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="인증 코드가 없습니다"
        )
    
    # 카카오 토큰 요청
    token_url = (
        f"https://kauth.kakao.com/oauth/token?"
        f"grant_type=authorization_code&"
        f"client_id={settings.REST_API_KEY}&"
        f"client_secret={settings.CLIENT_SECRET}&"
        f"redirect_uri={settings.KAKAO_CALLBACK_URI}&"
        f"code={code}"
    )
    token_response = requests.get(token_url)
    token_json = token_response.json()
    
    if "error" in token_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=token_json.get("error")
        )
    
    kakao_access_token = token_json.get("access_token")
    
    # 카카오 프로필 요청
    profile_response = requests.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {kakao_access_token}"}
    )
    profile_data = profile_response.json()
    
    kakao_account = profile_data.get("kakao_account")
    if not kakao_account or not kakao_account.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="등록하려면 이메일이 필요합니다."
        )
    
    kakao_id = str(profile_data.get("id"))
    email = kakao_account.get("email")
    nickname = kakao_account["profile"]["nickname"]
    profile_image_url = kakao_account["profile"].get("profile_image_url")
    
    # 비밀번호 해시 생성
    hash_object = hashlib.sha256(kakao_id.encode())
    password_hash = hash_object.hexdigest()
    
    # 사용자 조회 또는 생성
    user = db.query(User).filter(User.username == kakao_id).first()
    
    if not user:
        # 새 사용자 생성
        user = User(
            username=kakao_id,
            email=email,
            first_name=nickname,
            password=hash_password_django(password_hash),
            is_active=True,
            date_joined=datetime.utcnow().isoformat()
        )
        db.add(user)
        
        # 프로필 이미지 저장
        if profile_image_url:
            try:
                img_response = requests.get(profile_image_url)
                if img_response.status_code == 200:
                    image_name = f"{kakao_id}_profile_image.jpg"
                    image_path = settings.MEDIA_DIR / "profile_images" / image_name
                    image_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(image_path, "wb") as f:
                        f.write(img_response.content)
                    user.images = f"profile_images/{image_name}"
            except Exception:
                pass
        
        db.commit()
        db.refresh(user)
    
    # JWT 토큰 발급
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})
    
    # 프론트엔드로 리다이렉트
    frontend_url = f"{settings.FRONTEND_URL}/profile/"
    response = RedirectResponse(url=frontend_url)
    set_auth_cookies(response, access_token, refresh_token)
    
    return response


# === 아이들 로그인 ===
@router.post("/login/")
async def login(
    login_data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """아이들 로그인"""
    # 사용자명 존재 확인
    user_exists = db.query(User).filter(User.username == login_data.username).first()
    if not user_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="존재하지 않는 아이디입니다."
        )
    
    # 인증
    user = authenticate_user(db, login_data.username, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="패스워드가 틀렸습니다."
        )
    
    # JWT 토큰 발급
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})
    
    # 응답 데이터
    user_data = UserResponse.model_validate(user)
    
    response = Response(
        content=user_data.model_dump_json(),
        media_type="application/json"
    )
    set_auth_cookies(response, access_token, refresh_token)
    
    return response


# === 로그아웃 ===
@router.post("/logout/")
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user)
):
    """로그아웃"""
    # TODO: 리프레시 토큰 블랙리스트 추가 (Redis 또는 DB)
    
    delete_auth_cookies(response)
    return {"message": "로그아웃 되었습니다."}


# === 토큰 갱신 ===
@router.post("/token/refresh/")
async def refresh_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """리프레시 토큰으로 액세스 토큰 갱신"""
    refresh_token = get_refresh_token_from_cookie(request)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="리프레시 토큰이 없습니다."
        )
    
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 리프레시 토큰입니다."
        )
    
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다."
        )
    
    # 새 토큰 발급
    new_access_token = create_access_token(data={"sub": user.id})
    new_refresh_token = create_refresh_token(data={"sub": user.id})
    
    set_auth_cookies(response, new_access_token, new_refresh_token)
    
    return {"access_token": new_access_token, "refresh_token": new_refresh_token}


# === 부모/자녀 조회 ===
@router.get("/", response_model=ParentWithChildrenResponse)
async def get_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """부모와 자녀 목록 조회"""
    if current_user.parents_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="접근 권한이 없습니다."
        )
    
    # 자녀 목록 조회
    children = db.query(User).filter(User.parents_id == current_user.id).all()
    
    return {
        "parent": current_user,
        "children": children
    }


# === 자녀 계정 생성 ===
@router.post("/children/create/", response_model=UserResponse)
async def create_child(
    user_data: UserCreate,
    current_user: User = Depends(get_parent_user),
    db: Session = Depends(get_db)
):
    """자녀 계정 생성"""
    # 유효성 검사
    is_valid, err_msg = validate_signup(db, user_data.model_dump())
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg
        )
    
    # 새 사용자 생성
    new_user = User(
        username=user_data.username,
        password=hash_password_django(user_data.password),
        email=user_data.email or "",
        first_name=user_data.first_name,
        birthday=user_data.birthday,
        parents_id=current_user.id,
        is_active=True,
        date_joined=datetime.utcnow().isoformat()
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user


# === 자녀 상세 조회 ===
@router.get("/children/{pk}/", response_model=ChildWithParentResponse)
async def get_child(
    pk: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """자녀 정보 조회"""
    # 1. 부모 계정인 경우: 자신의 자녀인지 확인
    if current_user.parents_id is None:
        child = db.query(User).filter(
            User.id == pk,
            User.parents_id == current_user.id
        ).first()
        
        if not child:
            # 혹시 자녀 본인이 부모 계정처럼 등록된 사례가 있는지 2차 확인
            if current_user.id == pk:
                child = current_user
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="자녀 정보를 찾을 수 없거나 접근 권한이 없습니다."
                )
    
    # 2. 자녀 계정인 경우: 본인 정보만 조회 가능
    else:
        if current_user.id != pk:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="자신의 정보만 조회할 수 있습니다."
            )
        child = current_user
    
    # 부모 정보 조회
    parent = None
    if child.parents_id:
        parent = db.query(User).filter(User.id == child.parents_id).first()
    
    return {
        "child": child,
        "parent": parent
    }


# === 자녀 정보 수정 ===
@router.put("/children/{pk}/", response_model=UserResponse)
async def update_child(
    pk: int,
    firstname: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    birthday: Optional[str] = Form(None),
    encouragement: Optional[str] = Form(None),
    profile_image: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_parent_user),
    db: Session = Depends(get_db)
):
    """자녀 정보 수정"""
    child = db.query(User).filter(
        User.id == pk,
        User.parents_id == current_user.id
    ).first()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="아이들을 찾을수가 없습니다."
        )
    
    # 비밀번호 수정
    if password:
        is_valid, error_msg = custom_validate_password(password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        child.password = hash_password_django(password)
    
    # 이름 수정
    if firstname:
        child.first_name = firstname
    
    # 생일 수정
    if birthday:
        from datetime import datetime as dt
        child.birthday = dt.strptime(birthday, "%Y-%m-%d").date()
    
    # 격려 메시지 수정
    if encouragement:
        child.encouragement = encouragement
    
    # 프로필 이미지 업로드
    if profile_image:
        image_path = settings.MEDIA_DIR / "profile_images" / profile_image.filename
        image_path.parent.mkdir(parents=True, exist_ok=True)
        with open(image_path, "wb") as f:
            content = await profile_image.read()
            f.write(content)
        child.images = f"profile_images/{profile_image.filename}"
    
    db.commit()
    db.refresh(child)
    
    return child


# === 자녀 삭제 ===
@router.delete("/children/{pk}/")
async def delete_child(
    pk: int,
    current_user: User = Depends(get_parent_user),
    db: Session = Depends(get_db)
):
    """자녀 삭제"""
    child = db.query(User).filter(
        User.id == pk,
        User.parents_id == current_user.id
    ).first()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="아이들을 찾을 수 없습니다."
        )
    
    db.delete(child)
    db.commit()
    
    return {"success": "자녀가 성공적으로 삭제되었습니다."}


# === 카카오 보안 매직 링크 로그인 (GET/POST 모두 허용) ===
@router.api_route("/magic-login/", methods=["GET", "POST"])
async def magic_login(
    request: Request,
    db: Session = Depends(get_db)
):
    """토큰을 이용한 보안 자동 로그인 및 리다이렉트"""
    # POST와 GET 방식 모두에서 토큰 추출 (리다이렉트 시 메서드 유실 대비)
    token = None
    if request.method == "POST":
        try:
            form_data = await request.form()
            token = form_data.get("token")
        except:
            pass
    
    if not token:
        token = request.query_params.get("token")
    
    user_id = decode_magic_token(token) if token else None
    
    
    if not user_id:
    
        return RedirectResponse(url="/", status_code=303)
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
    
        return RedirectResponse(url="/", status_code=303)
    
    
    
    # 세션 토큰(JWT) 발급
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})
    
    # 리다이렉트 경로 확인 (기본값: /child_profile/)
    next_url = request.query_params.get("next", "/child_profile/")
    
    
    
    # 세션 토큰(JWT) 발급
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})
    
    # 지정된 경로 또는 기본 경로로 리다이렉트
    response = RedirectResponse(url=next_url, status_code=303)
    set_auth_cookies(response, access_token, refresh_token)
    
    return response


@router.get("/me/")
async def get_me(current_user: User = Depends(get_current_user)):
    """현재 로그인한 사용자 정보 반환"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "first_name": current_user.first_name,
        "is_parent": current_user.is_parent,
        "total": current_user.total
    }
