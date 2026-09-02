# Release Readiness — V1

更新时间：2026-09-02

## 当前结论

**不可提审（NOT READY）**。本地 Mock、静态检查和后端自动测试通过，不代表真实微信能力、广告收益或平台解析已验证。

## 已完成

- 微信原生五页面、首页/我的底部导航和统一视觉变量。
- 免费解析/预览，保存时激励广告解锁 24 小时，完整观看后自动继续保存。
- 激励广告页面内单例生命周期、`isEnded` 判断和 Banner 条件渲染。
- FastAPI 登录令牌、SQLite 权益与广告幂等审计。
- Generic 与平台适配器、短期媒体 token、Range、大小/超时/并发限制。
- SSRF 公网 IP 固定、逐跳重定向复检、响应大小和 Content-Type 校验。
- Alembic、Dockerfile、Compose 和 Caddy HTTPS 样例。
- 自动测试：前端 15 项、后端 43 项；小程序结构/语法/资源校验通过。
- 微信开发者工具 Stable 2.02.2608060 / 基础库 3.17.2 的 362×783 Mock 主流程通过。

## 未验证 Gate

| Gate | 状态 | 通过条件 |
|---|---|---|
| A 开发者工具 UI | PARTIAL | 362×783 Mock 主流程已通过；五页面、字体放大和 360–430px 多机型仍需人工检查 |
| B 微信与广告 | NOT VERIFIED | AppID/AppSecret、激励广告和 Banner 真机闭环通过 |
| C 真实解析 | NOT VERIFIED | Generic 加至少一个真实平台，各 3 个公开样例有记录 |
| D 真机下载 | NOT VERIFIED | Android/iOS 的 10MB、50MB、接近 180MiB、权限拒绝恢复、4G/Wi-Fi 通过 |
| E 合规与提审 | NOT VERIFIED | 备案 HTTPS、合法域名、隐私指引、类目、主体和广告资格齐备 |

## 发布红线

- 生产配置不得启用任何 Mock。
- 不得导入 Cookie、模拟登录或绕过付费、私密、风控、验证码、地域、年龄、DRM。
- Generic 与全部真实平台均不可用时不得发布。
- 发布候选不得存在 P0/P1；单平台只能以明确的“维护中/当前受限”降级。
