# 真实平台 Smoke Test 记录

更新时间：2026-09-03

已使用用户提供的两条抖音公开分享短链进行真实网络测试。两次请求都成功到达本机 FastAPI 与隔离的 yt-dlp 子进程，但上游分别要求 fresh cookies 或对公开详情 JSON 返回 HTTP 403，API 合规降级为 `CONTENT_RESTRICTED`；本项目没有导入 Cookie 或模拟登录。因此抖音仍为 `NOT VERIFIED`，这些失败不能算作平台通过。

Generic 使用 W3C 公开 MP4 `https://media.w3.org/2010/05/sintel/trailer.mp4` 完成真实解析、短期媒体 token、Range 预览和带认证下载，预览与下载均返回 HTTP 206，分别读取 1024 bytes；媒体大小 4,372,373 bytes，request_id `req_ff35cd74ebd544ad860df5a0bf726f1b`。

Bilibili 使用用户提供的公开视频 `https://www.bilibili.com/video/BV1G7tG6tEwL/` 完成真实解析、DASH 音视频下载与 ffmpeg 合并、短期媒体 token、Range 预览和带认证下载。源视频 43 分 34 秒；解析器在 180MiB 客户端边界内自动选择 480P H.264 + AAC，成品 142,463,085 bytes，预览与下载均返回 HTTP 206 并分别读取 1024 bytes，request_id `req_7e320414bdd64703aaefa1b2607ec959`。ffprobe 复核为 852×480 H.264 视频流与 AAC 音频流。

新增画质选择后的元数据样例显示：该视频 720P H.264 与音频组合超限，但 720P H.265 与 AAC 预计约 164MB，可作为同分辨率兜底。自动选择测试已通过；连续真实请求后 Bilibili 返回 HTTP 412，最后一次 API 请求规范化为 `PLATFORM_CHANGED`，request_id `req_5a8831ebaa5740e7908e7122996c9d40`。因此本轮未把 720P H.265 写成真实下载 PASS，也未使用 Cookie 或其他方式规避临时限制。

Windows Uvicorn 真实服务回归修复后，再次以同一 Bilibili 样例选择 540P：持久任务从 0–100 完成，输出 480P H.264、时长 2614.315 秒、171,656,688 bytes；预览和带认证下载均以 `Range: bytes=0-1023` 返回 HTTP 206，`Content-Range` 总长一致。任务 `pj_6c20553ebe985a1981ea18c5ab92c94f`。该记录证明本机后端链路可运行，但仍不替代 Android/iOS 相册保存验证。

本机 yt-dlp `2026.08.19` 已列出 Bilibili、微博、小红书和抖音 extractor，未列出快手 extractor。被列出只表示存在适配器，不表示当前网络环境和具体公开视频一定可解析。

| 平台 | 样例数 | 状态 | 备注 |
|---|---:|---|---|
| Generic | 1/3 | PARTIAL | 1 个公开 MP4 的解析、预览与下载真实链路 PASS；仍缺 2 个样例 |
| Bilibili | 1/3 | PARTIAL | 1 个公开视频的解析、DASH 合并、预览与下载真实链路 PASS；仍缺 2 个样例与真机保存 |
| 微博 | 0/3 | NOT VERIFIED | 公开元数据适配器存在 |
| 小红书 | 0/3 | NOT VERIFIED | 公开元数据适配器存在 |
| 抖音 | 0/3 成功；2 次失败 | CONTENT_RESTRICTED | 最新作品 ID `7678631238139268402` 的详情 JSON 返回 403 并要求 fresh cookies；request_id `req_c1fbc8cfcbf14ffa9bc73388b7cfe97a`；未绕过 |
| 快手 | 0/3 | NOT VERIFIED | yt-dlp 未列出 extractor；当前仅 Generic 合规降级路径 |

记录真实样例时只保存页面 URL、测试时间、结果码、媒体大小/时长摘要和 request_id，不保存 Cookie 或私密内容。
