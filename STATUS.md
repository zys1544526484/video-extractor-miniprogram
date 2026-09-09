# STATUS

更新时间：2026-09-09

## 当前阶段

- M1 P3 真实 MediaSource 归属集中修正（2026-09-09）：用户在 `e548e6d6dbfd76a8236b1f59ee3f1466530e3f68` 上完成权威 Headed 验收，目标作品 `7678969660380843304`、canonical 页面、唯一可见 blob 主播放器均正确，且捕获 4 个主框架、origin-only Referer、`video/mp4` 响应，但最终仍为 `DOUYIN_SESSION_MEDIA_NOT_FOUND`。审计确认 4 条响应已通过 MIME/Referer/主框架过滤并进入有界观察队列；旧溯源只依赖网络 payload 与 `SourceBuffer.appendBuffer` 参数的 JavaScript 对象身份，真实播放器复制、切片或流式传递数据后该身份丢失，MSE 绑定为空。响应又发生在目标确认前，不会进入后置 `early_candidates`，而 play/seek 没有产生新请求，因此候选组计数为 0。`935c13b0cc26c0f6bd9feda7a590705c6bae2847` 改为在页面脚本前对当前 MediaSource 的每个视频 SourceBuffer 记录有界追加字节样本，再用 SafeHttpClient 以无 Cookie/Authorization/Token 的精确 Range 读取做字节指纹匹配；只有目标页、唯一可见主播放器、允许 Referer、主框架、视频 MIME、SSRF、公网校验和唯一强等价组同时成立才返回候选。多个 SourceBuffer、多个非等价资源或样本不匹配继续安全失败。Smoke/一键验收新增观察、合格、视频缓冲、追加样本、采样尝试/失败/不匹配/匹配、SSRF、陈旧、未观察直链、歧义缓冲及最终绑定组的纯计数，不输出字节、哈希、路径、查询或签名。自动验证为后端 `236 passed`（2 warnings）、Ruff/compileall、Alembic 空库升级/head、后端 production 配置、Node `49 passed`、小程序常规/production 各 `80 files checked` 与 `git diff --check` 全部 PASS；[GitHub Actions run 34305162529](https://github.com/zys1544526484/video-extractor-miniprogram/actions/runs/34305162529) 已成功（含 Docker build 与 Caddy validate）。真实 Headed 修复结果仍为 `NOT VERIFIED`。

- M1 P3 最后一次集中归属修正（2026-09-09）：用户的一键 Headed 真实验收确认 canonical 作品 ID、唯一可见播放器和 blob 来源均正常，并捕获 4 个 `video/mp4` 响应，但这些响应发生在 `player_mount` 前后且后续 seek 未产生新请求，因此以 `DOUYIN_SESSION_MEDIA_NOT_FOUND` 安全失败。commit `de34af6` 在 `goto` 前安装有界 MediaSource 溯源，只在 `Response`/XHR/stream 的 payload 实际进入当前唯一可见主播放器对应的 Blob/MediaSource，且同一 URL 已由 Playwright 观察为主框架、合格 Referer、video/HLS 响应时，才交给既有公网 URL 与无 Cookie Range 复验；广告/推荐、未观察地址、SSRF 地址仍不能绑定。完整媒体 URL 只驻留本次任务内存，`CapturedMedia` repr、日志、JSON 和磁盘均不暴露。自动回归为 backend pytest `227 passed`（2 warnings）、Ruff/compileall PASS、Node `49 passed`、小程序常规/production 各 `80 files checked`、Alembic 空库升级/head、backend production 配置与 `git diff --check` PASS；本机真实 Chromium 合成页已验证 `arrayBuffer` 与流式 payload 均可建立 MSE 归属。[GitHub Actions run 34300779710](https://github.com/zys1544526484/video-extractor-miniprogram/actions/runs/34300779710) 已成功，包含 Docker build 与 Caddy validate。本修正后的真实抖音结果仍为 `NOT VERIFIED`，只允许再执行一次一键 Headed 验收；若仍失败则保持功能默认关闭并记录阻塞，不再继续堆叠启发式判断。

- M1 P3 单次验收入口（2026-09-08）：新增 `scripts/verify_douyin_session.ps1` 与可单测的 `app.douyin_session.verify`。脚本自动 fetch 并核对 `codex/p3-douyin-session-poc`、远端完整 HEAD 与 `f15943d...` 最低基线；只容忍三个既有 egg-info 修改，检查显式开关、smoke URL 和仓库外有效运营者会话后，强制 `headless=false` 并只调用一次 smoke。最终 JSON从白名单重建，媒体只保留 scheme+hostname，路径、查询、签名、Cookie、Token、会话路径和未知字段均不透传。最新全量回归为 backend pytest `222 passed`（2 warnings）、Ruff/compileall PASS、Node `49 passed`、小程序常规/production 各 `80 files checked`、Alembic 空库升级/head 与 `git diff --check` PASS；代码提交 `ba345f4903fa47afc1d60f1613dc079a54c24ab2` 的 [GitHub Actions #93](https://github.com/zys1544526484/video-extractor-miniprogram/actions/runs/34234612318) 成功。本轮没有执行真实浏览器或读取运营者会话，最新 P3 真实结果仍为 `NOT VERIFIED`，下一步是用户只运行一次该脚本。
- M1 真实预检修正（2026-09-08）：首次运行一键脚本时发现 Git porcelain 首行的前导状态空格被 trim，导致第一个允许保留的 egg-info 文件路径少一个字符并误报工作区异常；smoke 未启动。现保留原始 porcelain 输出并新增回归，允许列表本身未扩大。

- M0 接管基线（2026-09-08）：已核对 `origin/main=af3f2bc452a317675f67c25b0d099b53b8a9d60d`、当前 `codex/p3-douyin-session-poc=f15943d599cdab085566662b6c9116751b504a21`，并确认当前分支与远端一致。新增 `docs/SOL_TAKEOVER_SPEC.md` 作为 M0–M6 当前执行基准，历史 `SOURCE_SPEC_V1.md` 降为需求来源。文档已校准免费模式、24 小时任务/媒体记录、900 秒访问 Token、90000 秒临时文件清理、HTTPS MP4 按需代理和旧广告视觉记录。P3 暖浏览器、可调用的 Xvfb 内部 Worker、Registry 接入及 3/3 真实样例仍未实现或验证；下一步为 M1 一键 Headed 单次验收工具，不继续零散启发式修补。

- P3 Referer 跨域归属收紧（2026-09-08）：视频/HLS MIME 先被过滤，之后 Referer 仅以安全计数归类为 `exact_target_path`、`douyin_origin_only`、`other_douyin_path`、`external_origin`、`missing`；不会输出 Referer 值。完整目标路径继续可用；抖音 origin-only 仅在目标 `/video/{id}`、唯一可见主播放器、隐藏播放器暂停/禁预载、受控捕获窗口、主框架、唯一等价组、SSRF 与无 Cookie Range 复验均满足时才可用。其余三类一律拒绝。seek 只尝试未缓冲位置；已全缓冲时最多 reload 一次并重新确认目标 ID。真实 Headed smoke 未运行，仍为 `NOT VERIFIED`。

- P3 blob 主播放器受控归属（2026-09-08）：目标 ID 与唯一可见主播放器确认后，Worker 暂停隐藏 video、关闭其预加载、清空前置匿名候选，并仅在短时 `main_player_capture` 窗口内激活该主播放器。候选在任务内存中记录捕获阶段、主框架、资源类型、Range/长度、ETag 与规范路径指纹；输出只含八类未绑定原因计数和等价组数。窗口候选需主框架、canonical Referer、视频 MIME、SSRF 校验，且以规范路径指纹形成唯一强等价组；跨 CDN 同路径 Range 镜像可归组，多个不同组继续安全失败。无 Cookie 复验以 `bytes=0-4095` 读取并在内存比较内容哈希，不记录内容或哈希。blob 无候选时仅对同一主播放器 seek 一次，不再 reload。真实 Windows Headed smoke 仍为 `NOT VERIFIED`。

- P3 目标媒体归属收紧（2026-09-08）：在 `goto` 前监听的官方作品详情 JSON 只有请求 `aweme_id`、响应 `aweme_id` 与目标完全一致时才可形成候选；页面 hydration/JSON-LD 同样先定位精确目标作品对象，再只读取 `play_addr_h264`、`play_addr`、按可比较码率从高到低的 `bit_rate.play_addr` 和最后回退的 `download_addr`。多个 CDN `url_list` 被作为同一已绑定作品的镜像，逐个以无 Cookie 的安全请求头复验；`download_addr` 不承诺去除任何画面内标识。没有该绑定证据时，裸网络响应仍必须唯一、主框架且 Referer 为 canonical 目标页，否则安全失败。结构化候选出现后跳过播放器等待与 reload。smoke 安全 JSON 追加绑定/未绑定候选计数、候选组数和来源枚举；已关闭 Context 记录为正常关闭，不再误报 cleanup failed。自动测试已覆盖详情 ID 双向匹配、推荐对象排除、镜像/码率优先级、描述伪造 URL、未绑定多 MP4 拒绝及关闭边界；本机真实 Headed 复测仍为 `NOT VERIFIED`。

- P3 目标媒体归属远程验证：commit `c92873234a8e5b712890c72c76979fc9b68ad046` 的 [GitHub Actions CI #87](https://github.com/zys1544526484/video-extractor-miniprogram/actions/runs/34197350795) 成功。该结果仅证明自动化门禁，不能替代已配置会话上的一次 Headed smoke。

- P3 blob/MediaSource 早期响应捕获（2026-09-08）：response 监听现在在 `page.goto` 前安装，导航和播放器挂载期间的 video/HLS 响应仅作为当前任务内存中的有界候选（最多 4 条、单条最多 4096 字符、最长 15 秒），不写日志、磁盘或异常。确认 canonical 目标页及可见主播放器后，候选还必须是主框架请求、Referer 对应目标作品、video/HLS MIME 并通过 `SafeHttpClient.validate_url`；只有唯一候选才能用于无 Cookie 复验，广告/推荐/子框架和多候选均拒绝。blob 无归属候选时最多受控 reload 一次并重新确认目标 ID。播放器等待为 100ms 有界条件轮询，没有固定 sleep。Page、Context、Browser 依序关闭，清理失败仅记录安全资源类型和 `close_failed` 枚举。真实 Headed 新 smoke 仍待执行，不能将本轮代码或旧结果写为下载成功。

- P3 早期媒体捕获远程验证：commit `064ebfbf57788309200a22a14099a01e759caafa` 的 GitHub Actions CI #85 成功。该 CI 只证明自动化门禁，不能替代现有会话上的 Headed 真实 smoke。

- P3 诊断可见性与异常分类（2026-09-08）：`python -m app.douyin_session.smoke` 的最后一行 JSON 现在直接包含安全的 `last_phase`、阶段毫秒数、规范作品路径、主播放器 video/来源状态、媒体响应 MIME 和仅含 scheme+hostname 的媒体域名；不包含媒体路径/查询串、签名、Cookie、Token、Authorization 或 storage-state 路径。`DOUYIN_SESSION_UNAVAILABLE` 仅用于 Playwright 导入、浏览器启动或浏览器已断连；页面导航/播放器问题分别返回 `DOUYIN_SESSION_PAGE_FAILED`、`DOUYIN_SESSION_PLAYER_NOT_FOUND` 或既有媒体错误。Worker 在清理 Page/Context/Browser 时不会让清理异常覆盖业务错误，连续 headed/headless 运行使用独立对象。真实 Windows 复测尚未执行，因此当前两个模式的实际阶段 JSON 与成功率仍为 `NOT VERIFIED`。

- 本轮本地门禁（2026-09-08）：全量后端 pytest（2 条依赖弃用 warning）、Ruff、compileall、前端 Node `49 passed`、小程序静态与合成 production 校验（各 80 files）及 `git diff --check` 均通过。Docker CLI 本机不可用；push 后的远程 CI 尚待确认。

- P3 生产运行阶段化（2026-09-08）：Worker 现在分别限制 browser launch、`domcontentloaded` 导航、目标身份、播放器挂载/激活、媒体捕获与无 Cookie 媒体验证；超时日志只输出 `last_phase` 与阶段毫秒数。headless/headed 共用 storage state、上下文与播放器行为，不添加 stealth、webdriver 修改、验证码或风控处理。标准 headless 的真实稳定性仍为 `NOT VERIFIED`；可选 Linux Xvfb headed runner 以独立、默认关闭、无端口/VNC、仓库外只读会话卷方式提供，普通 API/Docker/CI 不受影响。浏览器暖复用尚未完成，不得当作性能改善交付。

- P3 主播放器捕获修正（2026-09-07）：确认目标作品页后，Worker 现在依次检查可见且非广告/非推荐主播放器的 `currentSrc`、`src`、`<source src>`；blob/MediaSource 场景仅接受启动该主播放器后出现的**单一** video/HLS 响应，多个候选保持失败以免误选广告或推荐内容。新增 `DOUYIN_SESSION_HEADLESS=true`（默认）供生产运行，人工本机 smoke 可临时设为 `false`；不会点击登录、验证码、风控或广告。失败明确区分主播放器不存在与播放器无可验证媒体。诊断日志仅含规范页面路径、作品 ID、video 可见计数、来源存在性、媒体响应 MIME 与域名。Smoke 在解析后失败时保留 `work_id`。本机当前进程没有继承 storage-state 配置，复跑返回 `DOUYIN_SESSION_CONFIG_INVALID` 并保留作品 ID；实际新捕获链路、媒体地址和无 Cookie 读取仍为 `NOT VERIFIED`。

- P3 短链规范化补充（2026-09-07）：专用 session smoke 的短链入口现在会经 `SafeHttpClient` 逐跳执行 SSRF/DNS/IP、协议/端口和抖音路径白名单校验，记录仅含脱敏路由链；`www.douyin.com/video/{数字ID}` 和 `www.iesdouyin.com/share/video/{数字ID}` 可在校验后剥离正常查询串并规范为严格 canonical URL，首页、推荐、站外、私网、userinfo、异常端口及循环仍拒绝。用户本轮短链已解析到作品 ID `7678969660380843304`，不携带 Cookie 进入解析阶段。完整 session smoke 随后因当前进程未配置仓库外 `DOUYIN_STORAGE_STATE_PATH` 安全返回 `DOUYIN_SESSION_CONFIG_INVALID`（516ms）；没有加载会话、未取得媒体地址或执行无 Cookie 读取。全量门禁：后端 pytest `180 passed`（2 warnings）、Ruff、compileall、前端 Node `49 passed`、小程序静态/合成 production 校验（80 files）及 `git diff --check` 均通过；远程 CI 待本次文档提交触发后确认。P3 仍为 `NOT VERIFIED`。

- P3 抖音运营者服务器专用会话 PoC：`IMPLEMENTED / NOT VERIFIED`。默认 `DOUYIN_SESSION_ENABLED=false`，不接入现有 API 或小程序流程。可选 bootstrap 仅在可视浏览器中等待运营者手动登录，先验证非空 `douyin.com` Cookie，再以临时文件原子替换仓库外 storage state；登录不完整不会创建或覆盖会话。Worker 先确认最终页面严格等于目标 `/video/{数字ID}`，有界等待可见主播放器的 `currentSrc/src`，再以结构化数据辅助；网络媒体仅作 MIME 合格的候选，不能替代主播放器来源。媒体复验只发送 Referer、Origin、User-Agent、Accept，绝不发送 Cookie/Authorization/Token，日志只保留 `https://媒体域名`。当前未手动登录、未取得真实媒体地址，未完成无 Cookie 1024-byte 读取；不能把抖音下载写为成功。

- P2 抖音公开内容解析 PoC：`IMPLEMENTED / PARTIAL LOCAL VERIFIED`。抖音现在使用独立的 `DouyinParser`，仅消费匿名公开跳转和 HTML 中的作品 ID/公开元数据；公开 HTML 未提供具体作品或安全媒体地址时返回可重试 `DOUYIN_RESOLVE_FAILED`，不再因 `cookie`、`unavailable` 或 `Unsupported URL` 宽泛文本误标为私密。用户此前的短链 smoke 已安全解析到作品页但未取得公开媒体地址，约 2.7 秒返回该错误，因此抖音真实下载仍为 `NOT VERIFIED`。

- P1 参考结果页与多媒体源：`IMPLEMENTED / LOCAL VERIFIED`。首页已移除画质预选；结果页提供视频/图片/标题 Tab、真实源列表切换、短期能力链接复制和图片保存；旧单源结果缓存兼容。源2刷新/历史重开会保持，只有服务端确认源已过期才回退并提示；视频封面不会自动进入作品图片列表，纯图片结果使用 `media_type=image`。图片链路现已走独立 SafeHttpClient 探测/下载路径，数据库清理不会误删 TEMP_DIR 中的 SQLite 文件。

- Phase 00 工程基线：`COMPLETE`。
- Phase 01–03 微信端与 Mock 闭环：`COMPLETE / LOCAL VERIFIED`。
- Phase 04–16 后端、权益、安全代理：`COMPLETE / LOCAL VERIFIED`。
- Phase 17–22 平台适配：代码和 contract tests 已完成；Generic 与 Bilibili 各有 1 个真实视频网络样例通过，其余平台 `NOT VERIFIED`；抖音、小红书、快手、微博、Bilibili 的图文解析全部保持 `NOT VERIFIED`。
- Phase 23–26 部署与发布：Docker/Alembic/Caddy 文件已完成；微信开发者工具 Mock 主流程已本机验证，容器、真机和生产部署 `NOT VERIFIED`。
- P0 安全与生产门禁：媒体访问 Token 短期 TTL、Token/媒体保留时间拆分、应用/Caddy 日志脱敏、HTTP(S) 标准端口 SSRF 校验、production Alembic head 校验和 CI 门禁已实现；最新分支 push CI 的两个 job 均成功。自动化门禁已通过，但部署后的日志抽样、真机和生产环境仍为 `NOT VERIFIED`，因此不代表 P0 全部上线条件已完成。

## 本地验证结果

- P3 真实启动修复验证：lazy Playwright loader 返回的 `async_playwright` 工厂现在会被二阶段调用后才进入异步上下文，bootstrap 与 Worker 的无注入路径均有回归覆盖；bootstrap CLI 仅输出 `AppError` 错误码和中文安全提示，不输出 traceback。后端 pytest `171 passed`（2 warnings）；Ruff、`compileall`、`git diff --check` 通过；前端 Node `49 passed`、小程序静态及合成 production 配置校验（各 80 files）通过。当前主机未安装 Docker CLI，Docker build 为 `NOT VERIFIED`；本轮未运行真实 Playwright 浏览器、不持有运营者会话，也未对真实抖音媒体发起 session smoke。

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
- 用户提供的抖音公开短链真实 smoke test 现在由独立 PoC 处理：短链跳转已得到具体公开作品页，但匿名公开 HTML 未给出可安全代理的媒体地址；约 2.7 秒返回 `DOUYIN_RESOLVE_FAILED`（可重试）。没有导入 Cookie，抖音下载能力仍为 `NOT VERIFIED`。
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

## P1 轮询生命周期修正（2026-09-06）

- 结果页在轮询中经历 `onHide` 后立即 `onShow` 时，会标记恢复请求并等待旧轮询退出；旧轮询的进度、成功和失败结果均按 generation 与 job_id 丢弃，退出后仅启动一个当前页面的全新轮询，避免页面永久停在 loading 或旧结果覆盖新结果。
- 页面级 Node 回归覆盖“轮询等待 → hide → show → 旧结果返回 → 新轮询成功”，确认旧结果不会写入页面，且最终只由恢复轮询显示成功结果。
- 本轮本地验证：后端 pytest `116 passed`（2 warnings）；前端 Node `47 passed`；Ruff、compileall、小程序校验（80 files）、合成生产配置校验和 `git diff --check` 全部 PASS。微信开发者工具和真机生命周期操作仍为 `NOT VERIFIED`。

## P2 抖音公开内容解析 PoC（2026-09-07）

- 新增专用 `DouyinParser`，Registry 仅将抖音路由到该解析器；Bilibili、微博、小红书、快手和 Generic 适配器保持原有类型与路径。
- 仅使用 `SafeHttpClient` 执行初始 URL、每一跳重定向、公开页面及解析出的媒体/封面地址校验；不提交 Cookie、不调用签名隐藏接口、不模拟登录或绕过平台限制。短链丢失作品 ID、跳首页或 yt-dlp `Unsupported URL` 返回 `DOUYIN_RESOLVE_FAILED`（可重试）；只有公开页面或 yt-dlp 明确证明私密、删除、仅好友或必须登录时才返回 `CONTENT_RESTRICTED`。
- 公开 HTML 能提供作品 ID、标题、封面和公开媒体地址时，解析器只返回内部 `ParserResultModel` 来源，仍由既有媒体探测、短期 token、用户归属和代理链路处理；解析阶段不会预下载视频。
- 实际 smoke：使用临时 `DOUYIN_SMOKE_URL`（不写入测试夹具）测试用户此前提供的公开短链。最终安全页面路径为 `/video/7678631238139268402`，耗时 `2717ms`，未在匿名页面发现可用公开媒体地址，结果 `DOUYIN_RESOLVE_FAILED`。真实预览、下载、真机保存均继续为 `NOT VERIFIED`。

### P2 审查修正（2026-09-07）

- 已移除 URL 正则与“字段名附近 URL”启发式。现在只解析 script 内可解码的 JSON、JSON-LD 或 hydration JSON，并仅沿 `video.play_addr.url_list`、`video.play_addr_h264.url_list`、`video.download_addr.url_list`、`video.bit_rate[*].play_addr.url_list` 等明确路径取媒体地址；标题、描述、评论或其他任意文本中的 URL 不会成为媒体来源。
- 正常 URL、JSON escaped slash、Unicode escaped slash 和 HTML entity 地址均在结构化 JSON 解码后再执行 `SafeHttpClient.validate_url`；恶意重定向、媒体地址 SSRF、超时和日志查询脱敏继续由回归覆盖。
- `/note/{id}` 现在明确返回“抖音图文作品暂不支持视频提取”，既不改写为 `/video/{id}`，也不会请求视频元数据或回退 yt-dlp。
- 复测用户此前短链：匿名页面安全到达 `/video/7678631238139268402`，发现 2 个 script、21 个可解码 JSON/hydration 值，但没有白名单视频字段；因此无法取得公开视频媒体地址，`3234ms` 后返回 `DOUYIN_RESOLVE_FAILED`。抖音真实预览、下载与保存仍为 `NOT VERIFIED`。
