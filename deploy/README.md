# 部署说明

1. 将 `backend/.env.example` 复制为 `backend/.env`，填写生产值。
2. 将 `Caddyfile.example` 复制为 `Caddyfile`，设置环境变量 `API_DOMAIN`。
3. 确保域名已备案、DNS 指向服务器，80/443 可达。
4. 执行 `docker compose up -d --build`。
5. 验证 `https://你的域名/api/v1/health`，再把该域名加入微信 request/download 合法域名。

SQLite V1 固定单 API 进程；升级到多副本前必须迁移到托管数据库，并把解析并发控制移到共享存储。
