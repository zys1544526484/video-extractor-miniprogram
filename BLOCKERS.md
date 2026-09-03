# BLOCKERS

以下事项不阻塞本地 Mock、后端和自动测试，但阻塞真实上线或提审：

| Gate | 缺少内容 | 影响 |
|---|---|---|
| 微信身份 | AppSecret 与微信后台联调 | 开发者工具项目已识别 AppID，但真实 `wx.login` 换取 openid 仍未验证 |
| 广告 | 激励视频与 Banner 的 adUnitId | `isEnded` 真机回调、广告加载、结算、填充率和收益未验证；本地凭证不能替代微信广告后台证明 |
| 网络 | 已备案 HTTPS 域名与服务器 | request/download/video 合法域名无法配置 |
| UI Gate A | 字体放大及 360–430px 多机型人工检查 | 官方工具中的 362×783 Mock 主流程已通过，但 Gate A 尚未全部完成 |
| 容器 | Docker / Docker Compose | 镜像构建、volume、Caddy 自动证书尚未实机验证 |
| 真机 | Android、iOS 设备 | 相册权限、200MB 客户端上限、720P H.265 预览/相册播放和网络切换未验证 |
| 合规 | 主体、类目、隐私指引、广告资格 | 无法提交微信审核 |

真实平台 smoke test目前有 1 条 Bilibili 公开视频完整链路通过、1 条 Generic 公开 MP4 通过，以及 2 条抖音公开短链受限记录；微博、小红书和快手尚未执行成功样例，详见 `docs/PLATFORM_SMOKE_REPORT.md`。这不阻塞本地开发，但阻塞 Release Candidate。

当前代码内可修复的 P0 已完成本地验证；备案域名、真实凭证、广告资格、服务器和真机属于外部 Gate，不能用 Mock 或自动测试代替，也不能在补齐前改判为可提审。
