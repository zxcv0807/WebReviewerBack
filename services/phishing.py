from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from supabase import create_client, Client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

router = APIRouter()

# Pydantic Models
class PhishingSiteCreate(BaseModel):
    url: str = Field(..., description="피싱 의심 사이트 링크")
    reason: str = Field(..., description="사유 (예: '가짜 로그인 페이지', '결제 유도', '이메일 피싱')")
    description: Optional[str] = Field(None, description="자세한 설명 (선택사항)")

class PhishingSiteUpdate(BaseModel):
    url: Optional[str] = None
    reason: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = Field(None, description="상태 (검토중, 확인됨, 무시됨)")

class PhishingSiteResponse(BaseModel):
    id: int
    url: str
    reason: str
    description: Optional[str]
    status: str
    created_at: str

# API Endpoints
@router.post("/phishing-sites", response_model=PhishingSiteResponse)
def create_phishing_site(phishing_site: PhishingSiteCreate):
    now = datetime.utcnow().isoformat()
    result = supabase.table("phishing_site").insert({
        "url": phishing_site.url,
        "reason": phishing_site.reason,
        "description": phishing_site.description,
        "status": "검토중",
        "created_at": now
    }).execute()
    phishing_site_id = result.data[0]["id"]
    site_row = supabase.table("phishing_site").select("*").eq("id", phishing_site_id).single().execute().data
    return PhishingSiteResponse(**site_row)

@router.get("/phishing-sites", response_model=List[PhishingSiteResponse])
def get_phishing_sites(status: Optional[str] = None):
    if status:
        sites = supabase.table("phishing_site").select("*").eq("status", status).order("created_at", desc=True).execute().data
    else:
        sites = supabase.table("phishing_site").select("*").order("created_at", desc=True).execute().data
    return [PhishingSiteResponse(**site) for site in sites]

@router.get("/phishing-sites/{site_id}", response_model=PhishingSiteResponse)
def get_phishing_site(site_id: int):
    site_row = supabase.table("phishing_site").select("*").eq("id", site_id).single().execute().data
    if not site_row:
        raise HTTPException(status_code=404, detail="Phishing site not found")
    return PhishingSiteResponse(**site_row)

@router.put("/phishing-sites/{site_id}", response_model=PhishingSiteResponse)
def update_phishing_site(site_id: int, site_update: PhishingSiteUpdate):
    existing_site = supabase.table("phishing_site").select("*").eq("id", site_id).single().execute().data
    if not existing_site:
        raise HTTPException(status_code=404, detail="Phishing site not found")
    update_data = {}
    if site_update.url is not None:
        update_data["url"] = site_update.url
    if site_update.reason is not None:
        update_data["reason"] = site_update.reason
    if site_update.description is not None:
        update_data["description"] = site_update.description
    if site_update.status is not None:
        update_data["status"] = site_update.status
    if not update_data:
        raise HTTPException(status_code=400, detail="No update fields provided")
    try:
        supabase.table("phishing_site").update(update_data).eq("id", site_id).execute()
        site_row = supabase.table("phishing_site").select("*").eq("id", site_id).single().execute().data
        if not site_row:
            raise HTTPException(status_code=404, detail="Phishing site not found after update")
        return PhishingSiteResponse(**site_row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update phishing site: {str(e)}")

@router.delete("/phishing-sites/{site_id}")
def delete_phishing_site(site_id: int):
    if not supabase.table("phishing_site").select("id").eq("id", site_id).single().execute().data:
        raise HTTPException(status_code=404, detail="Phishing site not found")
    try:
        supabase.table("phishing_site").delete().eq("id", site_id).execute()
        return {"msg": "Phishing site deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete phishing site: {str(e)}") 