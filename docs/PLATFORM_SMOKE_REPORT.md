# 真实平台 Smoke Test 记录

更新时间：2026-09-09

此前两条抖音公开分享短链的失败曾被过宽地归类为 `CONTENT_RESTRICTED`。P2 已修正该语义：Cookie、`unavailable`、跳转首页和 `Unsupported URL` 都不足以证明内容私密。只有公开页面或上游明确证明私密、删除、仅好友或必须登录时才使用该错误码；其余公开短链/平台兼容失败使用可重试 `DOUYIN_RESOLVE_FAILED`。

2026-09-07 使用用户此前提供的公开抖音短链，以临时环境变量 `DOUYIN_SMOKE_URL` 执行独立 PoC smoke。SafeHttpClient 将短链安全跳转到路径 `/video/7678631238139268402`；匿名公开 HTML 未提供可安全代理的媒体地址，yt-dlp 短时回退也未提供有效公开来源。总耗时 2717ms，结果为 `DOUYIN_RESOLVE_FAILED`（retryable）。没有提交或导入 Cookie、签名参数、账号会话，也没有把链接写入自动测试。

审查修正后再次 smoke：解析器不再扫描字段附近的 URL，而只读取 script 内结构化 JSON、JSON-LD 或 hydration JSON 的白名单视频字段。该匿名页面有 2 个 script、21 个可解码 JSON/hydration 值，但未发现 `video.play_addr`、`video.play_addr_h264`、`video.download_addr` 或 `video.bit_rate[*].play_addr`。因此本次没有取得媒体地址，3234ms 后仍正确返回 `DOUYIN_RESOLVE_FAILED`（retryable），不能描述为解析成功。

P3 增加了默认关闭的运营者服务器专用会话 PoC，但本轮**未执行真实 session smoke**：当前环境没有可验证的运营者手动登录会话，未取得真实媒体地址，也未进行无 Cookie 1024-byte 读取。该缺口记录为 `NOT VERIFIED`，不能以自动 fake-browser 测试替代。后续仅可在运营者手动登录、会话文件保留在仓库外且没有验证码/风控时，针对用户有权保存的公开作品单独记录耗时和结果；不得保存 Cookie、完整签名地址或会话内容。

P3 短链修正后，用户本轮提供的短链可由无会话的安全重定向阶段规范到作品 ID `7678969660380843304`。该阶段对初始地址和每一跳均执行 SafeHttpClient 的 SSRF/DNS/IP 校验及抖音域名/作品路径白名单；正常查询参数仅在已核实数字 ID 后丢弃，日志不保存查询、Cookie、Token 或签名。完整 smoke 以临时开关运行时，在浏览器启动前因当前进程没有配置仓库外 storage state 返回 `DOUYIN_SESSION_CONFIG_INVALID`，总耗时 `516ms`。因此本次未加载会话、未取得媒体地址、未进行无 Cookie 1024-byte 读取，仍为 `NOT VERIFIED`，不得描述为抖音下载成功。

P3 主播放器捕获已扩展并具有自动回归：直接 `currentSrc`、`src`、`video > source[src]`、延迟来源、blob 后唯一 video/HLS 响应均覆盖；预加载、广告或推荐响应不会被选作目标媒体。启动仅发生在页面身份严格匹配目标作品后，且只对选定主播放器静音播放，不会点击登录、验证码、风控或广告。当前 Codex 进程复跑时没有继承外部 storage-state 配置，安全输出为 `DOUYIN_SESSION_CONFIG_INVALID`、保留作品 ID `7678969660380843304`、耗时 `921ms`；未打开运营者会话，实际媒体地址、无 Cookie 1024-byte 读取和真实耗时仍为 `NOT VERIFIED`。

用户在本机报告：同一公开作品的 headed Chromium session smoke 已取得 douyinvod 媒体域名并无 Cookie 读取 1024 bytes，耗时 20171ms；headless 仍在约 30546ms 返回 `DOUYIN_SESSION_TIMEOUT`。这证明 headed 路线，不证明 headless 或可部署性。后续 smoke 日志将按 browser launch、页面导航、身份、播放器、媒体捕获、媒体复验分别记录安全阶段耗时；实际 Xvfb/headless 与暖启动结果尚未产生，均为 `NOT VERIFIED`。

2026-09-08 的 M1 未新增真实平台结果：已提供 `scripts/verify_douyin_session.ps1`，用于对最新 P3 只执行一次 Headed smoke。当前 Codex 进程仅验证到安全前置失败 `VERIFY_SESSION_NOT_ENABLED`，没有启动浏览器、读取 storage state 或发送抖音请求。必须等待运营者在原有已配置终端运行该脚本后的单行脱敏 JSON，不能把自动测试或历史单次 headed 成功当作最新版本 PASS。

2026-09-09 用户完成首次 M1 一键 Headed 验收：短链进入正确作品 `7678969660380843304`，最终页为对应 `/video/{id}`，2 个 video 中只有 1 个可见主播放器，播放器为 blob/MediaSource；网络观察到 4 个 `video/mp4` 响应和单一脱敏 douyinvod 域名，但没有结构化目标媒体或受控等价组，最后在 `player_seek` 返回 `DOUYIN_SESSION_MEDIA_NOT_FOUND`。该结果是真实失败，未取得媒体地址、未执行成功的无 Cookie 1024-byte 读取，不能计入抖音 3/3 样例。随后 `de34af6` 增加导航前的数据流归属，把实际追加到当前主播放器 MediaSource 的 payload 与已观察视频响应交叉验证；自动测试和无会话合成 Chromium 验证通过，但该新版本尚未对真实作品复测，状态仍为 `NOT VERIFIED`。按 M1 约束只再允许一次一键 Headed 验收；如仍失败则保持功能关闭并记录阻塞。

随后用户将 `e548e6d6dbfd76a8236b1f59ee3f1466530e3f68` 的 Headed 结果指定为新的权威真实样本：同一作品 ID 与 canonical 路径、唯一可见 blob 主播放器、4 个 origin-only `video/mp4` 响应均成立，但 13.702 秒后仍在 `player_seek` 返回 `DOUYIN_SESSION_MEDIA_NOT_FOUND`；没有形成候选组或等价组，也没有完成公开 1024-byte 读取。审计确认旧版只按 JavaScript payload 对象身份关联 SourceBuffer，真实复制/切片后关联丢失。`935c13b0cc26c0f6bd9feda7a590705c6bae2847` 改为记录当前视频 SourceBuffer 的有界追加字节，并用无 Cookie 精确 Range 内容指纹、SSRF/public URL、主框架、允许 Referer、唯一视频缓冲和唯一强等价组共同证明归属；[CI 34305162529](https://github.com/zys1544526484/video-extractor-miniprogram/actions/runs/34305162529) 已成功。该提交尚无新的真实 Headed 结果；抖音仍为 `0/3`、`NOT VERIFIED`。

Generic 使用 W3C 公开 MP4 `https://media.w3.org/2010/05/sintel/trailer.mp4` 完成真实解析、短期媒体 token、Range 预览和带认证下载，预览与下载均返回 HTTP 206，分别读取 1024 bytes；媒体大小 4,372,373 bytes，request_id `req_ff35cd74ebd544ad860df5a0bf726f1b`。

Bilibili 使用用户提供的公开视频 `https://www.bilibili.com/video/BV1G7tG6tEwL/` 完成真实解析、DASH 音视频下载与 ffmpeg 合并、短期媒体 token、Range 预览和带认证下载。源视频 43 分 34 秒；解析器在 180MiB 客户端边界内自动选择 480P H.264 + AAC，成品 142,463,085 bytes，预览与下载均返回 HTTP 206 并分别读取 1024 bytes，request_id `req_7e320414bdd64703aaefa1b2607ec959`。ffprobe 复核为 852×480 H.264 视频流与 AAC 音频流。

图文解析状态单独计算：抖音、小红书、快手、微博和 Bilibili 均为 `NOT VERIFIED`。上面的 Bilibili 视频样例不代表 Bilibili 图文或图片列表解析通过；在每个平台完成公开图文样例验证前，不得写成 PASS。

新增画质选择后的元数据样例显示：该视频 720P H.264 与音频组合超限，但 720P H.265 与 AAC 预计约 164MB，可作为同分辨率兜底。自动选择测试已通过；连续真实请求后 Bilibili 返回 HTTP 412，最后一次 API 请求规范化为 `PLATFORM_CHANGED`，request_id `req_5a8831ebaa5740e7908e7122996c9d40`。因此本轮未把 720P H.265 写成真实下载 PASS，也未使用 Cookie 或其他方式规避临时限制。

Windows Uvicorn 真实服务回归修复后，再次以同一 Bilibili 样例选择 540P：持久任务从 0–100 完成，输出 480P H.264、时长 2614.315 秒、171,656,688 bytes；预览和带认证下载均以 `Range: bytes=0-1023` 返回 HTTP 206，`Content-Range` 总长一致。任务 `pj_6c20553ebe985a1981ea18c5ab92c94f`。该记录证明本机后端链路可运行，但仍不替代 Android/iOS 相册保存验证。

本机 yt-dlp `2026.08.19` 已列出 Bilibili、微博、小红书和抖音 extractor，未列出快手 extractor。被列出只表示存在适配器，不表示当前网络环境和具体公开视频一定可解析。

| 平台 | 样例数 | 状态 | 备注 |
|---|---:|---|---|
| Generic | 1/3 | PARTIAL | 1 个公开 MP4 的解析、预览与下载真实链路 PASS；仍缺 2 个样例 |
| Bilibili | 1/3 | PARTIAL | 1 个公开视频的解析、DASH 合并、预览与下载真实链路 PASS；图文解析 NOT VERIFIED；仍缺 2 个样例与真机保存 |
| 微博 | 0/3 | NOT VERIFIED | 公开元数据适配器存在 |
| 小红书 | 0/3 | NOT VERIFIED | 公开元数据适配器存在 |
| 抖音 | 0/3 成功；公开 PoC 失败，专用会话 PoC 未实测 | NOT VERIFIED | 匿名短链未给出可安全使用的媒体地址；运营者专用会话默认关闭且尚未手动登录/实测；未绕过 |
| 快手 | 0/3 | NOT VERIFIED | yt-dlp 未列出 extractor；当前仅 Generic 合规降级路径 |

记录真实样例时只保存页面 URL、测试时间、结果码、媒体大小/时长摘要和 request_id，不保存 Cookie 或私密内容。
