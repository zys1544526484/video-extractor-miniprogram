# API 契约

统一前缀 `/api/v1`，成功和失败响应均包含 `request_id` 与 `success`。

- `GET /health`
- `POST /auth/wechat`
- `GET /entitlement`：查询下载访问模式；返回 `access_mode` 与 `can_download`。首版 `free` 模式直接允许下载。
- `POST /entitlement/ad-attempt`：下载权益无效时，由服务端签发短期、绑定用户的广告尝试凭证。
- `POST /entitlement/ad-complete`：需要认证、`Idempotency-Key`，请求体必须携带前一步的 `attempt_token`。
- `POST /parse`：免费解析公开链接，但仍需认证与限流。请求体为分享文案 `text` 与 `quality`；`quality` 只允许 `original`、`720p`、`540p`，默认 `original`。成功结果回显 `requested_quality`，`quality_label` 始终描述实际媒体。
- `GET /media/{token}/preview`
- `GET /media/{token}/download`：必须认证且 token 属于当前用户；仅 `rewarded_ad` 模式额外检查下载权益。

媒体接口只接受服务端签发 token。错误包含稳定 `code`、中文 `message` 和 `retryable`。

首版 `free` 模式下两个广告完成接口返回 `FEATURE_DISABLED`。未来切换 `rewarded_ad` 后，广告尝试凭证仍只保存 SHA-256 摘要并按原安全规则消费。
