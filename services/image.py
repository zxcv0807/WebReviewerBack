from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse
from datetime import datetime
import os
import uuid
import logging
from pathlib import Path
from PIL import Image
import io
from .db import supabase

# 로깅 설정
logger = logging.getLogger(__name__)

# Supabase Storage 설정
STORAGE_BUCKET = "images"
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB 제한
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

# 이미지 최적화 설정
MAX_IMAGE_WIDTH = 1920
MAX_IMAGE_HEIGHT = 1080
JPEG_QUALITY = 85

router = APIRouter()

def validate_and_optimize_image(file_content: bytes) -> tuple[bytes, str]:
    """
    이미지 검증 및 최적화
    Returns: (optimized_content, format)
    """
    try:
        # PIL로 이미지 열기 및 검증
        image = Image.open(io.BytesIO(file_content))
        image.verify()  # 이미지 무결성 검증
        
        # 이미지 다시 열기 (verify 후에는 객체가 손상됨)
        image = Image.open(io.BytesIO(file_content))
        
        # RGBA -> RGB 변환 (JPEG 호환성)
        if image.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
            image = background
        
        # 크기 조정 (필요시)
        if image.width > MAX_IMAGE_WIDTH or image.height > MAX_IMAGE_HEIGHT:
            image.thumbnail((MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT), Image.Resampling.LANCZOS)
        
        # 최적화된 이미지를 바이트로 변환
        output = io.BytesIO()
        format_name = "JPEG"  # 기본적으로 JPEG로 변환
        image.save(output, format=format_name, quality=JPEG_QUALITY, optimize=True)
        
        return output.getvalue(), format_name.lower()
        
    except Exception as e:
        logger.error(f"이미지 검증/최적화 실패: {str(e)}")
        raise ValueError("유효하지 않은 이미지 파일입니다")

def sanitize_filename(filename: str) -> str:
    """파일명 보안 처리"""
    # 경로 조작 방지
    filename = os.path.basename(filename)
    # 특수문자 제거
    safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"
    filename = "".join(c for c in filename if c in safe_chars)
    return filename[:100]  # 길이 제한

@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    """
    이미지 파일 업로드 API (Supabase Storage 사용)
    
    보안 검증:
    - 파일 크기 제한 (5MB)
    - 파일 타입 검증 (확장자 + MIME + 내용)
    - 파일명 보안 처리
    - 이미지 최적화 및 크기 조정
    """
    try:
        # 1. 기본 검증
        if not file.filename:
            raise HTTPException(status_code=400, detail="파일명이 제공되지 않았습니다")
        
        # 2. 파일 크기 검증
        file_content = await file.read()
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"파일 크기가 너무 큽니다. 최대 {MAX_FILE_SIZE//1024//1024}MB까지 허용됩니다")
        
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="빈 파일입니다")
        
        # 3. 파일 확장자 검증
        original_filename = sanitize_filename(file.filename)
        file_ext = Path(original_filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"허용되지 않는 파일 형식입니다. 허용 형식: {', '.join(ALLOWED_EXTENSIONS)}")
        
        # 4. MIME 타입 검증
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=400, detail="허용되지 않는 MIME 타입입니다")
        
        # 5. 이미지 검증 및 최적화
        try:
            optimized_content, image_format = validate_and_optimize_image(file_content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # 6. 고유 파일명 생성 (UUID + 타임스탬프)
        unique_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        save_name = f"{timestamp}_{unique_id}.{image_format}"
        
        # 7. Supabase Storage에 업로드
        try:
            storage_response = supabase.storage.from_(STORAGE_BUCKET).upload(
                path=save_name,
                file=optimized_content,
                file_options={
                    "content-type": f"image/{image_format}",
                    "cache-control": "3600"
                }
            )
            
            if not storage_response or hasattr(storage_response, 'error'):
                raise Exception(f"Storage upload failed: {getattr(storage_response, 'error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Supabase Storage 업로드 실패: {str(e)}")
            raise HTTPException(status_code=500, detail="이미지 저장에 실패했습니다")
        
        # 8. 공개 URL 생성
        try:
            public_url_response = supabase.storage.from_(STORAGE_BUCKET).get_public_url(save_name)
            public_url = public_url_response
        except Exception as e:
            logger.error(f"공개 URL 생성 실패: {str(e)}")
            # 업로드된 파일 삭제 시도
            try:
                supabase.storage.from_(STORAGE_BUCKET).remove([save_name])
            except:
                pass
            raise HTTPException(status_code=500, detail="이미지 URL 생성에 실패했습니다")
        
        # 9. 데이터베이스에 메타데이터 저장
        uploaded_at = datetime.utcnow().isoformat()
        
        try:
            result = supabase.table("image").insert({
                "url": public_url,
                "filename": original_filename,
                "file_size": len(optimized_content),
                "uploaded_at": uploaded_at,
                "storage_path": save_name
            }).execute()
            
            if not result.data:
                # DB 저장 실패 시 Storage에서 파일 삭제
                try:
                    supabase.storage.from_(STORAGE_BUCKET).remove([save_name])
                except:
                    pass
                raise HTTPException(status_code=500, detail="데이터베이스 저장에 실패했습니다")
                
        except Exception as e:
            # DB 저장 실패 시 Storage에서 파일 삭제
            try:
                supabase.storage.from_(STORAGE_BUCKET).remove([save_name])
            except:
                pass
            logger.error(f"DB 저장 실패: {str(e)}")
            raise HTTPException(status_code=500, detail="데이터베이스 저장에 실패했습니다")
        
        logger.info(f"이미지 업로드 성공: {save_name} (최적화된 크기: {len(optimized_content)} bytes)")
        return {
            "url": public_url,
            "filename": original_filename,
            "file_size": len(optimized_content),
            "optimized": len(optimized_content) != len(file_content)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"이미지 업로드 중 예상치 못한 오류: {str(e)}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다")


@router.delete("/delete/{image_id}")
async def delete_image(image_id: int):
    """이미지 삭제 API"""
    try:
        # 1. 데이터베이스에서 이미지 정보 조회
        result = supabase.table("image").select("storage_path").eq("id", image_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
        
        storage_path = result.data[0]["storage_path"]
        
        # 2. Supabase Storage에서 파일 삭제
        try:
            supabase.storage.from_(STORAGE_BUCKET).remove([storage_path])
        except Exception as e:
            logger.error(f"Storage 파일 삭제 실패: {str(e)}")
            # Storage 삭제 실패해도 DB에서는 삭제 진행
        
        # 3. 데이터베이스에서 메타데이터 삭제
        delete_result = supabase.table("image").delete().eq("id", image_id).execute()
        
        if not delete_result.data:
            raise HTTPException(status_code=500, detail="데이터베이스에서 이미지 삭제에 실패했습니다")
        
        logger.info(f"이미지 삭제 성공: {storage_path}")
        return {"message": "이미지가 성공적으로 삭제되었습니다"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"이미지 삭제 중 예상치 못한 오류: {str(e)}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다")


@router.get("/list")
async def list_images(limit: int = 20, offset: int = 0):
    """이미지 목록 조회 API"""
    try:
        result = supabase.table("image").select("*").order("uploaded_at", desc=True).range(offset, offset + limit - 1).execute()
        
        return {
            "images": result.data,
            "total": len(result.data),
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"이미지 목록 조회 중 오류: {str(e)}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다")