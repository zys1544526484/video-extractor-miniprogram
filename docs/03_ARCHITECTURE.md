# 架构

微信小程序 → HTTPS FastAPI → Auth / Persistent Parse Queue / Parser Registry / Persistent Media Session → 公开媒体源。

前端不解析平台页面。后端统一提取 URL、识别平台、选择 Parser，并通过短期 media token 提供预览和下载。用户输入永远不能直接成为代理目标。

解析采用 SQLite 持久任务和单节点单并发 worker。小程序创建任务后每 1.5 秒查询进度，并把 `job_id` 写入本地存储；页面重开可继续查询。服务重启时，未过期的排队中/处理中任务重新排队。

所有最终媒体先写入 `TEMP_DIR`。数据库仅保存相对路径，媒体访问 token 只保存 SHA-256 摘要。结果默认可访问 2 小时，异常或过期临时文件最长保留 3 小时后由清理任务删除。
