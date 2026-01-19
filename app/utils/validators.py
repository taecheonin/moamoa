"""
유효성 검사 유틸리티
Django의 accounts.validators를 FastAPI용으로 변환
"""
import hashlib
import re
from typing import Tuple, List, Optional
from sqlalchemy.orm import Session

from ..models.user import User


def validate_signup(db: Session, user_data: dict) -> Tuple[bool, List[dict]]:
    """
    회원가입 유효성 검사
    
    Args:
        db: 데이터베이스 세션
        user_data: 회원가입 데이터
    
    Returns:
        (유효성 여부, 에러 메시지 리스트)
    """
    err_msg = []
    
    # validate_username
    username = user_data.get("username")
    if username:
        if db.query(User).filter(User.username == username).first():
            err_msg.append({"username": ["이미 존재하는 아이디입니다."]})
    
    # validate_password
    password = user_data.get("password")
    password2 = user_data.get("password2")
    
    if password != password2:
        err_msg.append({"password": ["비밀번호가 일치하지 않습니다."]})
    else:
        # 비밀번호 유효성 검사
        is_valid, error = custom_validate_password(password)
        if not is_valid:
            err_msg.append({"password": [error]})
    
    # validate_email
    email = user_data.get("email")
    if email:
        if db.query(User).filter(User.email == email).first():
            err_msg.append({"email": "이미 존재하는 이메일입니다."})
        else:
            # 이메일 형식 검사
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, email):
                err_msg.append({"email": "이메일 형식이 올바르지 않습니다."})
    
    if err_msg:
        return False, err_msg
    return True, err_msg


def custom_validate_password(password: str) -> Tuple[bool, Optional[str]]:
    """
    비밀번호 유효성 검사
    
    Args:
        password: 검사할 비밀번호
    
    Returns:
        (유효성 여부, 에러 메시지)
    """
    if not password:
        return False, "비밀번호를 입력해주세요."
    
    if len(password) < 8:
        return False, "비밀번호는 8자 이상이어야 합니다."
    
    has_letter = any(c.isalpha() for c in password)
    has_number = any(c.isdigit() for c in password)
    
    if not (has_letter and has_number):
        return False, "비밀번호는 문자와 숫자를 모두 포함해야 합니다."
    
    for i in range(len(password) - 3):
        if password[i] == password[i+1] == password[i+2] == password[i+3]:
            return False, "동일한 문자를 4번 이상 연속해서 사용할 수 없습니다."
    
    return True, None


def verify_django_password(password: str, encoded: str) -> bool:
    """
    Django PBKDF2 형식의 비밀번호 검증
    
    Django 비밀번호 형식: algorithm$iterations$salt$hash
    """
    try:
        algorithm, iterations, salt, hash_value = encoded.split('$')
        
        if algorithm != 'pbkdf2_sha256':
            return False
        
        iterations = int(iterations)
        
        import hashlib
        import base64
        
        # PBKDF2로 비밀번호 해싱
        dk = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            iterations,
            dklen=32
        )
        
        # Base64 인코딩
        computed_hash = base64.b64encode(dk).decode('utf-8')
        
        # 비교
        return computed_hash == hash_value
    except Exception:
        return False


def hash_password_django(password: str, salt: Optional[str] = None, iterations: int = 720000) -> str:
    """
    Django PBKDF2 형식으로 비밀번호 해싱
    """
    import hashlib
    import base64
    import secrets
    
    if salt is None:
        salt = secrets.token_hex(6)  # 12자 솔트
    
    dk = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        iterations,
        dklen=32
    )
    
    hash_value = base64.b64encode(dk).decode('utf-8')
    
    return f"pbkdf2_sha256${iterations}${salt}${hash_value}"
