"""ContentForge - AI Content Generation SaaS"""
import os
from datetime import datetime, timedelta
from pathlib import Path

import secrets
import hashlib

from fastapi import FastAPI, Request, Depends, HTTPException, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, Text, func
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BASE_DIR = Path(__file__).parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except Exception:
    pass

# --- Database ---
engine = create_engine(f"sqlite:///{BASE_DIR}/contentforge.db", connect_args={"check_same_thread": False})

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    plan = Column(String(20), default="free")  # free, pro, business
    credits = Column(Integer, default=10)       # free users get 10 credits
    total_generated = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    last_login = Column(DateTime, default=func.now())

class Generation(Base):
    __tablename__ = "generations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    tool_type = Column(String(50), nullable=False)
    prompt = Column(Text, nullable=False)
    result = Column(Text, nullable=False)
    tokens_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    plan = Column(String(20), nullable=False)
    amount = Column(Integer, nullable=False)  # cents
    status = Column(String(20), default="pending")
    stripe_session_id = Column(String(255))
    created_at = Column(DateTime, default=func.now())

Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Auth ---
import hashlib

def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100000)
    return f"{salt}${h.hex()}"

def verify_password(pw: str, hashed: str) -> bool:
    try:
        salt, h = hashed.split("$", 1)
        computed = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100000)
        return h == computed.hex()
    except Exception:
        return False


# Simple token-based sessions
_sessions = {}  # token -> user_id

def create_token(user_id: int) -> str:
    token = secrets.token_hex(32)
    _sessions[token] = user_id
    return token

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get("cf_token")
    if not token or token not in _sessions:
        return None
    return db.query(User).filter_by(id=_sessions[token]).first()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = db.query(User).filter_by(id=int(payload["sub"])).first()
        return user
    except (JWTError, ValueError):
        return None

# --- Stripe ---
STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "")
stripe_available = False
if STRIPE_KEY:
    import stripe
    stripe.api_key = STRIPE_KEY
    stripe_available = True

PLANS = {
    "free":  {"name": "免费版", "price": 0, "credits": 10, "features": ["每月10积分", "基础AI写作", "文本最多2000字"]},
    "pro":   {"name": "专业版", "price": 29, "credits": 200, "features": ["每月200积分", "高级AI写作", "SEO优化", "社交媒体生成", "邮件营销", "文本最多5000字", "优先支持"]},
    "business": {"name": "企业版", "price": 99, "credits": 1000, "features": ["每月1000积分", "全部功能", "无限字数", "API接入", "团队协作", "专属客服"]},
}

TOOLS = [
    {"id": "blog", "name": "博客文章", "icon": "file-text", "desc": "生成SEO优化的博客文章", "color": "blue"},
    {"id": "social", "name": "社交媒体", "icon": "share2", "desc": "生成各平台社交媒体文案", "color": "pink"},
    {"id": "email", "name": "邮件营销", "icon": "mail", "desc": "撰写高转化营销邮件", "color": "green"},
    {"id": "product", "name": "产品描述", "icon": "package", "desc": "生成吸引人的产品详情", "color": "purple"},
    {"id": "seo", "name": "SEO优化", "icon": "search", "desc": "优化现有内容提升排名", "color": "orange"},
    {"id": "ad", "name": "广告文案", "icon": "megaphone", "desc": "撰写高点击率广告文案", "color": "red"},
]

# --- App ---
app = FastAPI(title="ContentForge", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- Template helpers ---
def template_ctx(request: Request, user: User | None = None, **extra):
    return {
        "request": request,
        "user": user,
        "plans": PLANS,
        "tools": TOOLS,
        **extra,
    }

# --- Pages ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User | None = Depends(get_current_user)):
    if user:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(request, "index.html", template_ctx(request, user))

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user: User | None = Depends(get_current_user)):
    if user:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(request, "login.html", template_ctx(request, user))

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, user: User | None = Depends(get_current_user)):
    if user:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(request, "register.html", template_ctx(request, user))

@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request, user: User | None = Depends(get_current_user)):
    return templates.TemplateResponse(request, "pricing.html", template_ctx(request, user, active_page="pricing"))

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: User | None = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return RedirectResponse("/login")
    payment_success = request.query_params.get("payment") == "success"
    generations = db.query(Generation).filter_by(user_id=user.id).order_by(Generation.created_at.desc()).limit(10).all()
    return templates.TemplateResponse(request, "dashboard.html", template_ctx(request, user, generations=generations, active_page="dashboard", payment_success=payment_success))

@app.get("/tool/{tool_id}", response_class=HTMLResponse)
async def tool_page(tool_id: str, request: Request, user: User | None = Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login")
    tool = next((t for t in TOOLS if t["id"] == tool_id), None)
    if not tool:
        raise HTTPException(404)
    return templates.TemplateResponse(request, f"tools/{tool_id}.html", template_ctx(request, user, tool=tool, active_page="tools"))

# --- Auth API ---
@app.post("/api/auth/register")
async def api_register(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
):
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(400, "邮箱已注册")
    if db.query(User).filter_by(username=username).first():
        raise HTTPException(400, "用户名已存在")
    if len(password) < 6:
        raise HTTPException(400, "密码至少6位")

    user = User(
        email=email,
        username=username,
        password_hash=hash_password(password),
        credits=PLANS["free"]["credits"],
    )
    db.add(user)
    db.commit()

    token = create_token(user.id)
    resp = RedirectResponse("/dashboard", 302)
    resp.set_cookie("cf_token", token, max_age=365 * 86400, httponly=True)
    return resp

@app.post("/api/auth/login")
async def api_login(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
):
    user = db.query(User).filter_by(email=email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(400, "邮箱或密码错误")

    user.last_login = datetime.utcnow()
    db.commit()

    token = create_token(user.id)
    resp = RedirectResponse("/dashboard", 302)
    resp.set_cookie("cf_token", token, max_age=365 * 86400, httponly=True)
    return resp

@app.get("/logout")
async def logout():
    resp = RedirectResponse("/")
    resp.delete_cookie("cf_token")
    return resp

# --- AI Generation API ---
@app.post("/api/generate")
async def api_generate(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
    tool_type: str = Form(...),
    prompt: str = Form(...),
    topic: str = Form(""),
    style: str = Form("professional"),
    length: str = Form("medium"),
    keywords: str = Form(""),
):
    if not user:
        raise HTTPException(401)

    if user.credits <= 0:
        return JSONResponse({"error": "积分不足，请升级套餐", "success": False})

    # Build the AI prompt
    full_prompt = build_prompt(tool_type, topic, prompt, style, length, keywords)
    result = await call_openai(full_prompt)

    if not result:
        return JSONResponse({"error": "生成失败，请稍后重试", "success": False})

    # Save
    tokens = len(result) // 4  # rough estimate
    gen = Generation(user_id=user.id, tool_type=tool_type, prompt=prompt, result=result, tokens_used=tokens)
    db.add(gen)

    user.credits -= 1
    user.total_generated += 1
    db.commit()

    return JSONResponse({"success": True, "result": result, "credits_left": user.credits})

def build_prompt(tool_type: str, topic: str, prompt: str, style: str, length: str, keywords: str) -> str:
    length_map = {"short": "约200字", "medium": "约500-800字", "long": "约1500-2000字"}
    style_map = {
        "professional": "专业正式",
        "casual": "轻松随意",
        "persuasive": "有说服力",
        "creative": "创意活泼",
    }

    base = f"你是一个专业的内容创作助手。请用中文回答。\n\n"
    kw_hint = f"\n关键词（请自然地融入内容）：{keywords}" if keywords else ""

    prompts = {
        "blog": f"{base}请撰写一篇关于「{topic}」的博客文章。\n风格：{style_map.get(style, '专业')}\n长度：{length_map.get(length, '约500-800字')}\n要求：包含引人入胜的标题、小标题分段、实用内容，适合SEO优化。{kw_hint}\n用户额外要求：{prompt}",
        "social": f"{base}请为「{topic}」创作社交媒体文案。\n风格：{style_map.get(style, '专业')}\n要求：适合小红书/微博/朋友圈发布，包含emoji和话题标签，吸引互动。{kw_hint}\n用户额外要求：{prompt}",
        "email": f"{base}请撰写一封关于「{topic}」的营销邮件。\n风格：{style_map.get(style, '有说服力')}\n要求：包含吸引人的邮件主题、个性化开头、清晰的价值主张和行动号召。{kw_hint}\n用户额外要求：{prompt}",
        "product": f"{base}请为「{topic}」撰写产品描述。\n风格：{style_map.get(style, '有说服力')}\n要求：突出产品特点、使用场景、解决什么问题，激发购买欲望。{kw_hint}\n用户额外要求：{prompt}",
        "seo": f"{base}请优化以下内容的SEO：\n原文：{topic}\n要求：改进标题、增加关键词密度、优化meta描述、增加内部链接建议。\n用户额外要求：{prompt}",
        "ad": f"{base}请为「{topic}」撰写广告文案。\n风格：{style_map.get(style, '有说服力')}\n长度：{length_map.get(length, '约200字')}\n要求：抓住注意力、突出卖点、包含强有力的行动号召（CTA）。{kw_hint}\n用户额外要求：{prompt}",
    }

    return prompts.get(tool_type, f"{base}{prompt}\n\n主题：{topic}")

async def call_openai(prompt: str) -> str | None:
    """Call AI API. Supports OpenAI, DeepSeek, or falls back to mock."""
    import openai

    # Try DeepSeek first
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if api_key:
        try:
            client = openai.OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=4000,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"DeepSeek error: {e}")

    # Try OpenAI
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        try:
            client = openai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=2000,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"OpenAI error: {e}")

    # Fallback mock content for demo
    return generate_mock(prompt)

def generate_mock(prompt: str) -> str:
    """Generate demo content when no API key available."""
    if "博客" in prompt:
        return """# 🚀 2024年AI内容创作完全指南

## 为什么AI内容创作正在改变游戏规则

在数字化时代，内容为王。但创作高质量内容需要大量时间和精力。AI内容创作工具的出现，让这一切变得简单。

### 核心优势

1. **效率提升10倍** —— 原来需要一整天写的文章，现在30分钟完成
2. **质量稳定** —— AI不会累，每篇文章都保持高水准
3. **SEO友好** —— 自动优化关键词，提升搜索排名

### 如何开始？

选择一款好的AI写作工具。ContentForge就是一个不错的选择，支持多种内容类型生成。

### 最佳实践

- 始终人工审核AI生成的内容
- 加入个人见解和案例
- 保持品牌语调一致

> 💡 **提示**：AI是助手，不是替代品。最好的内容来自人机协作。

---

*本文由 ContentForge AI 辅助生成*"""
    elif "社交" in prompt:
        return """📱 今日份干货分享！

💡 3个提升内容创作效率的小技巧：

1️⃣ 用AI生成初稿，再个性化修改
2️⃣ 建立内容模板库，一键复用
3️⃣ 批量创作，定时发布

#内容创作 #效率提升 #AI写作 #自媒体运营

你用过AI写作工具吗？评论区聊聊你的体验 👇"""
    elif "邮件" in prompt:
        return """主题：🔥 限时优惠：年度订阅享5折！

Hi {用户名}，

你是否曾经为了写一篇像样的文案而熬夜？

ContentForge AI写作助手，让你在几分钟内生成高质量内容：
✅ 博客文章一键生成
✅ 社交媒体文案自动创作
✅ 邮件营销模板应有尽有

🎁 现在升级年度订阅，立享5折优惠！

[立即升级] 👈 点击这里

优惠截止日期：本月底

期待你的加入！
ContentForge 团队"""
    elif "产品" in prompt:
        return """# ✨ ContentForge Pro —— 你的AI写作搭档

## 产品概述
ContentForge Pro 是一款基于GPT-4的智能内容创作工具，帮助创作者、营销人员和企业家快速生成各类高质量内容。

## 核心功能

| 功能 | 说明 |
|------|------|
| 📝 博客写作 | SEO优化的长文生成 |
| 📱 社交媒体 | 多平台适配的短文案 |
| 📧 邮件营销 | 高转化率的营销邮件 |
| 🏷️ 产品描述 | 吸引人的产品介绍 |

## 为什么选择我们？

- ⚡ **极速生成** —— 平均30秒完成一篇文章
- 🎯 **精准定制** —— 支持风格、长度、关键词自定义
- 💰 **超高性价比** —— 每月仅需29元

## 适合谁用？

创业者、自媒体人、市场营销、电商运营、自由职业者……

> 已经有10,000+创作者选择了ContentForge

[免费试用] [了解更多]"""
    else:
        return """这是一段AI生成的高质量内容。

根据你的需求，我已经优化了文案结构和关键词布局。

### 主要亮点
- 结构清晰，易于阅读
- 关键词自然融入
- 符合SEO最佳实践

你可以直接使用或根据需要修改。"""

# --- Payment API ---
@app.post("/api/payment/create-checkout")
async def create_checkout(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401)

    body = await request.json()
    plan_id = body.get("plan", "pro")

    if plan_id not in PLANS or plan_id == "free":
        raise HTTPException(400, "Invalid plan")

    plan = PLANS[plan_id]

    if stripe_available:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "cny",
                    "product_data": {"name": f"ContentForge {plan['name']}"},
                    "unit_amount": plan["price"] * 100,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=str(request.base_url) + "dashboard?payment=success",
            cancel_url=str(request.base_url) + "pricing",
            metadata={"user_id": str(user.id), "plan": plan_id},
        )

        order = Order(user_id=user.id, plan=plan_id, amount=plan["price"] * 100, stripe_session_id=session.id)
        db.add(order)
        db.commit()

        return {"url": session.url}

    # Demo mode: instantly upgrade
    user.plan = plan_id
    user.credits = plan["credits"]

    order = Order(user_id=user.id, plan=plan_id, amount=plan["price"] * 100, status="completed")
    db.add(order)
    db.commit()

    return {"success": True, "message": f"已升级到{plan['name']}", "url": None}



# --- Health Check ---
@app.get("/health")
async def health():
    return {"status": "ok"}

# --- Stripe Webhook ---
@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    if not stripe_available:
        return JSONResponse({"error": "Stripe not configured"}, status_code=400)

    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
    except Exception:
        raise HTTPException(400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = int(session["metadata"]["user_id"])
        plan_id = session["metadata"]["plan"]

        user = db.query(User).filter_by(id=user_id).first()
        if user:
            user.plan = plan_id
            user.credits = PLANS[plan_id]["credits"]
            db.commit()

        # Update order
        order = db.query(Order).filter_by(stripe_session_id=session["id"]).first()
        if order:
            order.status = "completed"
            db.commit()

    return {"status": "ok"}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
