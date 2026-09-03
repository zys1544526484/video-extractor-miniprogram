# 安全与合规

- SSRF：阻断 localhost、内网、link-local、IPv6 本地/私网、metadata、非 HTTP(S)，重定向逐跳复检。
- 媒体：随机 token、TTL、大小/时间/并发限制、文件名清洗、Content-Type 校验。
- 环境隔离：体验版/正式版必须使用 production 配置；生产启动拒绝 Mock、HTTP/IP/占位 API 域名、占位微信凭证和低熵令牌密钥。
- 下载访问：首版 `free` 模式仍要求认证和媒体所有权；保留的广告模式使用服务端摘要凭证、用户绑定、最短等待、一次性消费和幂等审计。
- 外部解析：yt-dlp 禁用插件、用户 site-packages 和代理，在独立子进程中限制资源并阻断非公网 DNS 结果。
- 隐私：最小化保存 openid、下载权益和必要审计；日志不长期记录完整分享 URL。
- 日志：HTTP 客户端日志最低为 WARNING，避免微信 `code2Session` 查询串中的 AppSecret 和一次性 code 进入 INFO 日志。
- 缓存：仅短时处理并自动删除，隐私文案不得声称绝不存储。
- 版权：只处理公开可访问且用户有权保存的内容，不绕过技术保护。
