# 架构

微信小程序 → HTTPS FastAPI → Auth / Download Entitlement / Parser Registry / Media Session → 公开媒体源。

前端不解析平台页面。后端统一提取 URL、识别平台、选择 Parser，并通过短期 media token 提供预览和下载。用户输入永远不能直接成为代理目标。

