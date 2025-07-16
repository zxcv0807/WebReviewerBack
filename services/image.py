from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from datetime import datetime
import os
from .db import get_db

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter()

@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    # 파일 확장자 체크 (보안)
    if not file.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
        raise HTTPException(status_code=400, detail="Invalid file type")
    # 저장 경로 생성
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    ext = os.path.splitext(str(file.filename))[1]
    save_name = f"{timestamp}{ext}"
    save_path = os.path.join(UPLOAD_DIR, save_name)
    # 파일 저장
    with open(save_path, "wb") as f:
        f.write(await file.read())
    # DB에 기록
    conn = get_db()
    cursor = conn.cursor()
    url = f"/uploads/{save_name}"
    uploaded_at = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO image (url, filename, uploaded_at) VALUES (%s, %s, %s)",
        (url, file.filename, uploaded_at)
    )
    conn.commit()
    conn.close()
    return {"url": url}