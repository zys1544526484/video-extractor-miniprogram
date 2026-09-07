# 真实平台 Smoke Test 记录

更新时间：2026-09-07

此前两条抖音公开分享短链的失败曾被过宽地归类为 `CONTENT_RESTRICTED`。P2 已修正该语义：Cookie、`unavailable`、跳转首页和 `Unsupported URL` 都不足以证明内容私密。只有公开页面或上游明确证明私密、删除、仅好友或必须登录时才使用该错误码；其余公开短链/平台兼容失败使用可重试 `DOUYIN_RESOLVE_FAILED`。

2026-09-07 使用用户此前提供的公开抖音短链，以临时环境变量 `DOUYIN_SMOKE_URL` 执行独立 PoC smoke。SafeHttpClient 将短链安全跳转到路径 `/video/7678631238139268402`；匿名公开 HTML 未提供可安全代理的媒体地址，yt-dlp 短时回退也未提供有效公开来源。总耗时 2717ms，结果为 `DOUYIN_RESOLVE_FAILED`（retryable）。没有提交或导入 Cookie、签名参数、账号会话，也没有把链接写入自动测试。

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
| 抖音 | 0/3 成功；公开 PoC 失败 | DOUYIN_RESOLVE_FAILED | 短链已安全得到具体作品路径，但匿名公开页面未给出可安全使用的媒体地址；2026-09-07 smoke 2717ms；未绕过 |
| 快手 | 0/3 | NOT VERIFIED | yt-dlp 未列出 extractor；当前仅 Generic 合规降级路径 |

记录真实样例时只保存页面 URL、测试时间、结果码、媒体大小/时长摘要和 request_id，不保存 Cookie 或私密内容。
