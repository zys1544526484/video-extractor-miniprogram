# 部署与微信提审

V1 使用单机 Docker：Caddy、FastAPI、SQLite volume 和受限临时媒体 volume。生产统一使用备案 HTTPS 域名承载 API、preview 和 download。

首版上线前必须验证合法域名、TLS、Android/iOS 相册保存、真实微信登录、隐私指引和主体类目；广告与 Banner 不属于本次发布 Gate。
