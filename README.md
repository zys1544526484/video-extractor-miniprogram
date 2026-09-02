# 视频提取微信小程序

一个微信原生小程序与 FastAPI 后端组成的公开视频链接提取工具。解析和预览免费；用户完整观看一次微信激励视频广告后，获得 24 小时下载权益。

## 仓库结构

- `miniprogram/`：微信原生小程序。
- `backend/`：FastAPI、解析器、权益和安全媒体代理。
- `docs/`：产品、安全、部署与验收规范。
- `scripts/`：静态检查与烟雾测试。
- `deploy/`：Docker Compose 与 HTTPS 反向代理样例。

## 本地启动

后端需要 Python 3.12：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

小程序在没有真实凭证时使用开发配置。复制 `miniprogram/project.config.json.example` 为 `project.config.json` 后，用微信开发者工具打开 `miniprogram/`。真实 AppID、AppSecret 和广告单元不要提交到 Git。

## 检查

```powershell
npm test
node scripts/validate_miniprogram.js
cd backend
.\.venv\Scripts\python -m compileall app
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check app tests
```

当前发布状态见 `RELEASE_READINESS.md`。没有真实微信凭证、备案 HTTPS 域名和 Android/iOS 真机记录时，项目不可提审。

## 数据迁移与部署

```powershell
cd backend
.\.venv\Scripts\python -m alembic upgrade head
cd ..\deploy
Copy-Item Caddyfile.example Caddyfile
docker compose up -d --build
```

部署前先填写 `backend/.env` 和 `API_DOMAIN`。生产启动会拒绝 Mock 登录；小程序生产配置也会拒绝 Mock API/广告以及非 HTTPS 域名。容器和真实微信能力在本机尚未验证，不能据此提审。
