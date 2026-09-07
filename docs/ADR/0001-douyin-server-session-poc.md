# ADR 0001：运营者服务器专用抖音会话 PoC

日期：2026-09-07

## 决策

用户明确选择一条窄范围的实验路线：服务器可复用**运营者自行手动登录**的抖音专用会话，用于检测用户有权保存的公开作品。该能力默认关闭，独立于常规解析器和小程序 API，不构成生产接入授权。

## 允许范围

- 仅在 `DOUYIN_SESSION_ENABLED=true` 且会话文件位于仓库外、权限安全且格式有效时可运行。
- bootstrap 只打开可视浏览器，由运营者手动扫码或登录；不接收账号、密码或 Cookie 参数。
- worker 只接受已验证的 `https://www.douyin.com/video/{数字ID}`，只接受与目标 ID 一致的公开视频媒体。
- 抓到候选媒体后，仍使用不携带会话 Cookie 的 `SafeHttpClient` 进行公网、重定向、MIME、大小和最小读取检查。

## 明确禁止

- 用户 Cookie、账号、密码、Token、Authorization、storage state 进入 Git、数据库、日志、API 或小程序。
- 自动填写登录表单，验证码、滑块、设备验证、风控、地区、年龄、付费、私密、好友可见或 DRM 绕过。
- 将会话 Cookie 转交 SafeHttpClient，或写进 `required_headers`。
- 保证删除作者在画面内烧录的标识。

## 失败语义

登录失效使用 `DOUYIN_SESSION_EXPIRED`；验证码或风险页使用 `DOUYIN_RISK_CONTROLLED`；仅会话可访问的媒体使用 `SESSION_BOUND_MEDIA`。三者都不触发重试规避，也不视为 POC 成功。

## 验收门槛

完整成功必须同时证明：目标 ID 一致、取得媒体地址、无 Cookie 的 SafeHttpClient 至少读取 1024 字节视频、耗时有记录、且没有敏感会话数据泄露。当前开发环境没有运营者交互式登录会话，手动登录和真实媒体能力均为 `NOT VERIFIED`。
