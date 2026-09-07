# 实施阶段

1. 工程体检与状态文件。
2. 微信骨架、页面与 Mock 状态机；首页仅粘贴并提取，结果页提供视频/图片/标题 Tab 与多视频源切换。
3. FastAPI、认证、下载权益和广告幂等。
4. URL 提取、平台识别、Parser Registry 与 Generic Parser。
5. Bilibili、微博、小红书、抖音、快手适配与合规降级。
6. media token、Range、安全代理、临时文件和清理；视频源与解析图片统一落盘后再签发短期地址。
7. Docker、HTTPS、微信生产配置和回归测试。
8. 输出 `RELEASE_READINESS.md`，未验证项写 `NOT VERIFIED`。
