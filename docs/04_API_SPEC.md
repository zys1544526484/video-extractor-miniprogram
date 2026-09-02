# API 契约

统一前缀 `/api/v1`，成功和失败响应均包含 `request_id` 与 `success`。

- `GET /health`
- `POST /auth/wechat`
- `GET /entitlement`：查询下载权益。
- `POST /entitlement/ad-complete`：需要认证和 `Idempotency-Key`。
- `POST /parse`：免费解析公开链接，但仍需认证与限流。
- `GET /media/{token}/preview`
- `GET /media/{token}/download`：必须具有有效下载权益。

媒体接口只接受服务端签发 token。错误包含稳定 `code`、中文 `message` 和 `retryable`。

