# 真实平台 Smoke Test 记录

更新时间：2026-09-01

本轮未进行真实网络样例测试，因为没有确认可授权用于测试和留档的公开样例。所有平台均按要求标记 `NOT VERIFIED`，不能以 fixture 或 Mock 替代。

| 平台 | 样例数 | 状态 | 备注 |
|---|---:|---|---|
| Generic | 0/3 | NOT VERIFIED | 本地 HTML/direct fixtures 已通过 contract test |
| Bilibili | 0/3 | NOT VERIFIED | 公开 DASH 合并代码存在，需真实服务器资源验证 |
| 微博 | 0/3 | NOT VERIFIED | 公开元数据适配器存在 |
| 小红书 | 0/3 | NOT VERIFIED | 公开元数据适配器存在 |
| 抖音 | 0/3 | NOT VERIFIED | 公开元数据适配器存在 |
| 快手 | 0/3 | NOT VERIFIED | 允许返回 `PLATFORM_CHANGED` 合规降级 |

记录真实样例时只保存页面 URL、测试时间、结果码、媒体大小/时长摘要和 request_id，不保存 Cookie 或私密内容。
