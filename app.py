"""
ContentForge MVP — AI 文案生成工具
单文件 FastAPI + SQLite + Jinja2 + DeepSeek
"""
import os
import secrets
import hashlib
import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, func
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BASE_DIR = Path(__file__).parent

# ========== 环境变量（不用 dotenv，直接从系统读） ==========
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8080")

# ========== 数据库 ==========
engine = create_engine(
    f"sqlite:///{BASE_DIR}/data.db",
    connect_args={"check_same_thread": False},
)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=func.now())

class Generation(Base):
    __tablename__ = "generations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    topic = Column(Text, nullable=False)
    result = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())

Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ========== 认证 ==========
def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100000)
    return f"{salt}${h.hex()}"

def verify_password(pw: str, hashed: str) -> bool:
    try:
        salt, h = hashed.split("$", 1)
        return h == hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100000).hex()
    except Exception:
        return False

_sessions: dict[str, int] = {}

def create_token(user_id: int) -> str:
    token = secrets.token_hex(32)
    _sessions[token] = user_id
    return token

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get("token")
    if not token or token not in _sessions:
        return None
    return db.query(User).filter_by(id=_sessions[token]).first()

# ========== App ==========
app = FastAPI(title="ContentForge")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def ctx(request: Request, user: User | None = None, **kw):
    return {"request": request, "user": user, **kw}

# ========== 页面路由 ==========
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", ctx(request))

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", ctx(request))

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", ctx(request))

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login")
    history = (
        db.query(Generation)
        .filter_by(user_id=user.id)
        .order_by(Generation.created_at.desc())
        .limit(20)
        .all()
    )
    return templates.TemplateResponse(
        request, "dashboard.html", ctx(request, user, history=history)
    )

# ========== 认证 API ==========
@app.post("/api/register")
async def api_register(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
):
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(400, "邮箱已注册")
    if len(password) < 6:
        raise HTTPException(400, "密码至少6位")

    user = User(email=email, username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()

    token = create_token(user.id)
    resp = RedirectResponse("/dashboard", 302)
    resp.set_cookie("token", token, max_age=365 * 86400, httponly=True, samesite="lax")
    return resp

@app.post("/api/login")
async def api_login(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
):
    user = db.query(User).filter_by(email=email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(400, "邮箱或密码错误")

    token = create_token(user.id)
    resp = RedirectResponse("/dashboard", 302)
    resp.set_cookie("token", token, max_age=365 * 86400, httponly=True, samesite="lax")
    return resp

@app.get("/logout")
async def logout():
    resp = RedirectResponse("/")
    resp.delete_cookie("token")
    return resp

# ========== AI 生成 API ==========
@app.post("/api/generate")
async def api_generate(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
    topic: str = Form(...),
    style: str = Form("professional"),
    length: str = Form("medium"),
):
    if not user:
        raise HTTPException(401)

    length_map = {"short": "约100-200字", "medium": "约400-600字", "long": "约800-1200字"}
    style_map = {
        "professional": "专业正式",
        "casual": "轻松活泼",
        "persuasive": "有说服力",
    }

    prompt = (
        f"你是一个专业文案撰写助手。请用中文回答。\n\n"
        f"请根据以下主题撰写一段营销文案：\n"
        f"主题：{topic}\n"
        f"风格：{style_map.get(style, '专业')}\n"
        f"长度：{length_map.get(length, '约400-600字')}\n"
        f"要求：内容实用、有吸引力、可直接使用。"
    )

    result = await call_deepseek(prompt)
    if not result:
        return JSONResponse({"error": "生成失败，请稍后重试", "success": False})

    gen = Generation(user_id=user.id, topic=topic, result=result)
    db.add(gen)
    db.commit()

    return JSONResponse({"success": True, "result": result})

async def call_deepseek(prompt: str) -> str | None:
    """调用 DeepSeek API。无 key 则直接报错，不伪造数据。"""
    if not DEEPSEEK_KEY:
        return None

    try:
        import openai
        client = openai.OpenAI(api_key=DEEPSEEK_KEY, base_url="https://api.deepseek.com")

        # 用 run_in_executor 避免阻塞 event loop
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=2000,
                timeout=30,
            ),
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"DeepSeek error: {e}")
        return None

# ========== 健康检查 ==========
@app.get("/health")
async def health():
    return {"status": "ok", "deepseek": bool(DEEPSEEK_KEY)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
