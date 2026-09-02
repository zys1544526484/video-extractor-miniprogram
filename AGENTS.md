# AGENTS.md — 视频提取小程序工程守则

本仓库实现微信原生小程序与 FastAPI 后端。开始修改前先阅读本文件、`docs/00_MASTER_EXECUTION.md` 以及当前任务相关规范。

## 不可违反的边界

- 只处理公开可访问、用户有权保存的内容。
- 不导入用户 Cookie，不模拟登录，不绕过验证码、风控、付费、私密、地域、年龄或 DRM。
- “原始媒体”不代表擦除作者烧录在画面里的水印。
- 媒体代理只接受服务端签发的短期 token，禁止任意 URL 开放代理。
- AppSecret、session_key、数据库密码和完整 Authorization 不得进入代码或日志。
- Mock 登录、Mock 广告和 Mock API 只能用于开发环境，生产启动必须拒绝 Mock 配置。

## 产品闭环

粘贴分享文案 → 免费解析和预览 → 点击保存 → 无下载权益时完整观看激励广告 → 解锁 24 小时下载 → 自动继续下载并保存到相册。展示型广告位仅在配置真实广告单元后渲染。

## 技术栈

- 微信原生小程序：WXML、WXSS、JavaScript、微信原生 API。
- 后端：Python 3.12、FastAPI、Pydantic v2、SQLAlchemy 2、SQLite、httpx、pytest、ruff。
- yt-dlp/ffmpeg 只能用于公开媒体的标准提取、重封装或音视频合并。

## 阶段完成条件

对应代码和测试存在，实际检查通过，安全边界未放宽，`STATUS.md` 与 `BLOCKERS.md` 已更新。未真机、未部署或未使用真实凭证的项目必须标记 `NOT VERIFIED`。

