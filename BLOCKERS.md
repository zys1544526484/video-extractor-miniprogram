# BLOCKERS

以下事项不阻塞本地 Mock、后端和自动测试，但阻塞真实上线或提审：

| Gate | 缺少内容 | 影响 |
|---|---|---|
| 微信身份 | AppID、AppSecret | 真实 `wx.login` 换取 openid 未验证 |
| 广告 | 激励视频与 Banner 的 adUnitId | 广告加载、结算、填充率和收益未验证 |
| 网络 | 已备案 HTTPS 域名与服务器 | request/download/video 合法域名无法配置 |
| UI Gate A | 字体放大及 360–430px 多机型人工检查 | 官方工具中的 362×783 Mock 主流程已通过，但 Gate A 尚未全部完成 |
| 容器 | Docker / Docker Compose | 镜像构建、volume、Caddy 自动证书尚未实机验证 |
| 真机 | Android、iOS 设备 | 相册权限、200MB 客户端上限和网络切换未验证 |
| 合规 | 主体、类目、隐私指引、广告资格 | 无法提交微信审核 |

真实平台公开样例 smoke test尚未执行，详见 `docs/PLATFORM_SMOKE_REPORT.md`。这不阻塞本地开发，但阻塞 Release Candidate。
