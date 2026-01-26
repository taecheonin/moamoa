from fastapi import APIRouter, Request, Depends, BackgroundTasks
import json
import os
import re
from datetime import datetime
from sqlalchemy.orm import Session
from ..config import settings
from ..database import get_db
from ..models.kakao import KakaoChat, KakaoChatMember, KakaoUtterance
import requests
import asyncio
import time
from ..utils.chatbot import chat_with_bot, update_remaining_balance
from ..models.user import User
from ..models.diary import FinanceDiary, KakaoSync
import uuid
from ..utils.validators import hash_password_django
from decimal import Decimal
from ..dependencies import create_magic_token

async def process_callback(callback_url: str, utterance: str, user_id: str, params: dict = None):
    """
    카카오 콜백 URL로 지연된 응답을 보냅니다.
    """

    # 임시로 5초 대기
    await asyncio.sleep(5)

    # 챗봇 응답 받기
    try:
        response_text = chat_with_bot(utterance, user_id)
    except Exception as e:
        response_text = "죄송해요, 지금은 대답하기가 어려워요."

    # 챗봇 응답에서 항목 추출 (Regex)
    # 1. 날짜, 2. 금액, 3. 사용 내역, 4. 분류, 5. 거래 유형
    date_match = re.search(r"1\.\s*(?:<strong>)?날짜(?:</strong>)?:?\s*(.*?)(?:\s*<br>|\n|$)", response_text)
    amount_match = re.search(r"2\.\s*(?:<strong>)?금액(?:</strong>)?:?\s*(.*?)(?:\s*<br>|\n|$)", response_text)
    desc_match = re.search(r"3\.\s*(?:<strong>)?사용 내역(?:</strong>)?:?\s*(.*?)(?:\s*<br>|\n|$)", response_text)
    cat_match = re.search(r"4\.\s*(?:<strong>)?분류(?:</strong>)?:?\s*(.*?)(?:\s*<br>|\n|$)", response_text)
    type_match = re.search(r"5\.\s*(?:<strong>)?거래 유형(?:</strong>)?:?\s*(.*?)(?:\s*<br>|\n|$)", response_text)

    if date_match and amount_match:
        # 데이터가 추출되면 itemCard 형태로 구성
        usage_desc = desc_match.group(1).strip().replace("<strong>","").replace("</strong>","") if desc_match else ""
        item_list = [
            {"title": "날짜", "description": date_match.group(1).strip().replace("<strong>","").replace("</strong>","")},
            {"title": "금액", "description": amount_match.group(1).strip().replace("<strong>","").replace("</strong>","")},
            {"title": "분류", "description": cat_match.group(1).strip().replace("<strong>","").replace("</strong>","") if cat_match else "-"},
            {"title": "거래 유형", "description": type_match.group(1).strip().replace("<strong>","").replace("</strong>","") if type_match else "-"}
        ]
        
        if params:
            if params.get('location'):
                item_list.append({"title": "장소", "description": params['location']})
            if params.get('number'):
                item_list.append({"title": "숫자", "description": params['number']})
        
        payload = {
            "version": "2.0",
            "template": {
                "outputs": [{
                    "itemCard": {
                        "title": f"{usage_desc}",
                        "description": "사용 내역이 맞는지 확인해 주세요!",
                        "profile": {"title": "뫄뫄AI", "imageUrl": "https://www.moamoa.kids/static/images/favicon.ico"},
                        "itemList": item_list,
                        "itemListSummary": {"title": "Total", "description": amount_match.group(1).strip().replace("<strong>","").replace("</strong>","")},
                        "buttons": [
                            {
                                "label": "맞아요 😊",
                                "action": "block",
                                "blockId": "696f71150c338f3b8e58fe2f",
                                "extra": {
                                    "cmd": "y",
                                    "user_id": user_id,
                                    "sync_id": (sync_id := str(uuid.uuid4())),
                                    "diary_data": {
                                        "diary_detail": usage_desc,
                                        "today": date_match.group(1).strip().replace("<strong>","").replace("</strong>","") if date_match else "",
                                        "category": cat_match.group(1).strip().replace("<strong>","").replace("</strong>","") if cat_match else "",
                                        "transaction_type": type_match.group(1).strip().replace("<strong>","").replace("</strong>","") if type_match else "",
                                        "amount": amount_match.group(1).strip().replace("<strong>","").replace("</strong>","").replace("원", "").replace(",", "") if amount_match else "0"
                                    }
                                }
                            },
                            {
                                "label": "아니요 😭",
                                "action": "block",
                                "blockId": "696f71150c338f3b8e58fe2f",
                                "extra": {
                                    "cmd": "n",
                                    "user_id": user_id,
                                    "sync_id": sync_id
                                }
                            }
                        ],
                        "buttonLayout": "horizontal"
                    }
                }]
            }
        }
    else:
        # 추출 실패 시 (Notice나 Limit 메시지 등) 기존대로 simpleText로 응답
        # <br> 태그와 <strong> 태그 제거하여 가독성 확보
        clean_text = response_text.replace("<br>", "\n").replace("<strong>", "").replace("</strong>", "")
        payload = {
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": clean_text}}]
            }
        }
            
    try:
        # 비동기 요청을 위해 httpx를 쓰는 게 좋지만 여기서는 requests 사용
        response = requests.post(callback_url, json=payload)
    except Exception as e:
        pass

router = APIRouter(tags=["kakao"])

@router.post("/msg")
async def kakao_message_log(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    카카오 메시지 그룹 방 로그 분석을 위한 엔드포인트
    수신된 JSON 값을 그대로 텍스트 파일에 저장합니다.
    """
    try:

        # 'bot' 헤더가 'moamoa'인 경우에만 로그 기록
        if request.headers.get("bot") != "moamoa":
            return {
                "version": "2.0",
                "template": {
                    "outputs": [{"simpleText": {"text": "기록되지 않은 봇의 메시지입니다."}}]
                }
            }
        
        # JSON 데이터 수신
        body = await request.json()
        
        # 특정 블록 ID 체크 및 채팅방 ID 저장
        user_request = body.get("userRequest", {})
        #블록 ID
        block = user_request.get("block", {})
        block_id = block.get("id")
        # 봇 ID
        bot_id = body.get("bot", {}).get("id")
        # 채팅방 ID
        chat = user_request.get("chat", {})
        chat_id = chat.get("id")
        # 사용자 ID
        user = user_request.get("user", {})
        user_id = user.get("id")
        # 콜백URL
        callback_url = user_request.get("callbackUrl")
        # 발화문 (사용자 입력 메시지)
        utterance = user_request.get("utterance")
        
        # Action 및 상세 파라미터 추출
        action = body.get("action", {})
        detail_params = action.get("detailParams", {})
        extracted_params = {
            "date": detail_params.get("sys_date", {}).get("origin"),
            "location": detail_params.get("sys_location", {}).get("origin"),
            "currency": detail_params.get("sys_unit_currency", {}).get("origin"),
            "number": detail_params.get("sys_number", {}).get("origin")
        }
        
        #블록 자녀 적용
        child_block_id = "69459714f37f4f7df3246a88"
        #블록 용돈기입장
        allowance_block_id = "6942260860f91e2c82b625ac"
        #블록 용돈기입장YN
        allowance_yn_block_id = "696f71150c338f3b8e58fe2f"
        #블록 월말결산 (ID 확인 필요 - 현재 YN블록과 동일하게 설정되어 있음)
        month_end_block_id = "69722914b3799b0f2936ac84"

        # 발화문 모니터링을 위한 DB 저장 ("용돈기입장" 포함된 경우만)
        if utterance and "용돈기입장" in utterance:
            try:
                new_utterance = KakaoUtterance(
                    user_key=user_id,
                    chat_id=chat_id,
                    utterance=utterance,
                    block_id=block_id,
                    params=json.dumps(extracted_params, ensure_ascii=False)
                )
                db.add(new_utterance)
                db.commit()
            except Exception as utt_e:
                db.rollback()

        # Kakao API를 통한 채팅방 멤버 정보 조회
        if bot_id and chat_id:
            try:
                url = f"https://bot-api.kakao.com/v2/bots/{bot_id}/group-chat-rooms/{chat_id}/members"
                headers = { "Authorization": f"KakaoAK {settings.REST_API_KEY}", "Content-Type": "application/json; charset=utf-8" }

                api_response = requests.get(url, headers=headers)

                if api_response.status_code == 200:
                    # 채팅방 정보 저장 및 ID 가져오기
                    chat_record = db.query(KakaoChat).filter(KakaoChat.chat_id == chat_id).first()
                    if not chat_record:
                        chat_record = KakaoChat(chat_id=chat_id)
                        db.add(chat_record)
                        db.commit()
                        db.refresh(chat_record)

                    # 멤버 리스트 저장 (중복 없이 등록)
                    members_data = api_response.json()
                    member_keys = members_data.get("users", [])
                    
                    for m_key in member_keys:
                        existing_member = db.query(KakaoChatMember).filter(
                            KakaoChatMember.chat_id == chat_record.id,
                            KakaoChatMember.user_key == m_key
                        ).first()
                        
                        if not existing_member:
                            db.add(KakaoChatMember(
                                chat_id=chat_record.id, 
                                user_key=m_key, 
                                user_type=0  # 기본값 등록
                            ))
                    db.commit()
            except Exception as api_e:
                pass
        
        #블록 자녀 선택
        if block_id == child_block_id:
            chat_record = db.query(KakaoChat).filter(KakaoChat.chat_id == chat_id).first()
            
            if chat_record:
                # 사용자가 자녀(1)인 경우 권한 방지
                current_user = db.query(KakaoChatMember).filter(
                    KakaoChatMember.chat_id == chat_record.id,
                    KakaoChatMember.user_key == user_id
                ).first()
                
                if current_user and current_user.user_type == 1:
                    return {
                        "version": "2.0",
                        "template": {
                            "outputs": [{"simpleText": {"text": "사용할 수 없는 메뉴입니다."}}]
                        }
                    }

            if not chat_record:
                # 채팅방 정보가 없는 경우 (이론상 발생하기 어렵지만 안전장치)
                chat_record = KakaoChat(chat_id=chat_id)
                db.add(chat_record)
                db.commit()
                db.refresh(chat_record)

            # 선택된 자녀 정보 미리 추출 및 유효성 검사 (자기 자신 제외)
            action_params = body.get("action", {}).get("params", {})
            child_keys_to_check = ["sys_user_mention", "sys_user_mention1", "sys_user_mention2", "sys_user_mention3", "sys_user_mention4"]
            new_child_keys = []
            self_selection_detected = False

            # 선택된 자녀 검증
            for ck in child_keys_to_check:
                child_param = action_params.get(ck)
                if child_param:
                    try:
                        child_data = json.loads(child_param)
                        ck_key = child_data.get("botUserKey")
                        if ck_key:
                            if ck_key == user_id:
                                self_selection_detected = True
                                continue
                            new_child_keys.append(ck_key)
                    except: pass
            
            new_child_keys = list(set(new_child_keys)) # 중복 제거
            

            # 자기 자신만 선택했거나 자녀가 한 명도 선택되지 않았을 경우 안내 메시지 반환
            if not new_child_keys:
                msg = "@뫄뫄AI 자녀선택 @자녀 \n @뫄뫄AI 자녀선택 @자녀 @자녀1 \n /자녀선택 @자녀 \n /자녀선택 @자녀 @자녀1 \n 아이들은 5명까지 선택이 가능합니다."
                if self_selection_detected:
                    msg = "본인은 자녀로 설정할 수 없습니다. 다시 선택해주세요."
                
                return {
                    "version": "2.0",
                    "template": {
                        "outputs": [{"simpleText": {"text": msg}}]
                    }
                }

            # 현재 DB의 자녀 목록과 비교 (중복 적용 방지)
            current_children = db.query(KakaoChatMember).filter(
                KakaoChatMember.chat_id == chat_record.id,
                KakaoChatMember.user_type == 1
            ).all()
            current_keys = [c.user_key for c in current_children]

            if set(current_keys) == set(new_child_keys):
                return {
                    "version": "2.0",
                    "template": {
                        "outputs": [{"simpleText": {"text": "이미 동일한 자녀들이 선택되어 있습니다."}}]
                    }
                }

            # 변경 사항이 있는 경우에만 업데이트 수행
            db.query(KakaoChatMember).filter(KakaoChatMember.chat_id == chat_record.id).update({"user_type": 0})
            
            for k in new_child_keys:
                db.query(KakaoChatMember).filter(
                    KakaoChatMember.chat_id == chat_record.id,
                    KakaoChatMember.user_key == k
                ).update({"user_type": 1})
            
            db.commit()

            # 멘션 정보 구성하여 결과 반환
            mentions_dict = {}
            mention_lines = []
            for i, k in enumerate(new_child_keys):
                mention_id = f"user{i+1}"
                mentions_dict[mention_id] = {"type": "botUserKey", "id": k}
                mention_lines.append(f" * {{{{#mentions.{mention_id}}}}}")
            
            success_msg = "자녀 선택이 완료되었습니다.\n" + "\n".join(mention_lines)
            if self_selection_detected:
                success_msg += "\n\n 본인은 자녀에서 제외되었습니다."

            return {
                "version": "2.0",
                "template": {
                    "outputs": [{"simpleText": {"text": success_msg}}]
                },
                "extra": {
                    "mentions": mentions_dict
                }
            }

        #블록 용돈기입장
        elif block_id == allowance_block_id:

            chat_record = db.query(KakaoChat).filter(KakaoChat.chat_id == chat_id).first()

            if chat_record:
                # 채팅방에 설정된 자녀가 있는지 확인
                has_child = db.query(KakaoChatMember).filter(
                    KakaoChatMember.chat_id == chat_record.id,
                    KakaoChatMember.user_type == 1
                ).first()
                
                if not has_child:
                    return {
                        "version": "2.0",
                        "template": {
                            "outputs": [{"simpleText": {"text": "설정된 자녀가 없습니다. 먼저 자녀를 선택해 주세요.\n\n(예: @뫄뫄AI 자녀선택 @자녀)"}}]
                        }
                    }

                # 사용자가 자녀(1)인 경우 권한 방지
                current_user = db.query(KakaoChatMember).filter(
                    KakaoChatMember.chat_id == chat_record.id,
                    KakaoChatMember.user_key == user_id
                ).first()
                
                # 부모(0)인 경우 사용 방지
                if not current_user or current_user.user_type == 0:
                    return {
                        "version": "2.0",
                        "template": {
                            "outputs": [{"simpleText": {"text": "자녀만 사용할 수 있는 메뉴입니다."}}]
                        }
                    }
            
            if callback_url:
                # 백그라운드 작업 추가
                utterance = utterance.replace("용돈기입장", "").strip()
                
                # user_id 는 kakao_chat_members 테이블에 id 값으로 적용
                # chat_id 와 user_key 매칭이 kakao_chat_members 테이블 id 값으로 user_id 반영
                member_id = current_user.id if (current_user and hasattr(current_user, 'id')) else user_id

                background_tasks.add_task(process_callback, callback_url, utterance, member_id, extracted_params)
            
                return {
                    "version": "2.0",
                    "useCallback" : True,
                    "data": { "loadingText" : utterance + "\n\n분석하고 있습니다. 잠시만 기다려 주세요!"}
                }

        #블록 용돈기입장YN
        elif block_id == allowance_yn_block_id:
            client_extra = action.get("clientExtra", {})
            cmd = client_extra.get("cmd")
            member_id = client_extra.get("user_id")
            sync_id = client_extra.get("sync_id")

            # 동기화 상태 확인
            sync_record = db.query(KakaoSync).filter(KakaoSync.sync_id == sync_id).first() if sync_id else None

            if cmd == "y":
                # 이미 처리된 건인지 확인
                if sync_record:
                    if sync_record.status == "SAVED":
                        return {
                            "version": "2.0",
                            "template": {
                                "outputs": [{"simpleText": {"text": "이미 기록된 내역입니다."}}]
                            }
                        }
                    elif sync_record.status == "CANCELLED":
                        return {
                            "version": "2.0",
                            "template": {
                                "outputs": [{"simpleText": {"text": "이미 취소된 내역입니다. 다시 입력해 주세요."}}]
                            }
                        }

                # 데이터베이스 저장 로직
                diary_data = client_extra.get("diary_data")
                if diary_data:
                    # 자녀/부모 매칭을 위한 KakaoChatMember 조회
                    chat_member = db.query(KakaoChatMember).filter(KakaoChatMember.id == member_id).first()
                    
                    if not chat_member:
                        chat_member = db.query(KakaoChatMember).filter(KakaoChatMember.user_key == member_id).first()

                    if chat_member:
                        child_user = db.query(User).filter(User.username == chat_member.user_key).first()
                        if not child_user:
                            child_user = User(
                                username=chat_member.user_key,
                                password=hash_password_django("kakao_default_pwd"),
                                first_name=f"카카오자녀_{chat_member.id}",
                                is_active=True,
                                date_joined=datetime.utcnow().isoformat()
                            )
                            db.add(child_user)
                            db.commit()
                            db.refresh(child_user)

                        parent_member = db.query(KakaoChatMember).filter(
                            KakaoChatMember.chat_id == chat_member.chat_id,
                            KakaoChatMember.user_type == 0
                        ).first()

                        if parent_member:
                            parent_user = db.query(User).filter(User.username == parent_member.user_key).first()
                            if not parent_user:
                                parent_user = User(
                                    username=parent_member.user_key,
                                    password=hash_password_django("kakao_default_pwd"),
                                    first_name=f"카카오부모_{parent_member.id}",
                                    is_active=True,
                                    date_joined=datetime.utcnow().isoformat()
                                )
                                db.add(parent_user)
                                db.commit()
                                db.refresh(parent_user)
                            
                            if child_user.parents_id != parent_user.id:
                                child_user.parents_id = parent_user.id
                                db.commit()
                        else:
                            parent_user = child_user

                        try:
                            amt_str = str(diary_data.get("amount", "0")).replace(",", "").replace("원", "").strip()
                            amount_val = Decimal(amt_str)
                        except:
                            amount_val = Decimal("0")
                        
                        today_str = diary_data.get("today")
                        try:
                            clean_date_str = re.sub(r'[^0-9-]', '', today_str)
                            today_date = datetime.strptime(clean_date_str, "%Y-%m-%d").date()
                        except:
                            today_date = datetime.now().date()

                        new_entry = FinanceDiary(
                            child_id=child_user.id,
                            parent_id=parent_user.id,
                            diary_detail=diary_data.get("diary_detail", ""),
                            category=diary_data.get("category", "기타/지출"),
                            transaction_type=diary_data.get("transaction_type", "지출"),
                            amount=amount_val,
                            remaining=child_user.total,
                            today=today_date,
                            kakao_sync_id=sync_id
                        )
                        db.add(new_entry)
                        
                        # 동기화 정보 저장
                        if sync_id:
                            new_sync = KakaoSync(sync_id=sync_id, status="SAVED")
                            db.add(new_sync)
                            
                        db.commit()
                        update_remaining_balance(db, child_user)

                        magic_token = create_magic_token(child_user.id)

                        return {
                            "version": "2.0",
                            "template": {
                                "outputs": [
                                    {
                                        "textCard": {
                                            "title": "기록 완료!",
                                            "description": "성공적으로 기록되었습니다.",
                                            "buttons": [
                                                {
                                                    "action": "webLink",
                                                    "label": "용돈기입장 보러가기",
                                                    "webLinkUrl": f"https://moamoa.kids/verify-token/?token={magic_token}"
                                                }
                                            ]
                                        }
                                    }
                                ]
                            }
                        }

                return {
                    "version": "2.0",
                    "template": {
                        "outputs": [{"simpleText": {"text": "데이터 오류가 발생했습니다. 다시 시도해 주세요."}}]
                    }
                }

            if cmd == "n":
                # 이미 기록된 건인지 확인하여 있으면 삭제 (취소 로직)
                if sync_id:
                    # 기존 기록 삭제
                    entry = db.query(FinanceDiary).filter(FinanceDiary.kakao_sync_id == sync_id).first()
                    if entry:
                        child_user = db.query(User).filter(User.username == entry.child.username).first()
                        db.delete(entry)
                        pass
                        
                        # 상태 업데이트
                        if sync_record:
                            sync_record.status = "CANCELLED"
                        else:
                            db.add(KakaoSync(sync_id=sync_id, status="CANCELLED"))
                        
                        db.commit()
                        
                        # 잔액 재계산
                        if child_user:
                            update_remaining_balance(db, child_user)
                            
                        return {
                            "version": "2.0",
                            "template": {
                                "outputs": [{"simpleText": {"text": "기록이 취소되었습니다."}}]
                            }
                        }
                    else:
                        # 아직 등록 전이라면 "취소됨" 상태만 저장 (추후 "맞아요" 눌러도 무시됨)
                        if not sync_record:
                            db.add(KakaoSync(sync_id=sync_id, status="CANCELLED"))
                            db.commit()
                        
                        return {
                            "version": "2.0",
                            "template": {
                                "outputs": [{"simpleText": {"text": "기록이 취소되었습니다. 다시 입력해 주세요."}}]
                            }
                        }

                return {
                    "version": "2.0",
                    "template": {
                        "outputs": [{"simpleText": {"text": "기록이 취소되었습니다."}}]
                    }
                }

        #블록 월말결산
        elif block_id == month_end_block_id:
            # 부모만 월말결산 볼수 있음
            chat_record = db.query(KakaoChat).filter(KakaoChat.chat_id == chat_id).first()
            if chat_record:
                current_member = db.query(KakaoChatMember).filter(
                    KakaoChatMember.chat_id == chat_record.id,
                    KakaoChatMember.user_key == user_id
                ).first()

                # 자녀인 경우 접근 제한
                if current_member and current_member.user_type == 1:
                    return {
                        "version": "2.0",
                        "template": {
                            "outputs": [{"simpleText": {"text": "부모님만 확인할 수 있는 메뉴입니다. 😊"}}]
                        }
                    }

                # 멘션된 자녀 추출 (있는 경우 해당 자녀만 표시)
                action_params = action.get("params", {})
                mentioned_keys = []
                for k in ["sys_user_mention", "sys_user_mention1", "sys_user_mention2", "sys_user_mention3", "sys_user_mention4"]:
                    m_val = action_params.get(k)
                    if m_val:
                        try:
                            m_data = json.loads(m_val)
                            kb_key = m_data.get("botUserKey")
                            if kb_key: mentioned_keys.append(kb_key)
                        except: pass
                
                mentioned_keys = list(set(mentioned_keys))

                # 채팅방에 등록된 자녀 목록 조회
                query = db.query(KakaoChatMember).filter(
                    KakaoChatMember.chat_id == chat_record.id,
                    KakaoChatMember.user_type == 1
                )
                
                # 멘션이 있으면 멘션된 자녀들만 필터링
                if mentioned_keys:
                    query = query.filter(KakaoChatMember.user_key.in_(mentioned_keys))
                
                children_members = query.all()

                if not children_members:
                    return {
                        "version": "2.0",
                        "template": {
                            "outputs": [{"simpleText": {"text": "등록된 자녀가 없습니다. 먼저 자녀를 선택해 주세요.\n\n(예: @뫄뫄AI 자녀선택 @자녀)"}}]
                        }
                    }

                # 부모 User 객체 가져오기 (매직 토큰 생성용)
                parent_user = db.query(User).filter(User.username == user_id).first()
                if not parent_user:
                    # 유저가 없으면 임시 생성 (추후 정보 업데이트 가능)
                    parent_user = User(
                        username=user_id,
                        password=hash_password_django("kakao_default_pwd"),
                        first_name=f"카카오부모_{current_member.id if current_member else int(time.time())}",
                        is_active=True,
                        date_joined=datetime.utcnow().isoformat()
                    )
                    db.add(parent_user)
                    db.commit()
                    db.refresh(parent_user)

                now = datetime.now()
                year_month_str = now.strftime("%Y년 %m월")
                magic_token = create_magic_token(parent_user.id)
                output_cards = []
                mentions_dict = {}
                
                # 유효한(기록이 있는) 자녀 데이터 필터링
                valid_children_data = []
                for cm in children_members:
                    c_user = db.query(User).filter(User.username == cm.user_key).first()
                    if c_user:
                        # 한 건이라도 있는지 확인
                        if db.query(FinanceDiary).filter(FinanceDiary.child_id == c_user.id).first():
                            valid_children_data.append((cm, c_user))
                
                if not valid_children_data:
                    return {
                        "version": "2.0",
                        "template": {
                            "outputs": [{"simpleText": {"text": "/용돈기입장 자산내용 입력해주세요"}}]
                        }
                    }
                
                for i, (cm, child_user) in enumerate(valid_children_data[:3]):
                    mention_id = f"child_{i+1}"
                    mentions_dict[mention_id] = {"type": "botUserKey", "id": cm.user_key}
                    
                    # 부모-자녀 관계 연결 (누락 방지)
                    if child_user.parents_id != parent_user.id:
                        child_user.parents_id = parent_user.id
                        db.commit()

                    child_id = child_user.id

                    # 안내 메시지 (자녀가 1명일 때만 혹은 카드 제한에 맞춰 노출)
                    if len(valid_children_data) == 1:
                        output_cards.append({
                            "simpleText": {
                                "text": f"{{{{#mentions.{mention_id}}}}} 자녀의 {year_month_str} 용돈 관리 리포트가 준비되었습니다! 💌"
                            }
                        })
                    
                    # 메인 리포트 카드
                    output_cards.append({
                        "textCard": {
                            "title": f"{year_month_str} 월말결산 리포트",
                            "description": "자녀의 이번 달 소비 패턴과 AI 분석 결과를 리포트로 확인해 보세요! ",
                            "buttons": [
                                {
                                    "action": "webLink",
                                    "label": "결산 리포트 보기",
                                    "webLinkUrl": f"https://moamoa.kids/verify-token/?token={magic_token}&next=/profile/?child_id={child_id}"
                                }
                            ]
                        }
                    })
                    
                    # 카카오 3개 제한 방어
                    if len(output_cards) >= 3:
                        break

                return {
                    "version": "2.0",
                    "template": {
                        "outputs": output_cards
                    },
                    "extra": {
                        "mentions": mentions_dict
                    }
                }
            
        # 기본 응답 및 발화문 모니터링 위한 등록
        return {
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {"text": "[부모] 자녀들을 선택 할때?\n/자녀선택 @홍길동\n/자녀선택 @홍길동 @홍길동\n자녀는 5명까지 선택이 가능합니다.\n\n[부모] 월말 결산 및 리포트를 보고 싶다면?\n/월말결산 @홍길동\n\n[자녀] 용돈 기입장을 작성 하는 방법?\n(날짜, 내용, 금액이 포함되게 작성해주세요)\n/용돈기입장 오늘 엄마가 용돈을 만원 줬어\n/용돈기입장 오늘 형광펜 사느라 1000원 씀\n\n"}
                    }]
            }
        }

    except Exception as e:
        # 에러 발생 시 로그 (필요시 파일에 에러도 기록 가능)
        # 에러 발생 시 로그 (필요시 파일에 에러도 기록 가능)
        return {"status": "error", "message": str(e)}
