from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.auth import router as auth_router
from services.post import router as post_router
from services.image import router as image_router
from services.review import router as review_router
from services.phishing import router as phishing_router
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://webreviewer.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")
app.include_router(post_router, prefix="/posts")
app.include_router(review_router, prefix="/api")
app.include_router(phishing_router, prefix="/api")
app.include_router(image_router)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/")
def read_root():
    return {"message": "Backend is running"} 