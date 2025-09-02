"""
개인 쪽지 및 사용자 메모 관리 모듈

이 모듈은 웹사이트 리뷰 플랫폼의 사용자 간 소통 기능을 담당합니다:
- 개인 쪽지 송수신 (사용자명 기반)
- 사용자별 메모 저장 및 관리
- 쪽지 읽음 처리 및 삭제 관리
"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, validator
from .db import supabase
from .auth import get_current_user

# 로깅 설정
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# FastAPI 라우터
router = APIRouter()

# Pydantic 모델 정의

class MessageSend(BaseModel):
    """쪽지 발송 요청 모델"""
    receiver_username: str
    subject: str
    content: str
    
    @validator('receiver_username')
    def validate_receiver_username(cls, v):
        if len(v) < 3 or len(v) > 20:
            raise ValueError('수신자 사용자명은 3-20자 사이여야 합니다')
        if not v.isalnum():
            raise ValueError('수신자 사용자명은 영문자와 숫자만 허용됩니다')
        return v
    
    @validator('subject')
    def validate_subject(cls, v):
        if len(v.strip()) == 0:
            raise ValueError('제목을 입력해주세요')
        if len(v) > 100:
            raise ValueError('제목은 100자 이내로 입력해주세요')
        return v.strip()
    
    @validator('content')
    def validate_content(cls, v):
        if len(v.strip()) == 0:
            raise ValueError('내용을 입력해주세요')
        if len(v) > 1000:
            raise ValueError('내용은 1000자 이내로 입력해주세요')
        return v.strip()

class MessageResponse(BaseModel):
    """쪽지 응답 모델"""
    id: int
    sender_username: Optional[str] = None
    receiver_username: Optional[str] = None
    subject: str
    content: str
    created_at: str
    read_at: Optional[str] = None
    is_read: bool = False

class UserMemo(BaseModel):
    """사용자 메모 요청 모델"""
    target_username: str
    memo: str
    
    @validator('target_username')
    def validate_target_username(cls, v):
        if len(v) < 3 or len(v) > 20:
            raise ValueError('대상 사용자명은 3-20자 사이여야 합니다')
        if not v.isalnum():
            raise ValueError('대상 사용자명은 영문자와 숫자만 허용됩니다')
        return v
    
    @validator('memo')
    def validate_memo(cls, v):
        if len(v.strip()) == 0:
            raise ValueError('메모 내용을 입력해주세요')
        if len(v) > 500:
            raise ValueError('메모는 500자 이내로 입력해주세요')
        return v.strip()

class UserMemoResponse(BaseModel):
    """사용자 메모 응답 모델"""
    id: int
    target_username: str
    memo: str
    created_at: str
    updated_at: str

class InboxResponse(BaseModel):
    """수신 쪽지함 응답 모델"""
    messages: List[MessageResponse]
    page: int
    limit: int
    total: int

class SentMessagesResponse(BaseModel):
    """발신 쪽지함 응답 모델"""
    messages: List[MessageResponse]
    page: int
    limit: int
    total: int

class MemosResponse(BaseModel):
    """전체 메모 목록 응답 모델"""
    memos: List[UserMemoResponse]
    total: int

class MessageSendResponse(BaseModel):
    """쪽지 발송 응답 모델"""
    message: str
    message_id: int
    receiver: str

class MessageReadResponse(BaseModel):
    """쪽지 읽음 처리 응답 모델"""
    message: str
    read_at: str

class MessageDeleteResponse(BaseModel):
    """쪽지 삭제 응답 모델"""
    message: str

class MemoSaveResponse(BaseModel):
    """메모 저장 응답 모델"""
    message: str
    target_username: str
    memo: str

class MemoGetResponse(BaseModel):
    """메모 조회 응답 모델"""
    id: Optional[int] = None
    target_username: str
    memo: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class MemoDeleteResponse(BaseModel):
    """메모 삭제 응답 모델"""
    message: str

# 유틸리티 함수

def get_user_by_username(username: str):
    """사용자명으로 사용자 정보 조회"""
    try:
        user_result = supabase.table("user").select("id", "username", "email_verified").eq("username", username).execute()
        if not user_result.data:
            return None
        user_data = user_result.data[0]
        
        # 이메일 인증 여부 확인
        if not user_data.get("email_verified"):
            return None
            
        return user_data
    except Exception as e:
        logger.error(f"Error getting user by username: {str(e)}")
        return None

# 개인 쪽지 API 엔드포인트

@router.post("/send", response_model=MessageSendResponse)
def send_message(message: MessageSend, current_user=Depends(get_current_user)) -> MessageSendResponse:
    """
    개인 쪽지 발송
    - 수신자 사용자명으로 쪽지 발송
    - 자기 자신에게는 쪽지 발송 불가
    - 인증된 사용자만 쪽지 수신 가능
    """
    try:
        # 자기 자신에게 쪽지 발송 방지
        if message.receiver_username == current_user["username"]:
            raise HTTPException(status_code=400, detail="Cannot send message to yourself")
        
        # 수신자 존재 및 인증 여부 확인
        receiver = get_user_by_username(message.receiver_username)
        if not receiver:
            raise HTTPException(status_code=404, detail="Receiver not found or not verified")
        
        # 쪽지 저장
        message_data = {
            "sender_id": current_user["id"],
            "receiver_id": receiver["id"],
            "subject": message.subject,
            "content": message.content,
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("private_message").insert(message_data).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to send message")
        
        return MessageSendResponse(
            message="Message sent successfully",
            message_id=result.data[0]["id"],
            receiver=message.receiver_username
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")

@router.get("/inbox", response_model=InboxResponse)
def get_inbox(current_user=Depends(get_current_user), page: int = 1, limit: int = 20) -> InboxResponse:
    """
    수신 쪽지함 조회
    - 페이지네이션 지원
    - 본인이 받은 쪽지만 조회
    - 삭제하지 않은 쪽지만 조회
    """
    try:
        offset = (page - 1) * limit
        
        # 수신 쪽지 조회 (발신자 정보 포함)
        result = supabase.table("private_message").select(
            """
            id,
            subject,
            content,
            created_at,
            read_at,
            sender_id,
            sender:sender_id(username)
            """
        ).eq("receiver_id", current_user["id"]).eq("is_deleted_by_receiver", False).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
        messages = []
        for msg in result.data:
            messages.append(MessageResponse(
                id=msg["id"],
                sender_username=msg["sender"]["username"],
                subject=msg["subject"],
                content=msg["content"],
                created_at=msg["created_at"],
                read_at=msg["read_at"],
                is_read=msg["read_at"] is not None
            ))
        
        return InboxResponse(
            messages=messages,
            page=page,
            limit=limit,
            total=len(messages)
        )
        
    except Exception as e:
        logger.error(f"Error getting inbox: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get inbox: {str(e)}")

@router.get("/sent", response_model=SentMessagesResponse)
def get_sent_messages(current_user=Depends(get_current_user), page: int = 1, limit: int = 20) -> SentMessagesResponse:
    """
    발신 쪽지함 조회
    - 페이지네이션 지원
    - 본인이 보낸 쪽지만 조회
    - 삭제하지 않은 쪽지만 조회
    """
    try:
        offset = (page - 1) * limit
        
        # 발신 쪽지 조회 (수신자 정보 포함)
        result = supabase.table("private_message").select(
            """
            id,
            subject,
            content,
            created_at,
            read_at,
            receiver_id,
            receiver:receiver_id(username)
            """
        ).eq("sender_id", current_user["id"]).eq("is_deleted_by_sender", False).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
        messages = []
        for msg in result.data:
            messages.append(MessageResponse(
                id=msg["id"],
                receiver_username=msg["receiver"]["username"],
                subject=msg["subject"],
                content=msg["content"],
                created_at=msg["created_at"],
                read_at=msg["read_at"],
                is_read=msg["read_at"] is not None
            ))
        
        return SentMessagesResponse(
            messages=messages,
            page=page,
            limit=limit,
            total=len(messages)
        )
        
    except Exception as e:
        logger.error(f"Error getting sent messages: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get sent messages: {str(e)}")

@router.put("/{message_id}/read", response_model=MessageReadResponse)
def mark_message_as_read(message_id: int, current_user=Depends(get_current_user)) -> MessageReadResponse:
    """
    쪽지 읽음 처리
    - 수신자만 읽음 처리 가능
    - 이미 읽은 쪽지는 읽음 시간 변경 안함
    """
    try:
        # 쪽지 존재 및 권한 확인
        message_result = supabase.table("private_message").select("*").eq("id", message_id).eq("receiver_id", current_user["id"]).execute()
        
        if not message_result.data:
            raise HTTPException(status_code=404, detail="Message not found")
        
        message_data = message_result.data[0]
        
        # 이미 읽은 쪽지인 경우
        if message_data["read_at"]:
            return MessageReadResponse(message="Message already read", read_at=message_data["read_at"])
        
        # 읽음 처리
        read_at = datetime.utcnow().isoformat()
        update_result = supabase.table("private_message").update({"read_at": read_at}).eq("id", message_id).execute()
        
        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to mark message as read")
        
        return MessageReadResponse(message="Message marked as read", read_at=read_at)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking message as read: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to mark message as read: {str(e)}")

@router.delete("/{message_id}", response_model=MessageDeleteResponse)
def delete_message(message_id: int, current_user=Depends(get_current_user)) -> MessageDeleteResponse:
    """
    쪽지 삭제 (소프트 삭제)
    - 발신자는 is_deleted_by_sender = true
    - 수신자는 is_deleted_by_receiver = true
    - 양쪽 모두 삭제하면 실제 삭제
    """
    try:
        # 쪽지 존재 확인
        message_result = supabase.table("private_message").select("*").eq("id", message_id).execute()
        
        if not message_result.data:
            raise HTTPException(status_code=404, detail="Message not found")
        
        message_data = message_result.data[0]
        
        # 권한 확인 (발신자 또는 수신자)
        if message_data["sender_id"] != current_user["id"] and message_data["receiver_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Permission denied")
        
        update_data = {}
        
        if message_data["sender_id"] == current_user["id"]:
            update_data["is_deleted_by_sender"] = True
        elif message_data["receiver_id"] == current_user["id"]:
            update_data["is_deleted_by_receiver"] = True
        
        # 소프트 삭제
        supabase.table("private_message").update(update_data).eq("id", message_id).execute()
        
        # 양쪽 모두 삭제한 경우 실제 삭제
        if (update_data.get("is_deleted_by_sender") and message_data.get("is_deleted_by_receiver")) or \
           (update_data.get("is_deleted_by_receiver") and message_data.get("is_deleted_by_sender")):
            supabase.table("private_message").delete().eq("id", message_id).execute()
            return MessageDeleteResponse(message="Message permanently deleted")
        
        return MessageDeleteResponse(message="Message deleted successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete message: {str(e)}")

# 사용자 메모 API 엔드포인트

@router.post("/memo", response_model=MemoSaveResponse)
def save_user_memo(memo: UserMemo, current_user=Depends(get_current_user)) -> MemoSaveResponse:
    """
    사용자 메모 저장
    - 대상 사용자에 대한 개인 메모 저장
    - 기존 메모가 있으면 업데이트
    """
    try:
        # 대상 사용자 존재 확인
        target_user = get_user_by_username(memo.target_username)
        if not target_user:
            raise HTTPException(status_code=404, detail="Target user not found")
        
        # 자기 자신에 대한 메모 방지
        if target_user["id"] == current_user["id"]:
            raise HTTPException(status_code=400, detail="Cannot create memo for yourself")
        
        # 기존 메모 확인
        existing_memo = supabase.table("user_memo").select("*").eq("user_id", current_user["id"]).eq("target_user_id", target_user["id"]).execute()
        
        current_time = datetime.utcnow().isoformat()
        
        if existing_memo.data:
            # 기존 메모 업데이트
            update_result = supabase.table("user_memo").update({
                "memo": memo.memo,
                "updated_at": current_time
            }).eq("user_id", current_user["id"]).eq("target_user_id", target_user["id"]).execute()
            
            if not update_result.data:
                raise HTTPException(status_code=500, detail="Failed to update memo")
            
            return MemoSaveResponse(
                message="Memo updated successfully",
                target_username=memo.target_username,
                memo=memo.memo
            )
        else:
            # 새 메모 생성
            memo_data = {
                "user_id": current_user["id"],
                "target_user_id": target_user["id"],
                "memo": memo.memo,
                "created_at": current_time,
                "updated_at": current_time
            }
            
            insert_result = supabase.table("user_memo").insert(memo_data).execute()
            
            if not insert_result.data:
                raise HTTPException(status_code=500, detail="Failed to save memo")
            
            return MemoSaveResponse(
                message="Memo saved successfully",
                target_username=memo.target_username,
                memo=memo.memo
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving user memo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save memo: {str(e)}")

@router.get("/memo/{target_username}", response_model=MemoGetResponse)
def get_user_memo(target_username: str, current_user=Depends(get_current_user)) -> MemoGetResponse:
    """
    특정 사용자에 대한 메모 조회
    """
    try:
        # 대상 사용자 존재 확인
        target_user = get_user_by_username(target_username)
        if not target_user:
            raise HTTPException(status_code=404, detail="Target user not found")
        
        # 메모 조회
        memo_result = supabase.table("user_memo").select("*").eq("user_id", current_user["id"]).eq("target_user_id", target_user["id"]).execute()
        
        if not memo_result.data:
            return MemoGetResponse(target_username=target_username)
        
        memo_data = memo_result.data[0]
        
        return MemoGetResponse(
            id=memo_data["id"],
            target_username=target_username,
            memo=memo_data["memo"],
            created_at=memo_data["created_at"],
            updated_at=memo_data["updated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user memo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get memo: {str(e)}")

@router.get("/memos", response_model=MemosResponse)
def get_all_memos(current_user=Depends(get_current_user)) -> MemosResponse:
    """
    내가 작성한 모든 메모 조회
    """
    try:
        # 모든 메모 조회 (대상 사용자 정보 포함)
        memos_result = supabase.table("user_memo").select(
            """
            id,
            memo,
            created_at,
            updated_at,
            target_user_id,
            target_user:target_user_id(username)
            """
        ).eq("user_id", current_user["id"]).order("updated_at", desc=True).execute()
        
        memos = []
        for memo in memos_result.data:
            memos.append(UserMemoResponse(
                id=memo["id"],
                target_username=memo["target_user"]["username"],
                memo=memo["memo"],
                created_at=memo["created_at"],
                updated_at=memo["updated_at"]
            ))
        
        return MemosResponse(memos=memos, total=len(memos))
        
    except Exception as e:
        logger.error(f"Error getting all memos: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get memos: {str(e)}")

@router.delete("/memo/{target_username}", response_model=MemoDeleteResponse)
def delete_user_memo(target_username: str, current_user=Depends(get_current_user)) -> MemoDeleteResponse:
    """
    특정 사용자에 대한 메모 삭제
    """
    try:
        # 대상 사용자 존재 확인
        target_user = get_user_by_username(target_username)
        if not target_user:
            raise HTTPException(status_code=404, detail="Target user not found")
        
        # 메모 삭제
        delete_result = supabase.table("user_memo").delete().eq("user_id", current_user["id"]).eq("target_user_id", target_user["id"]).execute()
        
        if not delete_result.data:
            raise HTTPException(status_code=404, detail="Memo not found")
        
        return MemoDeleteResponse(message=f"Memo for {target_username} deleted successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user memo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete memo: {str(e)}")