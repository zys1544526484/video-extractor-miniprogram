# Release Readiness — V1

更新时间：2026-09-04

## 当前结论

**不可提审（NOT READY）**。Token 时间语义、生产配置校验和 Caddy 语法已由自动测试/最新分支 push CI 验证，两个 job 成功；但不代表真实微信能力、部署后日志行为、容器运行或五平台解析已验证。

## 已完成

- 微信原生五页面、首页/我的底部导航和统一视觉变量。
- 首版生产 `free` 模式允许登录用户直接解析、预览和保存，不渲染广告。
- 保留 `rewarded_ad` 模式代码，但不属于首版上线 Gate。
- FastAPI 登录令牌、SQLite 权益与广告幂等审计。
- SQLite 持久解析任务、重启恢复、页面续查、0–100 进度和持久媒体 token 摘要。
- 大源文件分块续传、FFprobe 校验、FFmpeg 自动压缩/降档与单一 MP4 交付管道。
- 体验版/正式版 production 配置门禁、服务端广告尝试凭证和敏感 HTTP 日志抑制。
- Generic 与平台适配器、900 秒短期媒体 token（`expires_at` 为当前 Token 过期时间，`media_expires_at` 为 24 小时媒体保留时间且可重新签发）、Range、大小/超时/并发限制。
- 应用与 Caddy 日志不记录媒体 Token；用户 URL 仅允许 HTTP 80 / HTTPS 443；production 启动校验 Alembic head，不调用 `create_all`。
- yt-dlp 独立受限子进程、禁插件/代理和非公网 DNS 阻断。
- SSRF 公网 IP 固定、逐跳重定向复检、响应大小和 Content-Type 校验。
- Alembic、Dockerfile、Compose 和 Caddy HTTPS 样例。
- 自动测试：本地前端 32 passed、后端 99 passed；小程序本地 76 个文件的结构/语法/资源校验通过；Alembic 空库升级到 `0003_parse_jobs_media_sessions`。最新分支 push CI 为 Node 32 passed、小程序 74 files checked、后端 96 passed/3 skipped（共收集 99 项，skipped 不计为 passed），Ruff 通过。
- GitHub Actions 已真实运行 `npm run validate:production`，并增加 compileall、Alembic 空库升级/head 校验、Docker build 和固定版本 Caddy `caddy validate`；最新分支 push CI 的前后端两个 job 均成功。Caddy 配置语法通过，但部署环境 access log 脱敏仍需人工抽样。
- 微信开发者工具 Stable 2.02.2608060 / 基础库 3.17.2 的 362×783 Mock 主流程通过。

## 未验证 Gate

| Gate | 状态 | 通过条件 |
|---|---|---|
| A 开发者工具 UI | PARTIAL | 362×783 Mock 主流程已通过；五页面、字体放大和 360–430px 多机型仍需人工检查 |
| B 微信身份 | NOT VERIFIED | AppID/AppSecret 与真实 `wx.login` 真机闭环通过 |
| C 真实解析 | NOT VERIFIED | Generic 加至少一个真实平台，各 3 个公开样例有记录 |
| D 真机下载 | NOT VERIFIED | Android/iOS 的 10MB、50MB、接近 180MiB、权限拒绝恢复、4G/Wi-Fi 通过 |
| E 合规与提审 | NOT VERIFIED | 备案 HTTPS、合法域名、隐私指引、类目和主体材料齐备 |

## 发布红线

- 生产配置不得启用任何 Mock。
- 不得导入 Cookie、模拟登录或绕过付费、私密、风控、验证码、地域、年龄、DRM。
- Generic 与全部真实平台均不可用时不得发布。
- 发布候选不得存在 P0/P1；单平台只能以明确的“维护中/当前受限”降级。
