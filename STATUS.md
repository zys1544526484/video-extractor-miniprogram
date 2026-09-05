# STATUS

更新时间：2026-09-05

## 当前阶段

- P1 参考结果页与多媒体源：`IMPLEMENTED / LOCAL VERIFIED`。首页已移除画质预选；结果页提供视频/图片/标题 Tab、真实源列表切换、短期能力链接复制和图片保存；旧单源结果缓存兼容。源2刷新/历史重开会保持，只有服务端确认源已过期才回退并提示；视频封面不会自动进入作品图片列表，纯图片结果使用 `media_type=image`。图片链路现已走独立 SafeHttpClient 探测/下载路径，数据库清理不会误删 TEMP_DIR 中的 SQLite 文件。

- Phase 00 工程基线：`COMPLETE`。
- Phase 01–03 微信端与 Mock 闭环：`COMPLETE / LOCAL VERIFIED`。
- Phase 04–16 后端、权益、安全代理：`COMPLETE / LOCAL VERIFIED`。
- Phase 17–22 平台适配：代码和 contract tests 已完成；Generic 与 Bilibili 各有 1 个真实视频网络样例通过，其余平台 `NOT VERIFIED`；抖音、小红书、快手、微博、Bilibili 的图文解析全部保持 `NOT VERIFIED`。
- Phase 23–26 部署与发布：Docker/Alembic/Caddy 文件已完成；微信开发者工具 Mock 主流程已本机验证，容器、真机和生产部署 `NOT VERIFIED`。
- P0 安全与生产门禁：媒体访问 Token 短期 TTL、Token/媒体保留时间拆分、应用/Caddy 日志脱敏、HTTP(S) 标准端口 SSRF 校验、production Alembic head 校验和 CI 门禁已实现；最新分支 push CI 的两个 job 均成功。自动化门禁已通过，但部署后的日志抽样、真机和生产环境仍为 `NOT VERIFIED`，因此不代表 P0 全部上线条件已完成。

## 本地验证结果

- 前端 Node 单测：本地 `npm test` 32 passed、0 failed；GitHub 最新分支 push CI 为 32 passed、0 failed。
- 小程序 JSON、路由、资源引用、JS 语法：本地工作区 76 files checked；GitHub 干净环境 74 files checked，均通过。本地多出的 `miniprogram/project.config.json` 与 `miniprogram/project.private.config.json` 是 `.gitignore` 忽略的本地配置，不提交。
- 后端 pytest：本地当前测试 `99 passed`（2 warnings）；最新分支 push CI 为 `96 passed、3 skipped`（共收集 99 项），skipped 主要因 runner 未安装 ffmpeg/ffprobe，不计为 passed。
- `ruff check app tests alembic`：本地复跑通过；最新分支 push CI 为 All checks passed。
- 除明确标注“本次收尾复跑”的条目外，其余 PASS 为既有历史验证记录，本次未重跑，不作为本次收尾的新验证。
- `compileall app alembic`：本地 PASS；最新分支 push CI PASS。
- Alembic 空 SQLite 数据库升级到 `0003_parse_jobs_media_sessions`：本地 PASS；最新分支 push CI PASS。
- Uvicorn 进程级 health/auth/entitlement/ad-complete：PASS。
- 首版正式免费模式：`DOWNLOAD_ACCESS_MODE=free` 时登录用户可直接下载，前端隐藏广告与权益 Gate，生产配置不要求 adUnitId；广告模式代码保留但默认关闭。
- 本轮结果来源修正：`/media/{token}/download` 是可独立打开的短期能力链接，不要求小程序 `Authorization` 请求头；`rewarded_ad` 仍在服务端按媒体会话所属用户检查权益。后端新增独立链接、源2续签/过期回退和 Generic 直接图片/画廊测试；本轮最终后端 pytest 110 项、前端 Node 43 项均通过。
- 本轮图片与源选择收尾复跑：真实 `SafeHttpClient` + 模拟网络响应覆盖图片直链、网页图片解析、落盘、预览和下载；`PATCH /parse/jobs/{job_id}/source` 与页面级 A/B/A、历史失效回退、过期复制刷新测试均通过。`npm run validate:miniprogram`（79 files）、合成 `npm run validate:production`、Ruff、compileall、`git diff --check` 均 PASS。
- Issue #3 单图语义修正：纯图片页显式 `img`/JSON-LD 即使重复 `og:image` 也会返回作品图片；视频页重复封面仍会排除；`.gif` 不再作为直接图片入口。后端 pytest 本轮为 113 passed；五个平台图文解析仍为 `NOT VERIFIED`。
- 持久解析任务：创建/轮询/取消、幂等、用户隔离、服务重启恢复、页面重开续查和 0–100 进度自动测试 PASS；任务与媒体会话存入 SQLite，媒体结果保留 24 小时。每次返回的 `result.expires_at` 是当前访问 Token 的实际过期时间，`media_expires_at` 独立表示媒体保留截止时间；结果页保存前按 Token 过期时间刷新，Token 失效不会延长媒体会话。
- 媒体访问安全：`MEDIA_ACCESS_TOKEN_TTL_SECONDS` 默认 900 秒，媒体会话保留 24 小时并支持重新签发；应用请求日志掩码媒体 Token，Caddy access log 删除 URI/请求头；公开 URL 仅允许 HTTP 80 或 HTTPS 443。
- production 数据库启动：不再依赖 `create_all`；启动前校验数据库存在且 Alembic 已到 head，迁移由部署命令负责。
- 提取记录与后台任务：已实现提取记录页面和入口、最多同时维护 2 个后台任务、活动任务状态刷新/恢复，以及在 24 小时结果有效期内从提取记录再次打开结果；本次 Node 单测 30/30 覆盖相关逻辑。微信真机交互、长任务和真实相册保存仍为 `NOT VERIFIED`。
- 大视频媒体管道：2GiB 源暂存上限、64KiB 分块流式下载、Range 断点续传、10GiB 磁盘门禁、FFprobe 校验和 FFmpeg H.264/AAC 自动压缩已通过自动测试；最终只交付一个不超过 180MiB 的 MP4。实际大文件真机保存仍 `NOT VERIFIED`。
- Generic 公网 MP4 真实链路：解析、短期 token、Range 预览和带认证下载 PASS（HTTP 206）。
- Bilibili 公开视频真实链路：公开元数据预检、180MiB 内 H.264 自动降档、DASH 下载与 ffmpeg 合并、短期 token、Range 预览和带认证下载 PASS（HTTP 206）；该样例为 480P H.264 + AAC、142,463,085 bytes，真机保存仍 `NOT VERIFIED`。
- 画质策略：后端仍兼容 `original`/`720p`/`540p` 请求参数和旧任务，但首页不再预选；新结果按真实视频源返回并在结果页切换，长视频 Android/iOS 预览和保存尚未真机验证。
- 432×911、360×800、430×932 浏览器视觉验收与核心广告保存流程：PASS。
- 微信开发者工具 Stable 2.02.2608060、基础库 3.17.2、362×783 模拟器：页面加载、输入、Mock 提取、结果页、广告解锁、下载进度和保存成功状态 PASS。
- P0 修复后使用官方开发者工具 CLI 重新执行 `open` 与 `auto`：项目载入/编译 PASS；本轮未把该检查扩大为真机或真实广告验证。
- 旧画质选择版本曾执行官方 CLI `open` 与 `auto`；当前结果源/Tab 改版尚未在微信开发者工具中完成自动截图，需人工确认。当前环境的 CUA 可见浏览器标签但没有微信开发者工具原生应用，且未发现官方 DevTools CLI，因此本轮无法生成新的开发者工具截图；不能将静态校验写成工具/真机验证。
- 首版免费模式改动后再次执行官方开发者工具 CLI `open` 与 `auto`：项目载入/编译 PASS；广告隐藏后的完整视觉与真机保存仍为 `NOT VERIFIED`。
- 持久任务与大视频进度改动后再次执行官方开发者工具 CLI `open` 与 `auto`：项目载入/编译 PASS；65 分钟长任务、接近 180MiB 成品和相册保存仍需真机验证。
- 修复 Windows Uvicorn 事件循环不支持 asyncio 子进程的问题；真实服务再次完成用户提供的 43 分钟 B站样例，输出 171,656,688 bytes 单一 MP4，预览与下载 Range 均为 HTTP 206。
- 小程序上传包估算由约 2.6MiB 降至约 99KiB；测试目录与未使用的大图已通过 `packOptions.ignore` 排除，尚未执行真实上传。
- 上线前 P0 代码修复：体验版/正式版生产配置强制校验、微信登录查询串日志降级、服务端广告尝试凭证、yt-dlp 独立受限子进程与 Windows UTF-8 协议均已本地回归通过。
- 用户提供的抖音公开短链真实 smoke test到达解析器，但上游要求 fresh cookies，按合规边界返回 `CONTENT_RESTRICTED`；没有导入 Cookie，抖音能力仍为 `NOT VERIFIED`。
- GitHub Actions CI：已配置 `codex/**` push 与针对 `main` 的 pull request 触发，并真实运行 `npm run validate:production`；同时执行 production 配置、compileall、Alembic 空库升级/head 校验、Docker build 和固定版本 Caddy `caddy validate`。最新分支 push CI 的前后端两个 job 均成功。

## 已确认产品决策

- 首版解析、预览和保存均免费，仍要求登录和媒体所有权校验。
- 首版不展示 Banner 或激励广告；后续商业化通过 `rewarded_ad` 模式启用。
- 首页不预选画质；解析器返回真实可用源，用户在结果页切换；结果页另提供解析图片与标题/分享文案。
- 提取记录保留 24 小时，用于后台任务恢复和未下载结果再次打开，不作为永久历史托管。
- 相册保存 V1 只交付 MP4；不支持的公开格式返回规范错误。
- 单平台可合规降级，不影响其他平台。

## 发布判断

**不可提审 / NOT READY**。见 `RELEASE_READINESS.md` 和 `BLOCKERS.md`；任何未完成的真实能力均不得写成 PASS。

## 本轮 P1 收尾（2026-09-05）

- 首页创建持久解析任务后立即跳转 `pages/result/result?job_id=...`；结果页按 1.5 秒轮询任务，展示后端进度阶段，成功后加载视频、图片、标题、来源和画质信息，失败时展示稳定 `error_code`、中文原因和“重新提取”。提取记录同步保存具体失败原因。
- 结果页进度条改用微信原生 `progress` 组件，移除动态 `style="width: ..."`，规避开发者工具 CSS 检查器误报。
- 直连路径：对已验证的 HTTPS MP4 源只执行 SafeHttpClient 元数据探测和 SSRF/大小校验，媒体会话保存短期能力所需的受限上游地址，用户点击预览/保存时才代理传输；非 HTTPS、非 MP4、需要降档或元数据不完整的源继续走安全落盘、ffprobe/处理回退路径。新增 Alembic `0004_remote_media_sessions`，兼容旧本地文件会话。
- 本轮不接入 SPAPI 或 media-parser；保留现有 SafeHttpClient、用户归属校验、短期 Token、24 小时媒体清理和 rewarded_ad 权益门禁。
- 本轮本地验证：后端 pytest `116 passed`（2 warnings）；Ruff PASS；`compileall` PASS；前端 Node `46 passed`；`npm run validate:miniprogram`（80 files）PASS；合成 `npm run validate:production` PASS；`git diff --check` PASS。
- 微信开发者工具、真机、真实 HTTPS 合法域名、生产微信登录、五平台真实公开样例和相册保存本轮仍为 `NOT VERIFIED`；当前环境未发现可操作的微信开发者工具原生应用或官方 CLI，静态校验不替代这些人工验收。
- PR #5 已保持 Draft 且未合并；尝试通过 GitHub 连接器同步描述时返回 `403 Resource not accessible by integration`，描述更新需具备 PR 写权限的 GitHub 账号手动完成。
