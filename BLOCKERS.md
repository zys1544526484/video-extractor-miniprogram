# BLOCKERS

以下事项不阻塞本地 Mock、后端和自动测试，但阻塞真实上线或提审：

| Gate | 缺少内容 | 影响 |
|---|---|---|
| 微信身份 | AppSecret 与微信后台联调 | 开发者工具项目已识别 AppID，但真实 `wx.login` 换取 openid 仍未验证 |
| 网络 | 已备案 HTTPS 域名与服务器 | request/download/video 合法域名无法配置 |
| UI Gate A | 字体放大及 360–430px 多机型人工检查 | 官方工具中的 362×783 Mock 主流程已通过，但 Gate A 尚未全部完成 |
| 容器 | Docker / Docker Compose | 镜像构建、volume、Caddy 自动证书尚未实机验证 |
| 真机 | Android、iOS 设备 | 相册权限、接近 180MiB 自动压缩成品、长视频播放、网络切换和中断恢复未验证 |
| 合规 | 主体、类目与隐私指引 | 个人主体类目可用性和审核材料尚未确认 |

真实平台 smoke test目前有 1 条 Bilibili 公开视频完整链路通过、1 条 Generic 公开 MP4 通过，以及 2 条抖音公开短链受限记录；微博、小红书和快手尚未执行成功样例，详见 `docs/PLATFORM_SMOKE_REPORT.md`。这不阻塞本地开发，但阻塞 Release Candidate。

当前首版为正式免费模式，广告资格和 adUnitId 不再阻塞上线。备案域名、真实微信凭证、服务器、五平台样例和真机仍属于外部 Gate，不能用 Mock 或自动测试代替。
