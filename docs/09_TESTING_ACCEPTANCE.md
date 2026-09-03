# 测试与验收

自动测试覆盖 URL 提取、平台伪造域名、画质参数白名单、自动降档如实标注、H.264/AAC 单文件输出、免费/广告模式隔离、广告幂等、持久任务、状态机、SSRF、token 篡改、Range、源文件断点续传、FFprobe、FFmpeg 压缩、磁盘门禁、超时、成品大小上限和临时清理。真实平台 smoke test单独记录，不能把 skip 写成 PASS。

Release Candidate 不允许已知 P0/P1。单平台可标记 degraded；若 Generic 和所有真实平台均不可用则不可发布。
