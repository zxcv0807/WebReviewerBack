from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from .db import get_db
import json

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
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        now = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT INTO phishing_site (url, reason, description, status, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (phishing_site.url, phishing_site.reason, phishing_site.description, "검토중", now))
        phishing_site_id = cursor.fetchone()[0] if cursor.description else None
        
        conn.commit()
        
        # 생성된 피싱 사이트 조회
        cursor.execute("SELECT * FROM phishing_site WHERE id = %s", (phishing_site_id,))
        site_row = cursor.fetchone()
        
        return PhishingSiteResponse(
            id=site_row[0],
            url=site_row[1],
            reason=site_row[2],
            description=site_row[3],
            status=site_row[4],
            created_at=site_row[5]
        )
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create phishing site report: {str(e)}")
    finally:
        conn.close()

@router.get("/phishing-sites", response_model=List[PhishingSiteResponse])
def get_phishing_sites(status: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if status:
            cursor.execute("SELECT * FROM phishing_site WHERE status = %s ORDER BY created_at DESC", (status,))
        else:
            cursor.execute("SELECT * FROM phishing_site ORDER BY created_at DESC")
        
        sites = []
        for site_row in cursor.fetchall():
            sites.append(PhishingSiteResponse(
                id=site_row[0],
                url=site_row[1],
                reason=site_row[2],
                description=site_row[3],
                status=site_row[4],
                created_at=site_row[5]
            ))
        
        return sites
        
    finally:
        conn.close()

@router.get("/phishing-sites/{site_id}", response_model=PhishingSiteResponse)
def get_phishing_site(site_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM phishing_site WHERE id = %s", (site_id,))
        site_row = cursor.fetchone()
        
        if not site_row:
            raise HTTPException(status_code=404, detail="Phishing site not found")
        
        return PhishingSiteResponse(
            id=site_row[0],
            url=site_row[1],
            reason=site_row[2],
            description=site_row[3],
            status=site_row[4],
            created_at=site_row[5]
        )
        
    finally:
        conn.close()

@router.put("/phishing-sites/{site_id}", response_model=PhishingSiteResponse)
def update_phishing_site(site_id: int, site_update: PhishingSiteUpdate):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 기존 피싱 사이트 확인
        cursor.execute("SELECT * FROM phishing_site WHERE id = %s", (site_id,))
        existing_site = cursor.fetchone()
        
        if not existing_site:
            raise HTTPException(status_code=404, detail="Phishing site not found")
        
        # 업데이트할 필드들
        update_fields = []
        update_values = []
        
        if site_update.url is not None:
            update_fields.append("url = %s")
            update_values.append(site_update.url)
        
        if site_update.reason is not None:
            update_fields.append("reason = %s")
            update_values.append(site_update.reason)
        
        if site_update.description is not None:
            update_fields.append("description = %s")
            update_values.append(site_update.description)
        
        if site_update.status is not None:
            update_fields.append("status = %s")
            update_values.append(site_update.status)
        
        if update_fields:
            update_values.append(site_id)
            
            cursor.execute(
                f"UPDATE phishing_site SET {', '.join(update_fields)} WHERE id = %s",
                update_values
            )
            conn.commit()
        
        # 업데이트된 피싱 사이트 조회
        cursor.execute("SELECT * FROM phishing_site WHERE id = %s", (site_id,))
        site_row = cursor.fetchone()
        
        return PhishingSiteResponse(
            id=site_row[0],
            url=site_row[1],
            reason=site_row[2],
            description=site_row[3],
            status=site_row[4],
            created_at=site_row[5]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update phishing site: {str(e)}")
    finally:
        conn.close()

@router.delete("/phishing-sites/{site_id}")
def delete_phishing_site(site_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 피싱 사이트 존재 확인
        cursor.execute("SELECT id FROM phishing_site WHERE id = %s", (site_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Phishing site not found")
        
        # 피싱 사이트 삭제
        cursor.execute("DELETE FROM phishing_site WHERE id = %s", (site_id,))
        conn.commit()
        
        return {"msg": "Phishing site deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete phishing site: {str(e)}")
    finally:
        conn.close() 