# API 契约

统一前缀 `/api/v1`，成功和失败响应均包含 `request_id` 与 `success`。

- `GET /health`
- `POST /auth/wechat`
- `GET /entitlement`：查询下载访问模式；返回 `access_mode` 与 `can_download`。首版 `free` 模式直接允许下载。
- `POST /entitlement/ad-attempt`：下载权益无效时，由服务端签发短期、绑定用户的广告尝试凭证。
- `POST /entitlement/ad-complete`：需要认证、`Idempotency-Key`，请求体必须携带前一步的 `attempt_token`。
- `POST /parse`：创建持久解析任务，要求认证和 `Idempotency-Key`，返回 HTTP 202。请求体为分享文案 `text` 与 `quality`；`quality` 只允许 `original`、`720p`、`540p`，默认 `original`。
- `GET /parse/jobs`：返回当前用户最近 24 小时的任务与结果摘要，最多 50 条；列表不签发媒体 token，也不返回下载地址。
- `GET /parse/jobs/{job_id}`：查询 `queued/processing/ready/failed/cancelled/expired` 状态、0–100 进度和当前阶段。`ready` 时返回媒体结果，`quality_label` 始终描述实际媒体。
- `DELETE /parse/jobs/{job_id}`：取消未完成任务。任务和结果均绑定当前登录用户。
- `GET /media/{token}/preview`
- `GET /media/{token}/download`：短期能力链接，不要求小程序 `Authorization` 请求头，适合复制后独立打开；token 仍必须由服务端签发并映射到已验证用户的媒体会话，不能作为任意 URL 代理。`rewarded_ad` 模式在访问时检查该媒体会话所属用户的下载权益。

`ready.result` 兼容旧缓存的单媒体字段，并新增：

- `sources[]`：每项包含 `source_id`、实际 `quality_label`、`size_bytes`、`mime_type`、短期 `preview_url`、短期 `download_url`、`expires_at` 和 `media_expires_at`。所有地址均为本服务签发的媒体 token 地址，不返回上游媒体直链、Cookie 或长期 token。
- `images[]`：每项包含 `image_id`、`alt`、`mime_type`、`size_bytes` 及本服务短期预览/下载地址；服务端无法安全落盘的图片不进入列表。
- `share_text`：作品分享文案；`selected_source_id`：当前视频源。旧结果没有这些字段时，客户端按顶层 `preview_url`/`download_url` 合成 `source-1`。

视频结果只有解析器明确返回的作品图片才进入 `images[]`；`cover_url` 永远只是封面，不能自动变成图片项。纯图片作品返回 `media_type: "image"`、`sources: []`，并以 `images[]` 作为图片页的唯一内容来源。

媒体接口只接受服务端签发 token。错误包含稳定 `code`、中文 `message` 和 `retryable`。

同一用户最多保留 2 个活动任务，开发默认启用 2 个任务 worker；生产示例仍按 2 核 4GB 配置 1 个 worker，第二个任务进入队列。FFmpeg 媒体处理默认只允许 1 路，避免多条大视频同时转码耗尽资源。服务端结果和任务记录默认保留 24 小时；用户读取已完成任务时重新签发不超过该结果原有效期的短期 token。

首版 `free` 模式下两个广告完成接口返回 `FEATURE_DISABLED`。未来切换 `rewarded_ad` 后，广告尝试凭证仍只保存 SHA-256 摘要并按原安全规则消费。
