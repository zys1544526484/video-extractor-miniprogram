# API 契约

统一前缀 `/api/v1`，成功和失败响应均包含 `request_id` 与 `success`。

- `GET /health`
- `POST /auth/wechat`
- `GET /entitlement`：查询下载权益。
- `POST /entitlement/ad-attempt`：下载权益无效时，由服务端签发短期、绑定用户的广告尝试凭证。
- `POST /entitlement/ad-complete`：需要认证、`Idempotency-Key`，请求体必须携带前一步的 `attempt_token`。
- `POST /parse`：免费解析公开链接，但仍需认证与限流。请求体为分享文案 `text` 与 `quality`；`quality` 只允许 `original`、`720p`、`540p`，默认 `original`。成功结果回显 `requested_quality`，`quality_label` 始终描述实际媒体。
- `GET /media/{token}/preview`
- `GET /media/{token}/download`：必须具有有效下载权益。

媒体接口只接受服务端签发 token。错误包含稳定 `code`、中文 `message` 和 `retryable`。

广告尝试凭证只保存 SHA-256 摘要，默认 10 分钟过期、一次性消费；客户端不得提交解锁时长或服务端时间。微信激励广告没有可供本服务独立验真的服务端观看回调时，凭证只用于约束客户端完成事件，最终仍必须以真机 `isEnded === true` 闭环验证。
