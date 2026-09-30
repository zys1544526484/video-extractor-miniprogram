# 部署说明

1. 将 `backend/.env.production.example` 复制为 `backend/.env`，填写生产值。已有文件先备份，不要覆盖；凭证只保存在服务器，禁止提交。
2. 将 `Caddyfile.example` 复制为 `Caddyfile`，设置环境变量 `API_DOMAIN`。
3. 确保域名已备案、DNS 指向服务器，80/443 可达。
4. 在 `deploy` 目录执行 `docker compose up -d --build --wait --wait-timeout 120`。API 以非 root 用户启动，先迁移数据库，再通过健康检查；Caddy 等待 API 健康后才启动。
5. 验证 `https://你的域名/api/v1/health`，再把该域名加入微信 request/download 合法域名。

SQLite V1 固定单 API 进程；升级到多副本前必须迁移到托管数据库，并把解析并发控制移到共享存储。

API 健康探针只访问容器内的 `/api/v1/health`，不使用凭证、不调用平台。停止时给予 30 秒清理窗口；不要用 `docker compose down -v` 删除数据库和媒体卷。若启动失败，先查看 `docker compose ps` 与脱敏日志，不要跳过 Alembic 或开启 Mock。

CI 使用虚构配置验证镜像真实启动、非 root、FFmpeg、迁移到 head、正常停止及同卷重启；不能替代真实域名/TLS、微信登录、备份恢复和真机验收。健康状态用于启动依赖，不等同自动恢复所有运行中故障；`restart: unless-stopped` 只在进程退出时重启。启动顺序依据 [Docker Compose 官方说明](https://docs.docker.com/compose/how-tos/startup-order/)。
# 可选抖音专用会话（Xvfb headed）

该服务默认不启动，也不暴露端口、VNC 或远程桌面。仅当标准 headless 经人工验证仍不稳定时，才在 Linux 上使用独立容器：

```sh
export DOUYIN_STORAGE_STATE_DIR=/srv/douyin-session
docker compose -f docker-compose.yml -f docker-compose.douyin-session.yml --profile douyin-session up -d --build
```

目录必须位于仓库外，包含由运营者手动登录得到的 `operator-state.json`，并以只读方式挂载。该运行方式不处理验证码、风控或登录；健康检查只验证显式开关和会话文件格式，不读取或输出 Cookie。
