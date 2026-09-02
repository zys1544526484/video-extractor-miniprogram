# 测试与验收

自动测试覆盖 URL 提取、平台伪造域名、下载权益、广告幂等、状态机、SSRF、token 篡改、Range、超时、大小上限和临时清理。真实平台 smoke test单独记录，不能把 skip 写成 PASS。

Release Candidate 不允许已知 P0/P1。单平台可标记 degraded；若 Generic 和所有真实平台均不可用则不可发布。

