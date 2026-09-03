# API 契约

统一前缀 `/api/v1`，成功和失败响应均包含 `request_id` 与 `success`。

- `GET /health`
- `POST /auth/wechat`
- `GET /entitlement`：查询下载访问模式；返回 `access_mode` 与 `can_download`。首版 `free` 模式直接允许下载。
- `POST /entitlement/ad-attempt`：下载权益无效时，由服务端签发短期、绑定用户的广告尝试凭证。
- `POST /entitlement/ad-complete`：需要认证、`Idempotency-Key`，请求体必须携带前一步的 `attempt_token`。
- `POST /parse`：创建持久解析任务，要求认证和 `Idempotency-Key`，返回 HTTP 202。请求体为分享文案 `text` 与 `quality`；`quality` 只允许 `original`、`720p`、`540p`，默认 `original`。
- `GET /parse/jobs/{job_id}`：查询 `queued/processing/ready/failed/cancelled/expired` 状态、0–100 进度和当前阶段。`ready` 时返回媒体结果，`quality_label` 始终描述实际媒体。
- `DELETE /parse/jobs/{job_id}`：取消未完成任务。任务和结果均绑定当前登录用户。
- `GET /media/{token}/preview`
- `GET /media/{token}/download`：必须认证且 token 属于当前用户；仅 `rewarded_ad` 模式额外检查下载权益。

媒体接口只接受服务端签发 token。错误包含稳定 `code`、中文 `message` 和 `retryable`。

小程序默认每 1.5 秒轮询，最长等待 30 分钟；`job_id` 保存在本地，页面重开后继续。服务端结果默认可访问 2 小时，每次读取已完成任务时重新签发不超过该结果原有效期的短期 token。

首版 `free` 模式下两个广告完成接口返回 `FEATURE_DISABLED`。未来切换 `rewarded_ad` 后，广告尝试凭证仍只保存 SHA-256 摘要并按原安全规则消费。
