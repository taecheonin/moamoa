#!/usr/bin/env python
"""
kakao_utterances 테이블에 bot_response와 date 열 추가하기
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from app.database import engine
from sqlalchemy import text

def migrate():
    """테이블에 열 추가"""
    with engine.connect() as conn:
        try:
            # bot_response 열 추가
            print("1️⃣ bot_response 열 추가 시도...")
            conn.execute(text("ALTER TABLE kakao_utterances ADD COLUMN bot_response LONGTEXT NULL"))
            conn.commit()
            print("✅ bot_response 열 추가 완료")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print("⚠️ bot_response 열이 이미 존재합니다")
            else:
                print(f"❌ 에러: {e}")
        
        try:
            # date 열 추가
            print("\n2️⃣ date 열 추가 시도...")
            conn.execute(text("ALTER TABLE kakao_utterances ADD COLUMN date DATE NULL INDEX"))
            conn.commit()
            print("✅ date 열 추가 완료")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print("⚠️ date 열이 이미 존재합니다")
            else:
                print(f"❌ 에러: {e}")
        
        # 테이블 구조 확인
        print("\n3️⃣ 현재 kakao_utterances 테이블 구조:")
        result = conn.execute(text("DESCRIBE kakao_utterances"))
        for row in result:
            print(f"  {row}")

if __name__ == "__main__":
    migrate()
