# 部署说明

1. 将 `backend/.env.example` 复制为 `backend/.env`，填写生产值。
2. 将 `Caddyfile.example` 复制为 `Caddyfile`，设置环境变量 `API_DOMAIN`。
3. 确保域名已备案、DNS 指向服务器，80/443 可达。
4. 执行 `docker compose up -d --build`。
5. 验证 `https://你的域名/api/v1/health`，再把该域名加入微信 request/download 合法域名。

SQLite V1 固定单 API 进程；升级到多副本前必须迁移到托管数据库，并把解析并发控制移到共享存储。
# 可选抖音专用会话（Xvfb headed）

该服务默认不启动，也不暴露端口、VNC 或远程桌面。仅当标准 headless 经人工验证仍不稳定时，才在 Linux 上使用独立容器：

```sh
export DOUYIN_STORAGE_STATE_DIR=/srv/douyin-session
docker compose -f docker-compose.yml -f docker-compose.douyin-session.yml --profile douyin-session up -d --build
```

目录必须位于仓库外，包含由运营者手动登录得到的 `operator-state.json`，并以只读方式挂载。该运行方式不处理验证码、风控或登录；健康检查只验证显式开关和会话文件格式，不读取或输出 Cookie。
