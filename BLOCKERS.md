# BLOCKERS

以下事项不阻塞本地 Mock、后端和自动测试，但阻塞真实上线或提审：

| Gate | 缺少内容 | 影响 |
|---|---|---|
| 微信身份 | AppSecret 与微信后台联调 | 开发者工具项目已识别 AppID，但真实 `wx.login` 换取 openid 仍未验证 |
| 网络 | 已备案 HTTPS 域名与服务器 | request/download/video 合法域名无法配置 |
| UI Gate A | 字体放大及 360–430px 多机型人工检查 | 官方工具中的 362×783 Mock 主流程已通过，但 Gate A 尚未全部完成 |
| 容器 | Docker / Docker Compose | 镜像构建、volume、Caddy 自动证书尚未实机验证 |
| 真机 | Android、iOS 设备 | 相册权限、接近 180MiB 自动压缩成品、长视频播放、网络切换和中断恢复未验证 |
| 合规 | 主体、类目与隐私指引 | 个人主体类目可用性和审核材料尚未确认 |

真实平台 smoke test目前有 1 条 Bilibili 公开视频完整链路通过、1 条 Generic 公开 MP4 通过，以及抖音公开短链解析失败记录。P2 PoC 已能把最新测试短链安全解析到具体作品页；最新匿名页面的 2 个 script 与 21 个可解码 JSON/hydration 值均没有白名单公开视频字段，无法安全取得媒体地址，故在约 3.2 秒返回 `DOUYIN_RESOLVE_FAILED` 而非误标私密。抖音下载仍为 `NOT VERIFIED`。微博、小红书和快手尚未执行成功样例，详见 `docs/PLATFORM_SMOKE_REPORT.md`。这不阻塞本地开发，但阻塞 Release Candidate。

当前首版为正式免费模式，广告资格和 adUnitId 不再阻塞上线。备案域名、真实微信凭证、服务器、五平台样例和真机仍属于外部 Gate，不能用 Mock 或自动测试代替。

P3 专用会话 PoC 也不消除抖音发布阻塞：短链重定向现已安全解析到用户本轮目标作品 ID，主播放器捕获已覆盖直接 DOM 来源、`source` 子元素和 blob 后单一媒体响应；但当前 Codex 进程没有继承仓库外 `DOUYIN_STORAGE_STATE_PATH`，完整 smoke 在浏览器前返回 `DOUYIN_SESSION_CONFIG_INVALID`。因此本轮既未加载会话，也没有取得目标媒体地址或完成无 Cookie 的 1024-byte 复验。若启用生产 PoC，`DOUYIN_STORAGE_STATE_PATH` 必须是仓库外、存在、JSON 格式有效且权限安全的文件；bootstrap 必须先发现非空 `douyin.com` Cookie，失败时保留旧文件且不生成新会话。会话失效、可见验证码/风控或仅会话可下载媒体必须停止而不是规避。该 PoC 尚未接入生产解析流程。

用户报告的 headed Chromium 完整成功证明专用会话路线曾可在人工可视环境完成目标作品、媒体域名和无 Cookie 1024-byte 复验；相同作品的标准 headless 曾在约 30 秒超时，故仍不可作为生产可部署结论。最新 Headed 诊断已证明登录、目标 ID 与可见 blob 主播放器正常，并捕获多个 MP4 CDN 响应；本轮不再从这些匿名响应猜选，而是优先使用与目标 `aweme_id` 双向匹配的官方详情 JSON 或页面 hydration 中的严格媒体字段。若仍没有这种绑定证据，多个候选继续安全失败。该策略和 cleanup 已关闭误报已完成自动测试，但尚未在该 Windows 会话复测，不能据此推断 headed/headless 已恢复。Xvfb、headless 阶段耗时、会话更新重载与浏览器暖复用仍须真实 Linux/Windows 验证；其中暖复用尚未实现。

本次 P0 加固（2026-09-04）增加了媒体 Token 日志脱敏、Token 与媒体保留时间拆分、900 秒 Token TTL、标准端口 SSRF 校验、production Alembic head 门禁和 GitHub Actions 自动检查；最新 CI 已通过生产配置、Docker build 和固定版本 Caddy 语法校验，但未消除任何真实上线阻塞。备案域名、真实微信凭证、服务器、平台样例和真机验证继续保持为 `NOT VERIFIED` / Release Candidate 阻塞项。部署后的 Caddy access log 脱敏仍需人工抽样，Docker Compose 运行和生产部署仍需真实环境验证。
