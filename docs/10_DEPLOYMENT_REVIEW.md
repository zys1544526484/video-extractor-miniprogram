# 部署与微信提审

V1 使用单机 Docker：Caddy、FastAPI、SQLite volume 和受限临时媒体 volume。生产统一使用备案 HTTPS 域名承载 API、preview 和 download。

上线前必须验证合法域名、TLS、Android/iOS 相册保存、真实微信登录、真实激励广告、Banner 填充、隐私指引、主体类目和广告资格。

