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

本轮进一步把无结构化字段的 blob 响应限制在目标可见主播放器的受控启动窗口：隐藏 video 会被暂停并禁用预加载，窗口外媒体只统计拒绝原因；窗口内必须满足主框架、canonical Referer、MIME、SSRF 和唯一等价组。跨 CDN 的相同规范路径/Ranges 可作为一个候选组，多个不同组保持失败；无 Cookie 小范围内容哈希只在内存中比较。该机制尚未在用户当前 Windows 会话上真实执行，不能描述为媒体已取得或下载成功。

Referer 现已按完整目标路径、抖音 origin-only、其他抖音路径、外部来源和缺失来源分别计数；图片/脚本/接口等非媒体 MIME 不进入这些计数。origin-only 不是通配许可，只有严格目标页、唯一可见主播放器与受控窗口等全部约束成立后才可参与唯一候选组；其他三类始终拒绝。真实 Windows 会话尚未复测，因此仍不能据此判断该公开作品已下载成功。

M1 已把最新 P3 的必要自动检查收敛为 `scripts/verify_douyin_session.ps1`。本机自动预检、测试和远程 CI 均已通过，但当前 Codex 进程不读取运营者会话，因此真实 Headed 结果仍是人工 Gate。用户只需在原先已配置会话的 PowerShell 中运行一次脚本；在收到这一次严格脱敏 JSON 前，不进入暖浏览器、Xvfb/headless 选型或正式 Parser 接入。

2026-09-09 的首次 M1 真实一键结果仍为 `DOUYIN_SESSION_MEDIA_NOT_FOUND`：作品页、作品 ID、唯一可见 blob 主播放器均已确认，且观察到 4 个 origin-only Referer 的 MP4 响应，但受控 play/seek 窗口没有产生可归属的新请求。最后一次集中修正改为从导航前追踪媒体 payload 到当前主播放器 Blob/MediaSource 的实际追加关系，并继续要求已观察 MIME/主框架/Referer、SSRF 和无 Cookie Range 复验；不会从 4 个裸响应中猜选。自动与合成 Chromium 验证通过，但修正后的真实 Headed 结果仍为 `NOT VERIFIED`。下一次一键验收若仍失败，P3 必须保持默认关闭并作为平台阻塞记录，不再用新的启发式规则无限延长 PoC。

同日用户在 `e548e6d6dbfd76a8236b1f59ee3f1466530e3f68` 上执行的最后一次真实 Headed 样本仍失败：作品 ID 与 `/video/{id}` 正确，2 个 video 中仅 1 个可见，主播放器为 blob/MediaSource，观察到 4 个 `video/mp4` 且 Referer 全为 douyin origin-only，但在 `player_seek` 以 `DOUYIN_SESSION_MEDIA_NOT_FOUND` 结束，未读取公开媒体字节。审计定位为旧 MSE 溯源仅保留 JavaScript payload 对象身份；真实播放器复制/切片后无法把已观察响应绑定到 SourceBuffer。当前修正使用有界 SourceBuffer 追加字节与无 Cookie Range 内容做双向证明，并保留唯一 SourceBuffer/唯一强等价组、SSRF 和严格身份约束；自动测试或 CI 不能替代下一次真实结果，因此抖音下载仍为 `NOT VERIFIED`，P3 继续默认关闭。

新的权威 Headed 样本在 `64a9b1b9bf1f1a1acb3964f2e482f636b429090c` 上已经形成 `main_player_mse` 的唯一绑定组与唯一等价组，说明真实 blob 主播放器媒体归属已生效；失败已后移到公开媒体探测。根因是 session smoke 将微信最终成品 `180MiB` 上限错误用于上游源文件，导致较大的有效源在无 Cookie 1024-byte Range 读取前被拒绝。`6e42163dfd77ef9a2b50de0a309ab9929fe86a7f` 已改用默认 `2GiB` 的源文件处理上限，同时保留最终 `180MiB` 成品约束、SSRF、唯一归属和无 Cookie Range 复验；CI 已通过。修复后的真实字节读取仍未执行，所以抖音仍为 `0/3`、`NOT VERIFIED`，且 P3 继续默认关闭。

本次 P0 加固（2026-09-04）增加了媒体 Token 日志脱敏、Token 与媒体保留时间拆分、900 秒 Token TTL、标准端口 SSRF 校验、production Alembic head 门禁和 GitHub Actions 自动检查；最新 CI 已通过生产配置、Docker build 和固定版本 Caddy 语法校验，但未消除任何真实上线阻塞。备案域名、真实微信凭证、服务器、平台样例和真机验证继续保持为 `NOT VERIFIED` / Release Candidate 阻塞项。部署后的 Caddy access log 脱敏仍需人工抽样，Docker Compose 运行和生产部署仍需真实环境验证。
