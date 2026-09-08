# 视频提取微信小程序接管执行规范

更新时间：2026-09-08

本文件整理自用户本轮完整接管指令，是后续开发、验收和状态汇报的当前执行基准。历史合并文档 `SOURCE_SPEC_V1.md` 仅保留需求来源；两者冲突时，以本文件、当前用户明确决定和真实代码/测试结果为准。

## 1. 目标与边界

- 产品是微信原生小程序，用于提取、预览和保存用户有权保存的公开作品视频、图片与标题文案。
- V1 完全免费、非盈利，固定使用 `DOWNLOAD_ACCESS_MODE=free`；不显示广告或广告占位，不要求广告单元 ID。
- 保留 `rewarded_ad` 代码供未来明确决定启用。届时解析和预览仍免费，只有点击保存时检查权益；完整观看后由服务端幂等解锁 24 小时。
- 不接入按次收费解析 API或来源不明的“去水印接口”。优先使用自建后端、公开页面、公开媒体源和合规开源组件。
- “原始媒体”只指公开来源实际提供的媒体，不能承诺或实施对作者烧录在画面内标识的擦除。
- 只处理公开且用户有权保存的内容。私密、好友可见、付费、会员、年龄/地区限制、DRM、验证码和风控页面必须明确失败，不得规避。

目标平台按独立验收统计：抖音、Bilibili、小红书、微博、快手、普通网页/公开直链。代码中存在适配器不等于已支持；每个平台 3/3 个真实公开样例完整通过后，产品文案才可标为支持。

## 2. 产品闭环

最短路径固定为：复制分享文案或链接 → 打开小程序 → 粘贴 → 开始提取 → 立即进入结果页 → 同页显示真实进度 → 预览 → 保存到相册并显示真实下载进度 → 明确成功或具体失败。

- 历史记录只用于最近 24 小时任务恢复，不得成为完成下载的必经步骤。
- 首页不预选原画、720P 或 540P；解析后在结果页展示后端实际提供的源。
- 首页包含标题、分享文案输入、粘贴、开始提取、免费说明、教程、FAQ、我的和“首页/我的”底部导航。
- 首版不显示会员、充值、卡密、积分、收藏、批量解析和广告占位。
- “我的”不要求手机号、头像或昵称，只使用服务所需的微信身份。

结果页固定三个 Tab：

- 视频：实际清晰度、大小、编码/压缩状态、多真实源、预览、复制短期链接、保存进度和明确重试。
- 图片：只显示作品明确返回的真实图片，封面不冒充作品图片；支持逐张保存，无图片显示空状态。
- 标题：作品标题、原分享文案、复制标题和复制全部。

教程控制在 6 步内。FAQ如实说明免费模式、失败原因、平台变化、临时缓存、相册权限和“原始媒体”的含义。

## 3. 架构与 API

保持现有微信原生 WXML/WXSS/JavaScript 与 FastAPI/Pydantic v2/SQLAlchemy 2/Alembic/SQLite/httpx/pytest/Ruff 技术栈。yt-dlp 和 FFmpeg 只用于公开媒体的标准提取、重封装、DASH 合并和兼容编码；Playwright 只用于明确隔离、默认关闭的平台会话服务。

生产职责至少拆分为 API、普通解析任务 Worker、FFmpeg 媒体任务、抖音隔离会话 Worker、临时媒体存储、SQLite 数据卷、清理任务与 Caddy HTTPS 代理。V1 单机可运行，但抖音会话 Worker 不得暴露公网端口。

统一 API 前缀 `/api/v1`，保留并完善：

- `GET /health`
- `POST /auth/wechat`
- `GET /entitlement`
- `POST /entitlement/ad-attempt`
- `POST /entitlement/ad-complete`
- `POST /parse`
- `GET /parse/jobs`
- `GET /parse/jobs/{job_id}`
- `PATCH /parse/jobs/{job_id}/source`
- `DELETE /parse/jobs/{job_id}`
- `GET /media/{token}/preview`
- `GET /media/{token}/download`

`POST /parse` 接受完整分享文案；存在多个链接时不得猜测。任务创建返回 HTTP 202，小程序携带 `job_id` 立即进入结果页。所有任务绑定当前用户，任务状态返回真实进度/阶段；成功与失败均有 `request_id`，失败有稳定 code、中文 message 和 retryable。

媒体 Token 只能映射服务端已验证媒体，默认 900 秒有效，支持 Range，不成为任意 URL 代理。Token、完整媒体路径、签名和敏感请求头不得进入 access log。当前期限明确区分为：任务和媒体记录 24 小时；访问 Token 900 秒；异常/过期临时文件清理上限由 `TEMP_FILE_TTL_SECONDS` 单独配置，当前默认 90000 秒，以覆盖 24 小时媒体记录而不与 Token TTL 混用。

可直接使用的 HTTPS MP4 在解析阶段只做安全元数据探测，用户预览/保存时才通过短期 Token 代理传输；需要 DASH 合并、重封装、格式兼容或降档时才落盘处理。不得把“所有媒体预先完整下载”写成当前实现。

## 4. 媒体与 Parser

- 支持 MP4 与公开 DASH 合并；必要时输出 H.264 + AAC 单一 MP4。
- 源文件临时上限默认 2GiB，可配置；小程序成品默认上限 180MiB，可配置。
- 超限时优先生成如实标注的兼容降档版本，不能把降档冒充原视频；无法安全处理时返回明确错误。
- FFmpeg 默认最多并行一路，临时文件由 TTL 清理，SQLite 文件不得被媒体清理误删。
- 解析速度与视频时长尽量解耦；取得安全媒体信息后先展示，真正的大文件传输在用户点击保存后开始。

每个平台实现独立 Parser，统一为 `can_handle(url)` 与 `parse(url, context)`，返回统一 `ParserResult`。优先级为：公开页面明确元数据 → 标准 JSON/JSON-LD/OpenGraph → 与目标作品 ID 严格绑定的公开响应 → 正常公开媒体请求 → 隔离且受限的 yt-dlp → 合规失败。

URL、重定向和媒体始终保留 SSRF、公网 DNS/IP、标准端口、Content-Type、大小、超时、并发及重定向限制。yt-dlp 禁插件、用户 site-packages 与环境代理，超时终止子进程树。

## 5. 抖音专用会话安全边界

匿名公开解析目前通常只能稳定取得作品 ID。允许的窄范围会话方案仅限运营者手动登录的服务器专用账号：

- 不接收或导入用户 Cookie，不接受账号密码参数，不自动填写登录信息。
- storage state 必须位于仓库外，不进入 Git、数据库、日志、API 或小程序。
- 不处理验证码、滑块、设备验证或风险控制；检测到即停止。
- 仅处理公开且用户有权保存的作品。
- 媒体最终必须在不携带 Cookie、Authorization 或 Token 的情况下完成安全 Range 复验。
- 日志仅保留作品 ID、稳定错误码、安全阶段耗时和 `scheme://hostname` 媒体域名。
- `DOUYIN_SESSION_ENABLED` 默认关闭；未完成最终部署方式的 3/3 真实样例前不得接入默认生产路径。

当前事实：运营者专用 headed Chromium 曾对作品 `7678969660380843304` 真实取得媒体域名、无 Cookie 读取 1024 bytes，耗时约 20.2 秒；标准 headless 曾超时。最新 `f15943d599cdab085566662b6c9116751b504a21` 已完成跨域 origin-only Referer 收紧，但尚未真实复测。Xvfb 文件存在但未部署，暖浏览器复用和正式 `/parse` 接入尚未实现。

接管后不得继续无限叠加启发式。先用一键脚本对最新实现只进行一次 Headed smoke：成功后进入生产化；失败时只允许基于完整脱敏证据进行一次集中修正，仍不稳定则保留开关并明确阻塞。

生产化必须选定并验证标准 headless 或独立 Linux Xvfb headed Worker。Xvfb 不开放 VNC/远程桌面，会话目录只读挂载，Worker 仅由 API 内部调用，并具备健康检查、单并发、超时和重启。禁止 stealth、隐藏 webdriver 或其他反检测。

暖浏览器复用要求：Worker 进程复用 Browser；每任务创建/重置隔离 Context/Page；会话文件更新后安全重载；达到最大任务数或生命周期后重建；浏览器失败最多重试一次；不得跨任务保存用户输入或媒体地址。

## 6. 性能目标

这些是目标，必须有真实数据才能标记 PASS：

- `POST /parse` 创建任务与小程序跳转各不超过 500ms。
- 缓存命中不超过 2 秒。
- Generic 直接媒体 P50 ≤ 3 秒、P95 ≤ 8 秒。
- 普通平台解析 P50 ≤ 8 秒、P95 ≤ 15 秒。
- 抖音暖浏览器 P50 ≤ 8 秒、P95 ≤ 15 秒。
- 抖音冷启动可更慢，但不超过 25 秒并显示真实阶段。
- 用户点击保存后 1 秒内进入下载进度状态。

阶段耗时包括 queue、redirect、page_navigation、target_identity、player_mount、media_capture、media_verify、prepare_download、ffmpeg 和 save_delivery；不得记录敏感 URL。

## 7. 测试与真实验收

每个里程碑至少运行：后端 pytest、Ruff、compileall、Alembic 空库升级与 head 校验；前端 Node 测试、小程序静态校验和 production 配置校验；通用 `git diff --check`、Docker build、Caddy validate 与 GitHub Actions。环境不具备的检查必须标为 `NOT VERIFIED`，不能用单元测试替代。

持续覆盖 Parser 契约、SSRF、重定向、错误分类、任务恢复、Range、Token 过期、日志脱敏、媒体清理、并发/超时、页面跳转和结果恢复。

每个平台至少准备 3 个用户有权保存的公开样例：短链接、完整链接、不同长度/形态。支持图文的平台另含公开图文样例。记录测试日期、脱敏页面信息、作品 ID、结果码、耗时、媒体类型、分辨率、大小、无 Cookie Range 结果和 request_id；不记录 Cookie 或媒体签名。

## 8. 部署与发布红线

推荐 Linux、最低 2 核 4GB（低并发）、推荐 4 核 8GB、80–100GB 磁盘、备案/合法 HTTPS 域名、Docker Compose、Caddy、持久卷、每日数据库备份和 TTL 清理。

生产必须禁用 Mock，使用真实微信 AppID/AppSecret，且 AppSecret 只在服务端。小程序只访问 HTTPS 合法域名。部署后抽样确认日志不含 Token、Cookie、媒体路径和签名。

未经用户明确授权，不购买服务、不部署、不修改 DNS、不使用真实生产密钥。以下全部完成前保持 `NOT READY`：目标平台真实样例、抖音最终运行方式、Android/iOS 预览下载保存、权限拒绝恢复、10MB/50MB/接近 180MiB、真实微信登录、HTTPS 合法域名、隐私/协议/类目/主体材料、生产无 Mock、日志抽样、迁移与备份恢复、无 P0/P1，且 `RELEASE_READINESS.md` 明确 READY。

## 9. 里程碑

- M0 接管基线：核对 main/P3/未合并差异，记录代码与文档矛盾，保存本规范并更新总执行入口。
- M1 P3 集中验收：审查最新 P3，提供安全的一键 PowerShell 脚本，完成自动测试后只请求一次 Headed smoke。
- M2 抖音生产化：根据 M1 真实结果选择 headless 或 Xvfb，完成暖浏览器、内部 Worker、健康检查、限流/重启、Registry/任务接入和 3 个真实样例；未达标保持默认关闭。
- M3 平台覆盖：Bilibili、Generic 各补齐 3 个样例；完成微博、小红书、快手独立适配与真实验证；不稳定平台明确降级。
- M4 产品与性能：保证立即跳结果页、真实阶段、按需下载、缓存和性能报告，完成前后端回归。
- M5 部署准备：Compose、Caddy、Alembic、备份/清理、日志、健康检查、一键部署和回滚文档；不实际部署。
- M6 人工发布 Gate：真实微信登录、合法域名、Android/iOS、相册权限、大文件、隐私与提审材料和 Release Readiness。

## 10. 协作与交付

- 不直接修改 main，不 force push，不删除分支，未经用户批准不合并。
- 每个可独立回滚步骤都更新测试、全部通过、更新 `STATUS.md`/`docs/HANDOFF.md`，单独 commit 后立即 push。
- 不提交 `.env`、AppSecret、Cookie、storage state、数据库密码、Authorization、Token、完整签名媒体 URL、缓存或临时文件。
- 普通代码、测试和 CI 故障自主修复。只有手动登录、真实微信凭证、域名/服务器权限、Android/iOS 操作、产品/安全边界变更或合并决定才暂停。
- 每次里程碑报告当前阶段、分支、完整 HEAD、提交、文件、自动测试、Actions、真实验证、`NOT VERIFIED`、工作区、PR/合并状态和用户最多三项操作。

## 11. M0 冲突登记

| 冲突 | 当前裁定 |
|---|---|
| `SOURCE_SPEC_V1.md` 仍包含解析前广告、无历史、单一清晰度等早期要求 | 作为历史来源保留；当前免费模式、24 小时恢复记录、结果页真实多源优先 |
| 架构、README 和隐私草案写结果 2 小时/临时文件 3 小时 | 改为任务/媒体记录 24 小时、Token 900 秒、临时文件 90000 秒并分别说明 |
| 架构写所有媒体都必须先落盘 | HTTPS MP4 安全快路径按需代理；只有处理型媒体预先落盘 |
| P3 配置包含 browser max tasks/TTL，但代码尚无暖复用 | 明确为未实现，不得把配置存在写成能力完成 |
| Xvfb 容器文件存在，但当前只提供待命进程且没有内部 Worker 接口 | 明确为部署骨架，M2 完成前不是生产服务 |
| 适配器/contract tests 已存在，但多数平台缺 3/3 真实样例 | 产品文案不得写“已支持”，状态保持 PARTIAL/NOT VERIFIED |
| 旧 UI 报告仍记录广告保存闭环 | 标注为历史 Mock 证据，不代表当前免费模式或真实广告 Gate |
| P3 文档同时出现“未手动登录”和用户报告的 headed 成功 | 区分“历史单次 headed 成功”和“最新 f15943d 未复测”，不得互相替代 |
