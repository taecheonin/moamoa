import os
from datetime import datetime
from ..config import settings

def log_rate_limit_error(error_message: str):
    """GitHub Token 사용 한도 초과 에러 로깅"""
    log_dir = settings.LOGS_DIR
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file = log_dir / "rate_limit_errors.log"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Rate Limit Exceeded: {error_message}\n")
