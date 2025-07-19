from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from datetime import datetime
import os
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter()

@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    if not file.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
        raise HTTPException(status_code=400, detail="Invalid file type")
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    ext = os.path.splitext(str(file.filename))[1]
    save_name = f"{timestamp}{ext}"
    save_path = os.path.join(UPLOAD_DIR, save_name)
    with open(save_path, "wb") as f:
        f.write(await file.read())
    url = f"/uploads/{save_name}"
    uploaded_at = datetime.utcnow().isoformat()
    supabase.table("image").insert({
        "url": url,
        "filename": file.filename,
        "uploaded_at": uploaded_at
    }).execute()
    return {"url": url}