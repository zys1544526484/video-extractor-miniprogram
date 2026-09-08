# 协作交接记录

本文件是 ChatGPT（决策与审查入口）、Codex（实现与验证）和 GitHub（分支、commit、Draft PR 中转）之间的长期交接记录。每个可独立验证的步骤完成测试后更新本文件。

## 当前基线

### 当前请求：P3 运营者服务器专用抖音会话 PoC（2026-09-07）

- 分支：`codex/p3-douyin-session-poc`，从已核对的 P2 HEAD `9275b0a11658dc2ccf788acfbb7a8a6b44b585ac` 创建；不修改 `main`、不使用 force push、不创建或合并 PR。
- 用户已明确授权**运营者手动登录的服务器专用会话**，但未授权用户 Cookie、自动登录、验证码/滑块/设备验证/风控处理、私密或受限内容访问。该路线默认关闭且不接入当前生产解析流程。
- 详细边界见 `docs/ADR/0001-douyin-server-session-poc.md`。会话文件必须存放在仓库外，且 `.gitignore` 增加了 storage-state 防护；任何测试和交付不得写入真实会话、账号或媒体签名地址。
- 已推送独立提交：`930df41`（范围授权与 ADR）、`f2a435c`（P2 目标身份收紧）、`c7c35cd`（可选 bootstrap 与配置）、`dddf9b1`（隔离 Worker PoC）、`6863277`（安全边界测试）。Playwright 为额外可选依赖，正常 API、CI 与 Docker 默认不会安装浏览器；所有 import 均延迟到明确 CLI/Worker 调用。
- Worker 只接受无查询串的 `https://www.douyin.com/video/{数字ID}`；先确认页面目标 ID，随后才用无 Cookie `SafeHttpClient` 探测/Range 读取候选视频。结果模型和日志不包含 Cookie、storage state、完整签名媒体 URL 或查询串。登录失效、风险页、目标不一致、session-bound 媒体和超时使用稳定错误停止。
- 本轮自动验证：后端 pytest `154 passed`（2 warnings）、Ruff、compileall、`git diff --check` PASS；前端 `npm test` `49 passed`，小程序静态与合成 production 配置校验（80 files）PASS。Docker CLI 在本机不可用。当前没有运行手动登录或真实会话 smoke，真实媒体地址、无 Cookie 1024-byte 读取、实际耗时和真机流程均为 `NOT VERIFIED`；不要将 PoC 代码描述为抖音下载成功。
- 审查修正已推送：`4869df2`（严格目标页后的主播放器等待、可见风控判断、原子 bootstrap 与安全请求头）、`9a64995`（环境变量驱动且输出脱敏的 smoke CLI）、`6a39fb2`（路径/查询签名日志脱敏回归）。Playwright 适配器级 fake-browser 测试覆盖 CDN URL 无作品 ID、延迟 `currentSrc`、广告/推荐网络候选不替代主播放器、页面目标不一致、隐藏 captcha 文本和可见风控组件。
- 当前复跑：后端 pytest `168 passed`（2 warnings）；Ruff、compileall、`git diff --check` PASS；前端 `npm test` `49 passed`；小程序静态及合成 production 校验均为 80 files PASS。Docker CLI 仍不可用；不执行真实登录或 smoke，等待远程 CI 与后续人工会话验证。
- 真实启动阻塞修复：`077c2df` 将 lazy loader 的两阶段调用收敛为“loader → `async_playwright` factory → async context manager”，既保留注入式 factory，也修复未注入真实路径的 `TypeError`。bootstrap 和 `PlaywrightSessionAdapter` 均有无注入回归；bootstrap 临时 state 失败清理与旧会话保留测试继续通过。CLI 捕获 `AppError` 后只输出稳定错误码和中文提示、退出码 1，不向普通用户显示 traceback 或会话数据。
- 本轮全量验证：后端 pytest `171 passed`（2 warnings）；Ruff、compileall、`git diff --check` PASS；前端 `npm test` `49 passed`；小程序静态及合成 production 校验均为 80 files PASS。`backend/wechat_video_extractor_backend.egg-info/` 的三个未提交变更在任务开始前已存在且不属于本次工作，未被暂存或提交。
- 短链重定向修正已推送：`10cc625` 为 smoke 短链增加每跳 `SafeHttpClient` SSRF/DNS/IP 校验和抖音路由白名单；只接受 `v.douyin.com` 短链及 `douyin.com` `/video/{数字ID}`、`www.iesdouyin.com` `/share/video/{数字ID}`，在路径/ID 校验后删除正常查询参数并交给严格的 query-free Worker。重定向日志仅记录脱敏路由，不记录查询、Cookie、Token 或签名。主页、站外、私网、userinfo、异常端口和循环都有回归覆盖。
- 真实短链本轮已安全规范到作品 ID `7678969660380843304`。完整 smoke 以临时 `DOUYIN_SESSION_ENABLED=true` 运行时，因本机没有配置仓库外 state 路径而返回 `DOUYIN_SESSION_CONFIG_INVALID`（516ms）；没有读取、打印或保存会话，且没有取得媒体地址。`c11e120` 把该配置错误收敛为稳定安全错误，防止 smoke CLI 输出 traceback。媒体地址、无 Cookie 1024-byte 读取、耗时与真机流程继续为 `NOT VERIFIED`。
- 本轮全量验证：后端 pytest `180 passed`（2 warnings）；Ruff、compileall、前端 `npm test` `49 passed`、`npm run validate:miniprogram` 与合成 `npm run validate:production`（各 80 files）以及 `git diff --check` 均通过。先前存在的三个 egg-info 未提交文件保持未暂存、未提交；本次文档 commit push 后再确认远程 CI。
- 主播放器捕获修正已推送：`f94e021`。身份严格匹配后，adapter 读取可见、非广告/非推荐主播放器的 `currentSrc`、`src` 和 `source[src]`；blob 仅在启动该播放器之后有唯一 video/HLS 响应时作为候选，多候选明确拒绝。新增安全 `PlayerDiagnostics`，仅记录规范页面路径、作品 ID、video 计数/布尔来源状态、响应 MIME 与域名；不保存 URL、Cookie、签名、Token 或 storage state。`DOUYIN_SESSION_HEADLESS` 默认 `true`，人工本机 smoke 可临时设为 `false`。错误新增 `DOUYIN_SESSION_PLAYER_NOT_FOUND`，与 `DOUYIN_SESSION_MEDIA_NOT_FOUND` 分离；smoke 后续失败仍保留已解析 `work_id`。
- 本机复跑的进程未继承外部 state 路径，故以 `DOUYIN_SESSION_CONFIG_INVALID` 结束，但安全输出已保留目标 ID `7678969660380843304`（921ms）。这不验证新播放器捕获是否能取得媒体；用户应在已配置运营者会话的本机终端执行可视 smoke。三个任务前已有 egg-info 修改继续未暂存、未提交。
- 补充 adapter 级“没有可见主播放器”回归已推送：`b263904` 增加该测试，`de2b7ff` 修正测试替身的播放器挂载等待模拟。最新本地全量门禁复跑均通过；该两笔提交未改动业务安全边界，远程 CI 需以最新 HEAD 为准。
- P3 阶段化生产诊断：`5d0184a` 将 launcher、导航（固定 `domcontentloaded`）、身份、播放器、媒体捕获与无 Cookie 媒体验证拆成独立上限，失败日志只保留阶段毫秒数和既有脱敏字段。可选 Xvfb headed 容器位于 `backend/Dockerfile.douyin-session` 与 `deploy/docker-compose.douyin-session.yml`，默认 profile 关闭、不暴露端口/VNC、只读挂载仓库外会话文件；普通 API 镜像和 CI 不变。全量本地 pytest、Ruff、compileall、Node 49 项、小程序与生产配置校验均通过。浏览器暖复用仍未实现，必须继续列为性能/部署阻塞。
- P3 诊断可见性与稳定性收尾（2026-09-08）：smoke 最后一行 JSON 直接输出安全 `last_phase`、`phase_elapsed_ms`、`phases_ms`、规范 `final_page_path`、video/source 计数与布尔状态、媒体响应 MIME/仅 scheme+hostname 域名；不输出任何媒体路径、查询、签名、Cookie、Token、Authorization 或 storage-state 信息。浏览器导入/启动/断连才使用 `DOUYIN_SESSION_UNAVAILABLE`；导航/页面错误使用 `DOUYIN_SESSION_PAGE_FAILED`，播放器和媒体错误保持具体分类。Worker 记录枚举式 internal reason 但不输出原始异常，安全关闭 Context/Browser，关闭失败不覆盖原业务错误。新增 smoke JSON 脱敏、具体错误分类和 headed→headless 资源独立回归。本地真实 headed/headless smoke 尚未复跑，故仍为 `NOT VERIFIED`；本轮完成全量门禁并 push 后在此记录 CI URL。
- 本轮本地门禁：全量 backend pytest（2 条依赖弃用 warning）、`ruff check app tests alembic`、`compileall app alembic`、`npm test`（49 passed）、小程序常规/合成 production 校验（各 80 files）与 `git diff --check` 均通过。Docker CLI 仍不可用，Docker build 本地为 `NOT VERIFIED`；远程 CI 必须以本次 push 的 run 为准。
- P3 blob 早期媒体捕获修正（2026-09-08）：response listener 在 `goto` 前安装；video/HLS 候选只保留于当前任务内存（最多 4 条、4096 字符、15 秒），任务结束清空，不进入日志、文件、异常或结果模型。目标 ID 和可见主播放器确认后，只有主框架、目标 Referer、MIME 合格且通过 `SafeHttpClient.validate_url` 的唯一候选才可用于无 Cookie 复验；多候选、广告/推荐/子框架均失败而非猜选。blob 无候选时只 reload 一次并再次确认目标 ID。Player 等待为有界条件等待；关闭顺序为 Page → Context → Browser，关闭异常仅记录 `resource` 和 `close_failed`。新增 navigation/mount 早期候选、唯一性、候选清空、一次 reload、关闭顺序与现有脱敏回归。真实 Headed 复测仍为 `NOT VERIFIED`，不需要重新 bootstrap。
- `064ebfbf57788309200a22a14099a01e759caafa` 已推送；[GitHub Actions CI #85](https://github.com/zys1544526484/video-extractor-miniprogram/actions/runs/34194264980) 成功。它覆盖自动化门禁，不代表真实 Headed blob 媒体已重新捕获；下一步仅需使用既有运营者会话执行一次 Headed smoke。
- P3 目标媒体归属收紧：详情 JSON 监听仍在 `goto` 前安装，但只接受官方 `douyin.com`/`iesdouyin.com` 明确 detail path，且请求与响应的 `aweme_id` 都严格等于目标；页面 hydration/JSON-LD 也只从匹配目标对象的 H.264、play、按码率排序的 bit-rate 和最后 download 字段读取。CDN 镜像是同一已绑定组，按顺序无 Cookie 复验；没有绑定组时，多条裸 MP4 继续拒绝猜选。结构化候选会跳过 player wait/reload；smoke JSON 增加安全的 bound/unbound/group/source 枚举字段，Context 已关闭不再被记成 cleanup failed。真实 Windows Headed smoke 仍未复跑，保持 `NOT VERIFIED`，不需要重新 bootstrap。
- `c92873234a8e5b712890c72c76979fc9b68ad046` 已推送；[GitHub Actions CI #87](https://github.com/zys1544526484/video-extractor-miniprogram/actions/runs/34197350795) 成功。它证明后端、前端及生产静态门禁在干净 runner 通过，不证明真实浏览器会话已取得媒体。
- P3 blob 主播放器受控归属：无结构化目标媒体时，身份和唯一可见主播放器确认后才暂停隐藏 video、清空匿名候选，并打开短时主播放器捕获窗口；只有该窗口的主框架、canonical Referer、视频 MIME、SSRF 合格候选才能用规范路径指纹组成唯一等价组。跨 CDN 同路径 Range 镜像可按组无 Cookie 复验；小范围内容哈希仅驻留内存且不进入日志/JSON。一个已验证主播放器最多 seek 一次，多个无法证明等价的组继续失败。smoke 新增安全原因计数和等价组数；真实 Headed 验证仍为 `NOT VERIFIED`，无需重新 bootstrap。
- P3 Referer 跨域修正：MIME 过滤先于 Referer 分类；安全 smoke JSON 只输出 `exact_target_path`、`douyin_origin_only`、`other_douyin_path`、`external_origin`、`missing` 五类数量，不含原始 Referer。exact 保持可用；origin-only 必须同时处于严格目标页、唯一可见主播放器/隐藏播放器暂停、受控 capture/seek/reload 窗口、主框架、唯一强等价组、SSRF 与无 Cookie Range 复验中。其他三类拒绝。seek 会选取未缓冲位置；没有未缓冲位置时最多 reload 一次并重验目标 ID。真实 Headed smoke 仍未执行。

### 当前请求：P2 抖音公开内容解析 PoC（2026-09-07）

- 任务分支：`codex/p2-douyin-parser-poc`；开始基线已核对为 `af3f2bc452a317675f67c25b0d099b53b8a9d60d`，工作区干净。本轮未切换或修改 `main`，不使用 force push，不合并。
- 已推送独立提交：`24c1152`（抖音错误分类）、`15d4bf5`（独立公开 Parser PoC）、`0185189`（安全/日志回归）和 `6717acc`（任务及小程序错误显示回归）。
- `DouyinParser` 只处理匿名公开重定向及 HTML/嵌入数据；初始和重定向 URL、从页面读取的媒体及封面地址都由 `SafeHttpClient` 和既有 SSRF 规则校验。未添加 Cookie、X-Bogus/A-Bogus、账号会话、隐藏接口或规避逻辑。公开 HTML 直接提供作品元数据和媒体地址时，仍只向下游媒体会话交付内部来源，不向小程序暴露上游地址。
- 分类规则：不再根据 `cookie`、`unavailable` 或 `Unsupported URL` 的宽泛字样判断私密；抖音短链跳首页、作品 ID 丢失或短时回退 Unsupported URL 返回 `DOUYIN_RESOLVE_FAILED`、中文“抖音短链接未能解析到具体作品，请稍后重试”、`retryable=true`。明确私密、删除、仅好友或登录要求才返回 `CONTENT_RESTRICTED`。结果页和 24 小时历史都会保存并展示该错误码和中文原因。
- 实际 smoke 使用临时 `DOUYIN_SMOKE_URL`（未写入测试）。用户此前的短链最终安全页面路径为 `/video/7678631238139268402`，耗时 2717ms，匿名公开页面未提供可安全代理的媒体地址，因此结果为 `DOUYIN_RESOLVE_FAILED`。抖音真实预览/下载/保存仍为 `NOT VERIFIED`。
- 自动测试覆盖短链、正常作品链接、跳首页、明确私密、恶意跳转、公开媒体地址 SSRF、超时、Registry 隔离、日志查询脱敏、任务/历史和结果页错误展示。后续须复跑全量门禁并检查远程 CI；不可将本次 smoke 失败写成平台通过。

### P2 审查修正：结构化抖音媒体字段（2026-09-07）

- 分支保持 `codex/p2-douyin-parser-poc`；未创建分支、PR，未切换或修改 `main`，不使用 force push。
- 删除不安全的 URL 正则/邻近字段启发式。解析器只读取 script 中可解码的 JSON、JSON-LD 或 hydration JSON，并仅从 `video.play_addr.url_list`、`video.play_addr_h264.url_list`、`video.download_addr.url_list`、`video.bit_rate[*].play_addr.url_list` 提取媒体地址。任意标题、描述、评论及其他文本中的 URL 都不会被当作媒体来源。
- 解码后的地址仍须通过 `SafeHttpClient.validate_url`。新增 JSON escaped slash、Unicode escaped slash、HTML entity、描述伪造地址、正确字段、`/note/`、SSRF 等回归；既有超时和日志脱敏测试保持。
- `/note/{id}` 返回 `PLATFORM_UNSUPPORTED` 和“抖音图文作品暂不支持视频提取”，不再改写为视频 URL，也不调用 yt-dlp。
- 真实短链复测：安全到达 `/video/7678631238139268402`；匿名页面有 2 个 script、21 个可解码 JSON/hydration 值，未提供任何白名单公开视频字段。没有取得媒体地址；耗时 3234ms，`DOUYIN_RESOLVE_FAILED`（可重试）。真实抖音媒体解析、预览、下载和相册保存仍为 `NOT VERIFIED`。

### 当前审计/实施交接（2026-09-05）

- 最新 `main`：`b006c3f7bcf00d369d22c7e99ab2f738764ea84f`
- PR #2：已合并到 `main`（本分支从该 SHA 创建）
- 当前任务分支：`codex/p1-reference-result-sources`
- 当前任务：按参考录屏重构结果页与数据契约；不是继续改动鉴权、SSRF、后台任务或广告规则。
- 已完成：首页移除画质预选；结果页视频/图片/标题 Tab；多源安全 token、源切换同步、图片保存、标题/分享文案复制；后端旧单源缓存兼容。
- 验证：前端 `npm test` 36 passed、`npm run validate:miniprogram` PASS；后端 pytest 100 passed、ruff PASS、compileall PASS；`git diff --check` PASS。
- 未验证：微信开发者工具本轮未自动化截图；真实域名、真实五平台样例、真机相册保存仍为 `NOT VERIFIED`。
- Draft PR：连接器调用 GitHub API 返回 `403 Resource not accessible by integration`，未创建成功；请使用有 Pull Request 写权限的 GitHub 账号打开 compare/new-PR 链接创建 Draft PR，不要直接合并。
- 收尾修正：源编号改为按返回列表位置生成，兼容非 `source-N` 的后端源 ID；`npm test` 36 passed，`npm run validate:miniprogram` PASS，已随 commit `45f7c785840f498eed27f1f207d5e422cfad70fb` 推送。

### 当前请求：参考结果页修正（2026-09-05）

- 当前分支保持为 `codex/p1-reference-result-sources`，不新建分支、不创建 PR。
- 本轮已推送 commits：`a4fd0b4`（媒体能力链接与图片结果）、`9f6c78f`（显式画廊图片测试）、`f3a8fd8`（源2保持、结果页布局与文档）。
- 下载链接现在是服务端签发的短期媒体能力地址；`/media/{token}/download` 可在没有小程序 `Authorization` 请求头的情况下独立打开，仍受媒体会话 token、过期时间和 `rewarded_ad` 权益检查保护。
- 结果页刷新或从历史记录重开时保留本地选择的源2；只有服务端不再返回该源（已真实过期/失效）才切换到可用源并提示。视频清晰度、大小和源按钮已收敛到同一行，源列表从底部弹出。
- 图片数据只来自解析器明确提供的公开图片；视频封面不再自动变成图片项。Generic 支持直接图片和显式画廊图片；纯图片作品使用 `media_type=image`，没有安全图片时显示空状态。
- 本轮新增/更新后端和前端回归测试；本地后端 pytest 105 项、Ruff、compileall，前端 `npm test` 39 项、`npm run validate:miniprogram` 与 `git diff --check` 均通过。
- 微信开发者工具验证：当前 CUA 状态没有微信开发者工具原生应用，工作区也未发现官方 DevTools CLI；因此本轮不能自动打开、操作或截图开发者工具，只能记录为 `NOT VERIFIED`，不得把静态校验当作截图/真机证据。
- 未验证：真实五平台图片/视频样例、真实 HTTPS 合法域名、真实登录、真机预览/下载/相册权限和生产部署。

### 当前请求：图片链路、源持久化与复制链接修正（2026-09-05）

- 分支保持为 `codex/p1-reference-result-sources`，未新建分支、未创建或合并 PR。
- `13343a2` 已推送：`SafeHttpClient` 增加独立 `probe_image` 与 `media_kind=image` 流式校验；Generic 直接图片和网页 `<img>` 均经真实 SafeHttpClient、SSRF、大小/MIME 检查后落盘，并通过预览/下载接口回归测试。视频链路仍只接受视频 MIME。
- `PATCH /api/v1/parse/jobs/{job_id}/source` 将 `selected_source_id` 写入任务 `result_json`；前端同时按 job_id 保存本地选择，覆盖 A 选源2→打开 B→重开 A、任务轮询续签及历史重开。源失效时才回退并提示。
- `copyCurrentLink` 复制前会按当前 job 和选中源刷新短期 Token；刷新或复制失败不会提示成功，复制内容仅为可独立打开的安全下载地址，不包含上游直链或长期 Token。
- 结果页底部空状态改为 `!result`；纯图片作品的视频 Tab 显示“该作品没有视频”，图片 Tab 只展示解析器返回的真实图片，不使用视频封面冒充。
- 媒体清理额外收紧为仅删除受支持媒体扩展名，避免 TEMP_DIR 与 SQLite 共用时误删数据库；回归测试确认数据库文件保留。
- 本轮复跑结果：后端 pytest `110 passed`、Ruff PASS、compileall PASS；前端 `npm test` `43 passed`；`npm run validate:miniprogram` `79 files checked PASS`；合成生产校验 PASS；`git diff --check` PASS。
- 微信开发者工具原生应用和官方 CLI 当前不可用，无法完成本轮首页/Tab/源切换/图片保存/标题复制/免费保存的截图或真机操作，记录为 `NOT VERIFIED`；静态校验不替代开发者工具与真机证据。
- 独立清理修复随后以 `fdb55f4` 提交并推送；文档更新将在该提交之后另行提交。远程 CI 由分支 push 触发，当前未通过 GitHub 连接器读取 run 详情，不能写成 CI 已通过。

### Issue #3：P1 结果页单图语义与视觉验收（2026-09-05）

- Issue #3 要求已执行：Generic 解析器现在区分“仅 og:image 封面”和“显式 img/JSON-LD 图片”。纯图片页即使显式图片与 `og:image` 相同也会返回真实图片；视频页重复封面不会进入作品图片列表。
- `DIRECT_IMAGE_EXTENSIONS` 已移除 `.gif`，与 SafeHttpClient 和媒体会话当前只接受 JPEG、PNG、WebP 的安全格式保持一致；新增 GIF 不进入图片链路的回归测试。
- 新增真实 SafeHttpClient + 模拟网络响应的端到端单图页面测试，覆盖 HTML 解析、图片探测、落盘、短期预览和下载；解析器单测覆盖显式封面、JSON-LD 图片、视频重复封面与 GIF 边界。
- 平台状态明确保持：抖音、小红书、快手、微博、Bilibili 的图文解析均为 `NOT VERIFIED`。已有 Bilibili 视频样例只证明公开视频链路，不代表图文解析通过。
- 本次实现提交为 `cfbeb76`，已推送到原分支；尚未合并，按 Issue 要求后续仅创建 Draft PR，不标记 ready。
- 交付门禁：后端 pytest `113 passed`（2 warnings）、Ruff PASS、compileall PASS；前端 Node `43 passed`；小程序校验 `79 files checked PASS`；合成生产校验 PASS；`git diff --check` PASS。

### 当前请求：P1 任务跳转、轮询与快速媒体路径收尾（2026-09-05）

- 当前分支保持为 `codex/p1-reference-result-sources`，不新建分支、不合并 PR。当前基线仍为 main `b006c3f7bcf00d369d22c7e99ab2f738764ea84f`；PR #2 已合并；PR #5 保持 Draft、目标为 `main`。
- 首页在 `POST /parse` 成功创建任务后立即跳转 `pages/result/result?job_id=...`。结果页自动轮询任务状态，显示进度/阶段；ready 后加载视频、图片、标题、真实来源和画质；failed 后显示后端错误码、中文原因和“重新提取”。历史记录使用同一错误明细，不再只显示“提取失败”。
- `result.wxml` 的下载/解析进度条已改用微信原生 `progress`，不再使用动态宽度 style，消除开发者工具 CSS 检查错误来源。
- 新增远程媒体会话字段和迁移 `backend/alembic/versions/0004_remote_media_sessions.py`。对于已通过 SafeHttpClient 元数据探测、SSRF 检查、MIME/大小限制的 HTTPS MP4，解析阶段不读取完整媒体体；仅在预览/保存请求时使用短期媒体 Token 代理传输。非 HTTPS、非 MP4、降档或探测不完整的源继续走现有分块下载/ffprobe/处理回退路径。旧本地文件会话保持兼容，媒体清理规则未放宽。
- 本轮测试：后端 pytest `116 passed`（2 warnings）；Ruff PASS；compileall PASS；前端 Node `46 passed`；`npm run validate:miniprogram` `80 files checked` PASS；合成 `npm run validate:production` PASS；`git diff --check` PASS。
- 人工验证仍未完成：当前环境没有可操作的微信开发者工具原生应用或官方 CLI，无法提供本轮截图；真实微信登录、合法 HTTPS 域名、五个平台公开样例、真机网络/相册保存和生产部署均继续标记 `NOT VERIFIED`。本轮未接入 SPAPI 或 media-parser。
- PR #5 已确认仍为 Draft、目标为 `main`，当前 head 为 `84ec701d80a622e29d523f3390ba4aa4e7434d89`。完成 push 后尝试通过 GitHub 连接器更新描述，但 GitHub API 返回 `403 Resource not accessible by integration`；网页入口也处于未登录状态，因此描述尚未更新。保持 Draft，不合并，需具备 PR 写权限的 GitHub 账号手动更新。

### 当前请求：P1 结果页 hide/show 轮询恢复（2026-09-06）

- 分支保持为 `codex/p1-reference-result-sources`，PR #5 保持 Draft，不创建新分支、不合并。
- 修复竞态：当结果页轮询中触发 `onHide` 后立即 `onShow`，`onShow` 不再因旧轮询仍在执行而丢弃恢复请求。页面记录恢复意图，旧 generation 退出后才启动一个新轮询循环。
- 所有轮询回调、成功和失败处理均检查当前 `job_id`、页面可见性和 generation；旧轮询无法覆盖新轮询的结果。任意时刻只允许一个有效轮询循环。
- 新增页面级 Node 回归：轮询等待期间依次 `onHide`、`onShow`，旧轮询随后返回旧结果；断言旧结果被忽略，第二次轮询启动并最终显示恢复后的结果。
- 本轮验证：后端 pytest `116 passed`（2 warnings）；前端 Node `47 passed`；Ruff、compileall、`npm run validate:miniprogram`（80 files）、合成 `npm run validate:production` 和 `git diff --check` 均 PASS。
- Browser 插件不可用，且当前环境没有可操作的微信开发者工具；因此本轮以页面级自动化测试验证生命周期，微信开发者工具/真机 hide/show 操作仍为 `NOT VERIFIED`。

- 仓库：`https://github.com/zys1544526484/video-extractor-miniprogram`
- 目标基线：`main`
- 任务分支：`codex/p1-reference-result-sources`
- `main` 已推送的基线 commit：`b006c3f7bcf00d369d22c7e99ab2f738764ea84f`
- 小程序安全检查点：`42334a8bc2a9478bd6926789157494cec23f6d66`
- Draft PR：当前分支尚未创建（历史 PR #1 属于已合并的 bootstrap 分支）
- 当前 P0 修复状态：`AUTOMATED_GATES_PASS_EXTERNAL_NOT_VERIFIED`；Token 时间语义、生产配置校验和 Caddy CI 门禁已完成自动化检查，真实部署与真机仍待验证。

## 长期工作规则

1. ChatGPT 负责拆分任务、审查范围、确认风险和决定是否允许合并。
2. Codex 在一个独立的 `codex/` 分支上实现；不得直接在 `main` 开发。
3. 每个可独立验证的小步骤都要先运行相关测试，再单独 commit 并立即 push。
4. 不使用 force push；push 失败立即停止并报告真实错误。
5. 不提交 `.env`、Token、密钥、密码、账号信息、完整 Authorization、Cookie、缓存或临时文件。
6. 未经用户明确允许，不合并到 `main`，不替用户作最终合并决策。
7. 每次交接报告都要包含仓库、分支、commit SHA、PR 地址、测试结果和下一步建议。

## 本次初始化记录

### 步骤一：现有小程序修改安全检查点

- 范围：19 个小程序页面、服务、存储、工具和测试文件。
- 处理：保留工作区已有修改，未覆盖、删除或还原；未将其他目录内容带入 commit。
- 敏感检查：变更路径未发现 `.env`、缓存或临时文件；未提交凭据、Token、密钥或账号信息。
- 验证：`npm test` 通过（30/30）；`npm run validate:miniprogram` 通过（74 个文件）。
- commit：`42334a8bc2a9478bd6926789157494cec23f6d66`
- push：已成功推送到 `origin/codex/bootstrap-github-handoff`。

### 步骤二：协作机制文件

- 本步骤创建或更新根目录 `AGENTS.md`、本文件和 `.github/pull_request_template.md`。
- 验证：`npm test` 通过（30/30）；`npm run validate:miniprogram` 通过（74 个文件）；`git diff --check` 通过。
- commit：`aad61e489a68d48a65f24ce079591d8abf523e07`
- push：已成功推送到 `origin/codex/bootstrap-github-handoff`。

### 步骤三：收尾状态与 CI

- `STATUS.md` 已更新为当前真实 Node、小程序验证和后端检查数量，并记录提取记录、最多两个后台任务及 24 小时结果再次打开的实现状态。
- `BLOCKERS.md` 已保留备案域名、真实微信凭证、服务器、平台样例和真机验证等上线阻塞项；本次协作收尾未消除这些 Gate。
- `.github/workflows/ci.yml` 已配置为在 `codex/**` push 和针对 `main` 的 pull request 上运行前端 Node 测试、小程序校验、后端 pytest 与 ruff。
- 本次本地验证：`npm test` 30/30；`npm run validate:miniprogram` 74 个文件；后端 pytest 87/87；ruff 通过；`git diff --check` 通过。
- GitHub Actions 远程 runner 结果需以 PR checks 为准，本地未将其写成 PASS。

### 步骤四：GitHub CI 最小修复

- 第一次远程 CI（PR #1 的 run #1）失败在 `actions/setup-node` 的 npm lockfile 检查阶段：仓库没有 `package-lock.json`，而旧配置启用了 `cache: npm`；后续 `npm ci` 也不适用于当前无依赖的根 `package.json`。
- 因此第一次远程 Node 测试没有执行；后端 CI 已通过。
- 本次只做最小修复：升级 `actions/checkout` 与 `actions/setup-node` 到 v5，保留 Node 20，删除 npm cache 和 `npm ci`，直接运行 `npm test` 与 `npm run validate:miniprogram`。
- 未生成依赖、未修改业务代码、未写入任何密钥或生产凭证。
- 最新 PR CI 检查已完成并成功：Node 30 passed、0 failed；小程序验证 72 files checked、PASS；后端 84 passed、3 skipped（共收集 87 项）；Ruff 为 All checks passed；前后端两个 job 均成功。
- 本地与 GitHub 文件计数差异：本地 validator 递归包含 `miniprogram/project.config.json` 和 `miniprogram/project.private.config.json`；两者均由 `.gitignore` 忽略，属于本地配置，不应提交。GitHub 干净 checkout 不包含它们，因此本地为 74 文件、远程为 72 文件。

### 步骤五：P0 媒体访问与 SSRF 加固（第一独立检查点）

- 当前分支：`codex/p0-security-production-gates`，基于最新 `origin/main`。
- 应用请求日志将 `/api/v1/media/{token}/preview|download` 中的 token 替换为 `<token>`；Caddy access log 删除 URI 和请求头，避免媒体 token 进入应用或 Caddy 日志。
- 新增 `MEDIA_ACCESS_TOKEN_TTL_SECONDS`，默认 900 秒；媒体会话仍保留 24 小时，过期 token 可在用户授权的任务结果中重新签发。
- SSRF URL 只接受 HTTP 80 和 HTTPS 443（含显式端口），并补充标准端口、协议错配和非标准端口测试。
- 本步骤本地验证：后端 pytest `97 passed`、ruff `All checks passed`、`git diff --check` 通过。
- 生产启动路径已在本步骤切换为 Alembic head 校验，不再在 production 调用 `create_all`；下一步补充 GitHub Actions 的生产配置、编译、空库迁移和 Docker 构建门禁。

### 步骤六：生产门禁与 CI 加固（第二独立检查点）

- `.github/workflows/ci.yml` 继续只在 `codex/**` push 和针对 `main` 的 pull request 运行，并新增 production 配置校验、`compileall app alembic`、空 SQLite 数据库 `alembic upgrade head`、Alembic head 再校验及 backend Docker build。
- production 配置校验使用非敏感的合成值，只确认正式 `free` 模式、Mock 关闭、24 小时媒体保留和 900 秒访问 Token TTL，不写入任何密钥或生产凭证。
- 本地对应检查：production 配置校验通过；`compileall app alembic` 通过；Alembic 空 SQLite 升级及 head 校验通过。
- 本机未安装 Docker CLI，因此 Docker build 未在本地运行；最新分支 push CI 已在干净 runner 成功完成该检查。

### 步骤七：P0 状态文档校准（第三独立检查点）

- `STATUS.md`、`RELEASE_READINESS.md` 和 `BLOCKERS.md` 已同步记录本次安全门禁、当前真实本地测试数量和未验证项，未删除任何备案域名、真实微信凭证、服务器、平台样例或真机阻塞项。
- 本地最终验证：`npm test` 30 passed；`npm run validate:miniprogram` 74 files checked、PASS；后端 pytest 98 passed（2 个依赖警告）；ruff All checks passed；`git diff --check` 通过。
- 最新分支 push CI 的 Node job 为 30 passed、72 files checked；Backend job 为 95 passed、3 skipped（共收集 98 项，3 skipped 因 runner 无 ffmpeg/ffprobe），ruff、production 配置校验、compileall、Alembic 空库升级/head 校验和 Docker build 均成功。
- Docker CLI 在本机不可用，Docker build 的本地状态仍为未验证；远程 CI 成功不等于容器部署或生产运行验证。

### 步骤八：Uvicorn 访问日志收口（第四独立检查点）

- Uvicorn access logger 已禁用，Dockerfile 和 README 的启动示例显式使用 `--no-access-log`，与应用路径掩码和 Caddy URI/请求头过滤共同避免媒体 Token 进入日志。
- 本步骤验证：`tests/test_api.py` 13 passed；ruff All checks passed。

### 步骤九：Draft PR 创建状态

- 当前分支 `codex/p0-security-production-gates` 已推送至 `origin`；最终本地与远程 HEAD 以交接报告执行时的 `git rev-parse HEAD` 为准。
- 状态：`DECISION_NEEDED`。已通过 GitHub connector 两次尝试创建目标为 `main` 的 Draft PR，但 GitHub API 均返回 `403 Resource not accessible by integration`；本机未安装 `gh` CLI，因此未声称 PR 已创建。
- 分支 push 触发的最新 GitHub Actions run 已成功；在获得 PR 权限前，Draft PR 地址保持为“未创建”。
- 受影响部分：需要用户选择由具备 pull-request 写权限的 GitHub 连接器重试，或由用户在 GitHub 网页使用已登录账号创建 Draft PR；代码、测试和普通分支 push 不受影响。

### 步骤十：媒体路径脱敏边界修正（第五独立检查点）

- 修正媒体路径掩码正则，保留未知后缀路径中的分隔符，同时继续保证 Token 不出现在应用日志。
- 本步骤验证：`tests/test_api.py` 14 passed；ruff All checks passed；随后已正常推送。

### 步骤十一：Token 过期与媒体保留时间拆分（本轮第一独立检查点）

- `result.expires_at` 现在表示当前预览/下载 Token 的实际过期时间；`result.media_expires_at` 单独表示媒体文件的 24 小时保留截止时间。
- 任务结果重新打开时会重新签发短期 Token；旧 Token 失效不会延长媒体会话，结果页保存前按 Token 过期时间判断是否刷新。
- 新增后端端到端覆盖：首次 Token 约 900 秒有效、Token 失效后从仍有效任务重新获取新 Token、媒体保留截止时间不变；新增结果页停留超过 15 分钟后刷新判断测试。
- 本步骤本地验证：`npm test` 31 passed；`npm run validate:miniprogram` 76 files checked、PASS；后端 pytest 99 passed（2 warnings）。
- 本步骤尚未完成远程 CI；下一独立步骤将补充 `npm run validate:production` 和固定版本 Caddy 配置验证。

### 步骤十二：生产配置与 Caddy CI 门禁（本轮第二独立检查点）

- `npm run validate:production` 现在支持通过 `MINIPROGRAM_VALIDATE_SYNTHETIC=1` 注入非敏感合成生产值；不会修改或提交真实生产配置。校验仍强制 `APP_ENV=production`，development 配置有单元测试证明会失败。
- GitHub Actions 的小程序 job 已实际运行 `npm run validate:production`；后端 job 新增固定版本 `caddy:2.10.0-alpine`，以虚构域名 `example.invalid` 执行 `caddy validate`。Caddy 配置通过删除 request URI 和 headers 避免把媒体 Token 写入 access log；运行时日志输出仍需人工抽样确认。
- 本步骤本地验证：`npm test` 32 passed；`npm run validate:miniprogram` 76 files checked、PASS；`MINIPROGRAM_VALIDATE_SYNTHETIC=1 npm run validate:production` PASS；`git diff --check` PASS。
- 本机没有 Docker CLI，Caddy validate 与 Docker build 需由 GitHub Actions runner 实际执行后再记录为 PASS；在此之前不得将 P0 写成全部通过。

### 步骤十三：Windows worker 公网目标前置校验（补充独立修复）

- 在启动 yt-dlp 子进程前拒绝字面量内网/本机 IP，避免 Windows 下 worker 解析 loopback 时超时；保留既有 `PLATFORM_CHANGED` 安全错误语义。
- 针对性测试 `test_adapter_worker_blocks_loopback_without_connecting` 和 ruff 均通过；全量 pytest 首轮曾出现该用例 `PARSE_TIMEOUT`，修复后全量复跑为 99 passed、2 warnings。

### 步骤十四：本轮全量门禁与状态校准

- 当前 HEAD：以本次交接时 `git rev-parse HEAD` 为准；最新提交已推送到 `origin/codex/p0-security-production-gates`。
- 最新分支 push CI 检查（见[分支 Actions 页面](https://github.com/zys1544526484/video-extractor-miniprogram/actions?query=branch%3Acodex%2Fp0-security-production-gates)）成功：Node 32 passed、0 failed；小程序普通校验 74 files checked、生产校验真实执行 `npm run validate:production` 并通过；后端 96 passed、3 skipped（共收集 99 项，skipped 不计为 passed）；Ruff All checks passed；compileall、Alembic 空库升级/head 校验、Docker build 和固定版本 `caddy:2.10.0-alpine caddy validate` 均成功。
- 本地复跑：`npm test` 32 passed；`npm run validate:miniprogram` 76 files checked、PASS；`MINIPROGRAM_VALIDATE_SYNTHETIC=1 npm run validate:production` PASS；pytest 99 passed（2 warnings）；ruff All checks passed；compileall、Alembic 空库升级/head 校验和 `git diff --check` PASS。Windows 工作区未安装 Docker CLI，因此 Docker build/Caddy validate 本地结果为 NOT VERIFIED，由上述远程 CI 验证。
- 本地与 GitHub 小程序文件数差异仅为本地 `.gitignore` 忽略的 `miniprogram/project.config.json`、`miniprogram/project.private.config.json`；它们未提交，故本地 76、干净 checkout 74。
- Token 语义修复已覆盖首次约 900 秒、Token 失效后从仍有效任务重新签发且不延长 `media_expires_at`，以及结果页超过 15 分钟保存前按 Token 过期时间刷新。应用/Caddy 配置静态删除 URI/headers；真实部署日志仍需人工抽样确认。
- 本轮自动化状态：`AUTOMATED_GATES_PASS_EXTERNAL_NOT_VERIFIED`。备案域名、真实微信凭证、服务器、五平台完整样例、真机下载/相册和生产部署继续保持 `NOT VERIFIED`。
- Draft PR 状态仍为 `DECISION_NEEDED`：本轮再次尝试创建目标为 `main` 的 Draft PR，GitHub API 返回 `403 Resource not accessible by integration`；未声称创建成功，也未影响普通分支 push。需用户在网页或使用具备 pull-request 写权限的连接器创建/重试。

## 未验证项

- 未进行微信开发者工具真机验证。
- 未进行部署验证，未使用真实生产凭证。
- 因此当前产品状态仍为 `NOT VERIFIED`。

## 下一步

等待 ChatGPT 审查、GitHub CI 后续检查和用户合并决定；不得直接合并到 `main`。
