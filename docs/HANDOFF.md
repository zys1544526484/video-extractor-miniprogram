# 协作交接记录

本文件是 ChatGPT（决策与审查入口）、Codex（实现与验证）和 GitHub（分支、commit、Draft PR 中转）之间的长期交接记录。每个可独立验证的步骤完成测试后更新本文件。

## 当前基线

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
