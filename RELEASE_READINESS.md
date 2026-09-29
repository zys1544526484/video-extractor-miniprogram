# Release Readiness — V1

更新时间：2026-09-29

## 当前结论

**本机后端真实链路已验证；不可提审（NOT READY）**。本轮修复了开发版应用启动抛错，以及匿名抖音解析可能拿到推荐作品的缺陷。已交付 `npm run start:local`，使用独立开发数据库、真实解析与下载，微信身份仅为开发模拟。

2026-09-29 实测公开 W3C Sintel MP4：任务 202、Range 预览 206、完整下载 200/4,372,373 bytes、记录再次读取通过；FFprobe 为 H.264/AAC、854×480、52.208 秒。微信开发者工具实际打开项目返回“需要重新登录（code 10）”，因此本轮界面及手机保存仍未验收。

本地自动门禁：pytest `243 passed`（2 warnings）、Node `52 passed`、小程序普通/合成 production 各 `82 files checked`，Ruff、compileall、Alembic 空库升级/head 与后端合成 production 配置通过。Docker CLI 本机未安装；代码检查点 `b8058ea` 的 [CI](https://github.com/zys1544526484/video-extractor-miniprogram/actions/runs/36575091183) 两个 job 成功，包含 Docker build/Caddy validate；远程 pytest `240 passed, 3 skipped`（共 243）、Node 52、小程序普通/production 各 80 文件。后续提交以对应 Actions 运行结果为准。

抖音 M1 已有单条真实 Headed 主播放器归属及无 Cookie Range PoC 成功证据；尚未接入正式解析任务、验证 Linux/Xvfb、暖浏览器、完整下载与 3/3 样例，不等于生产能力。

## 落地顺序

1. **本机可见可用**：手动重新登录微信开发者工具，运行 `npm run start:local`，验收粘贴 → 结果页进度 → 预览 → 提取记录。当前登录是唯一界面验收阻塞。
2. **确定首版可支持范围**：公开直链和已有 Bilibili 能力优先完成各 3 个真实样例；抖音、小红书、微博、快手逐平台验证，不把适配器存在当成支持，也不承诺“任意链接”。
3. **接入部署环境**：提供可操作服务器、HTTPS 域名和微信服务端凭证的安全接入方式；凭证仅放服务器环境，不发送到聊天或 Git。按 `deploy/README.md` 迁移、启动、健康检查，再做备份恢复和日志抽样。
4. **手机交付验收**：真实 `wx.login`、Android/iOS 预览与相册保存、权限拒绝恢复、大文件和网络切换；隐私、主体、类目材料齐全后才能给出 READY。

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
- 当前自动测试以本文件顶部本轮记录为准；旧 32/99 项是 P0 历史结果。Alembic 当前 head 为 `0004_remote_media_sessions`。本地小程序文件数包含两个忽略的工具配置，干净 Git checkout 少 2 个，跳过的测试不得计为通过。
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
- 不得导入用户 Cookie、自动登录或绕过付费、私密、风控、验证码、地域、年龄、DRM。唯一可选运营者专用会话 PoC 以 `AGENTS.md` 的仓库外存储、显式开关和人工登录约束为准，当前不进入默认生产路径。
- Generic 与全部真实平台均不可用时不得发布。
- 发布候选不得存在 P0/P1；单平台只能以明确的“维护中/当前受限”降级。
