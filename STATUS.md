# STATUS

更新时间：2026-09-03

## 当前阶段

- Phase 00 工程基线：`COMPLETE`。
- Phase 01–03 微信端与 Mock 闭环：`COMPLETE / LOCAL VERIFIED`。
- Phase 04–16 后端、权益、安全代理：`COMPLETE / LOCAL VERIFIED`。
- Phase 17–22 平台适配：代码和 contract tests 已完成；Generic 与 Bilibili 各有 1 个真实网络样例通过，其余平台 `NOT VERIFIED`。
- Phase 23–26 部署与发布：Docker/Alembic/Caddy 文件已完成；微信开发者工具 Mock 主流程已本机验证，容器、真机和生产部署 `NOT VERIFIED`。

## 本地验证结果

- 前端 Node 单测：25/25 PASS。
- 小程序 JSON、路由、资源引用、JS 语法：67 文件 PASS。
- 后端 pytest：81/81 PASS。
- `ruff check app tests alembic`：PASS。
- `compileall app alembic`：PASS。
- Alembic 空 SQLite 数据库升级到 `0003_parse_jobs_media_sessions`：PASS。
- Uvicorn 进程级 health/auth/entitlement/ad-complete：PASS。
- 首版正式免费模式：`DOWNLOAD_ACCESS_MODE=free` 时登录用户可直接下载，前端隐藏广告与权益 Gate，生产配置不要求 adUnitId；广告模式代码保留但默认关闭。
- 持久解析任务：创建/轮询/取消、幂等、用户隔离、服务重启恢复、页面重开续查和 0–100 进度自动测试 PASS；任务与媒体会话存入 SQLite，token 只存摘要，结果默认有效 2 小时。
- 大视频媒体管道：2GiB 源暂存上限、64KiB 分块流式下载、Range 断点续传、10GiB 磁盘门禁、FFprobe 校验和 FFmpeg H.264/AAC 自动压缩已通过自动测试；最终只交付一个不超过 180MiB 的 MP4。实际大文件真机保存仍 `NOT VERIFIED`。
- Generic 公网 MP4 真实链路：解析、短期 token、Range 预览和带认证下载 PASS（HTTP 206）。
- Bilibili 公开视频真实链路：公开元数据预检、180MiB 内 H.264 自动降档、DASH 下载与 ffmpeg 合并、短期 token、Range 预览和带认证下载 PASS（HTTP 206）；该样例为 480P H.264 + AAC、142,463,085 bytes，真机保存仍 `NOT VERIFIED`。
- 画质选择：原视频/720P/540P 参数、首页选择器、过期结果按原选择刷新、超限自动降档和实际画质标注已通过自动测试；长视频 Android/iOS 预览和保存尚未真机验证。
- 432×911、360×800、430×932 浏览器视觉验收与核心广告保存流程：PASS。
- 微信开发者工具 Stable 2.02.2608060、基础库 3.17.2、362×783 模拟器：页面加载、输入、Mock 提取、结果页、广告解锁、下载进度和保存成功状态 PASS。
- P0 修复后使用官方开发者工具 CLI 重新执行 `open` 与 `auto`：项目载入/编译 PASS；本轮未把该检查扩大为真机或真实广告验证。
- 画质选择改动后再次执行官方 CLI `open` 与 `auto`：项目载入/编译 PASS；Windows 界面截图接口返回 `SetIsBorderRequired 0x80004002`，三段式控件的视觉人工确认仍为 `NOT VERIFIED`。
- 首版免费模式改动后再次执行官方开发者工具 CLI `open` 与 `auto`：项目载入/编译 PASS；广告隐藏后的完整视觉与真机保存仍为 `NOT VERIFIED`。
- 持久任务与大视频进度改动后再次执行官方开发者工具 CLI `open` 与 `auto`：项目载入/编译 PASS；65 分钟长任务、接近 180MiB 成品和相册保存仍需真机验证。
- 小程序上传包估算由约 2.6MiB 降至约 99KiB；测试目录与未使用的大图已通过 `packOptions.ignore` 排除，尚未执行真实上传。
- 上线前 P0 代码修复：体验版/正式版生产配置强制校验、微信登录查询串日志降级、服务端广告尝试凭证、yt-dlp 独立受限子进程与 Windows UTF-8 协议均已本地回归通过。
- 用户提供的抖音公开短链真实 smoke test到达解析器，但上游要求 fresh cookies，按合规边界返回 `CONTENT_RESTRICTED`；没有导入 Cookie，抖音能力仍为 `NOT VERIFIED`。

## 已确认产品决策

- 首版解析、预览和保存均免费，仍要求登录和媒体所有权校验。
- 首版不展示 Banner 或激励广告；后续商业化通过 `rewarded_ad` 模式启用。
- 相册保存 V1 只交付 MP4；不支持的公开格式返回规范错误。
- 单平台可合规降级，不影响其他平台。

## 发布判断

**不可提审 / NOT READY**。见 `RELEASE_READINESS.md` 和 `BLOCKERS.md`；任何未完成的真实能力均不得写成 PASS。
