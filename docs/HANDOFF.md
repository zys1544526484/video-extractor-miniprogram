# 协作交接记录

本文件是 ChatGPT（决策与审查入口）、Codex（实现与验证）和 GitHub（分支、commit、Draft PR 中转）之间的长期交接记录。每个可独立验证的步骤完成测试后更新本文件。

## 当前基线

- 仓库：`https://github.com/zys1544526484/video-extractor-miniprogram`
- 目标基线：`main`
- 任务分支：`codex/p0-security-production-gates`
- `main` 已推送的基线 commit：`519da08d9873ecf099816d18d99b2c4908d68fef`
- 小程序安全检查点：`42334a8bc2a9478bd6926789157494cec23f6d66`
- Draft PR：当前分支尚未创建（历史 PR #1 属于已合并的 bootstrap 分支）

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

- 当前分支 `codex/p0-security-production-gates` 已推送至 `origin`，最新已推送 commit 为 `eaad627d9e0462161572a4f8abeb2286ca2890ba`。
- 状态：`DECISION_NEEDED`。已通过 GitHub connector 两次尝试创建目标为 `main` 的 Draft PR，但 GitHub API 均返回 `403 Resource not accessible by integration`；本机未安装 `gh` CLI，因此未声称 PR 已创建。
- 分支 push 触发的最新 GitHub Actions run 已成功；在获得 PR 权限前，Draft PR 地址保持为“未创建”。
- 受影响部分：需要用户选择由具备 pull-request 写权限的 GitHub 连接器重试，或由用户在 GitHub 网页使用已登录账号创建 Draft PR；代码、测试和普通分支 push 不受影响。

### 步骤十：媒体路径脱敏边界修正（第五独立检查点）

- 修正媒体路径掩码正则，保留未知后缀路径中的分隔符，同时继续保证 Token 不出现在应用日志。
- 本步骤验证：`tests/test_api.py` 14 passed；ruff All checks passed；随后已正常推送。

## 未验证项

- 未进行微信开发者工具真机验证。
- 未进行部署验证，未使用真实生产凭证。
- 因此当前产品状态仍为 `NOT VERIFIED`。

## 下一步

等待 ChatGPT 审查、GitHub CI 和用户合并决定。
