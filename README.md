# ContentForge - AI内容创作SaaS

## 本地运行

```bash
pip install -r requirements.txt
cp .env.example .env  # 编辑 .env 填入你的 API Key
python -m uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

## Docker 部署

```bash
docker-compose up -d
```

## 一键部署到 Railway

1. 注册 [Railway](https://railway.app)
2. 点击下方按钮:

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new)

3. 在 Railway 仪表板设置环境变量:
   - `OPENAI_API_KEY` - 你的 OpenAI API Key
   - `STRIPE_SECRET_KEY` - Stripe Secret Key
   - `STRIPE_WEBHOOK_SECRET` - Stripe Webhook Secret
   - `SECRET_KEY` - 随机字符串

4. Railway 会自动检测 Dockerfile 并部署

## 部署到 Render

1. 注册 [Render](https://render.com)
2. 新建 Web Service，连接你的 Git 仓库
3. 设置:
   - Runtime: Docker
   - Port: 8080
   - 环境变量同上

## Stripe 支付配置

1. 在 [Stripe Dashboard](https://dashboard.stripe.com) 创建产品和价格
2. 设置 Webhook endpoint: `https://你的域名/api/stripe/webhook`
3. Webhook 事件: `checkout.session.completed`
4. 将 Webhook Signing Secret 填入环境变量

## 自定义域名

部署后在你的平台设置中添加自定义域名，然后在 Stripe 更新 Webhook URL。
