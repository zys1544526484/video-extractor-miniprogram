# 《微信视频提取小程序 Codex 全自动开发执行文档 V1.0》
> 本文件为便于一次性阅读/复制的合并版。实际交给 Codex 时，推荐保留分文件结构。


---

## 文件：`AGENTS.md`

# AGENTS.md — 微信视频提取小程序项目总指令

版本：V1.0  
目标：让 Codex 在尽量少人工干预的情况下，完成一个可运行、可测试、可部署、可提审的微信视频链接提取小程序。

## 1. 最高优先级工作规则

在修改任何代码前，必须先：

1. 读取本文件。
2. 读取 `docs/00_MASTER_EXECUTION.md`。
3. 根据当前任务读取对应规范文档。
4. 检查仓库当前状态，不得假设项目为空。
5. 如果已经存在实现，先判断“可复用 / 需修复 / 应替换”，禁止无理由推倒重写。
6. 先建立或更新 `STATUS.md`，记录当前阶段、已完成项、失败项、阻塞项。
7. 再开始开发。

## 2. 产品核心

产品只有一个核心闭环：

粘贴分享链接或分享文本  
→ 自动提取 URL  
→ 自动识别平台  
→ 检查 24 小时使用权限  
→ 未解锁时观看一次微信激励视频广告  
→ 完整观看后解锁 24 小时  
→ 后端解析公开可访问、用户有权保存的媒体  
→ 返回视频信息  
→ 小程序预览  
→ 用户主动点击“保存视频”  
→ 下载并保存到系统相册

首发目标平台：

- 抖音
- Bilibili
- 小红书
- 微博
- 快手
- 普通公开网页视频链接

## 3. 明确禁止擅自增加的功能

除非用户另行明确要求，不得增加：

- 会员体系
- 充值
- 卡密
- 积分
- 排行榜
- 社区
- 评论
- 私信
- 用户上传
- 云盘
- 长期视频存储
- AI 改写
- 视频剪辑
- 转码工具箱
- 批量下载
- 多账号系统
- 爬取用户私密内容
- 绕过登录、付费、地域、私密、审核、风控、DRM 或其他访问控制

“去水印”的产品定义必须是：
优先获取公开页面或合法接口中可获得的原始媒体源；若作者已经把水印烧录进画面，或平台只提供带水印的公开版本，不做画面修复、遮挡、擦除、破解或技术保护规避。

## 4. 技术栈

### 微信端
- 微信原生小程序
- WXML
- WXSS
- JavaScript
- 微信原生 API

禁止未经批准改为：
- uni-app
- Taro
- React
- Vue
- Flutter

### 后端
- Python 3.11+
- FastAPI
- Pydantic
- httpx
- pytest
- ruff
- SQLite（首发单机）
- SQLAlchemy 或轻量存储层（二选一，优先清晰、可迁移）
- 可选 yt-dlp：仅用于其合法支持的公开媒体解析
- 可选 ffmpeg：仅用于公开媒体的音视频合并/封装，不得用于绕过 DRM

## 5. 文档系统

把 `AGENTS.md` 当作目录和工程守则，不要把全部知识塞进本文件。

必须按需读取：

- `docs/00_MASTER_EXECUTION.md`：总执行方案
- `docs/01_PRODUCT_SPEC.md`：产品需求
- `docs/02_UI_SPEC.md`：页面与交互
- `docs/03_ARCHITECTURE.md`：总体架构
- `docs/04_API_SPEC.md`：接口契约
- `docs/05_IMPLEMENTATION_PLAN.md`：阶段计划
- `docs/06_AD_UNLOCK_SPEC.md`：广告与 24h 权限
- `docs/07_PARSER_SPEC.md`：解析器架构
- `docs/08_SECURITY_COMPLIANCE.md`：安全与合规
- `docs/09_TESTING_ACCEPTANCE.md`：测试与验收
- `docs/10_DEPLOYMENT_REVIEW.md`：部署与微信提审
- `docs/11_SELF_CORRECTION_PROTOCOL.md`：自检、自修复和阻塞规则

## 6. 自主执行原则

普通工程问题不要询问用户，必须自行处理，例如：

- 语法错误
- 依赖冲突
- 路径错误
- JSON 配置错误
- API 请求格式不一致
- 测试失败
- 导入失败
- 空值异常
- 超时处理
- 状态管理错误
- UI 小范围适配
- 重复代码
- 类型问题
- 资源引用错误

遇到这些问题：
诊断 → 修复 → 测试 → 再诊断，直到通过。

只有以下“硬阻塞”可以停止并询问用户：

- 需要真实微信小程序 AppID
- 需要 AppSecret
- 需要微信广告位 adUnitId
- 需要用户拥有的域名
- 需要服务器/云平台凭证
- 需要备案、主体或微信公众平台人工配置
- 需要真实第三方平台官方授权凭证
- 某目标平台在当前条件下只能通过绕过访问控制、DRM、登录、私密限制才能实现
- 官方平台规则或接口发生重大变化，且无法通过公开资料可靠判断
- 必须由用户作产品取舍

发生硬阻塞时，不要只说“做不了”。必须：
1. 写入 `BLOCKERS.md`；
2. 说明阻塞位置；
3. 说明已尝试的方法；
4. 给出用户最少需要提供的内容；
5. 继续完成其他不受影响的阶段。

## 7. 每次修改后的强制检查

每个阶段结束前必须至少执行：

### 后端
- `python -m compileall backend`
- `pytest`
- `ruff check backend tests`

如果仓库实际命令不同，以 README/pyproject 为准。

### 微信小程序
- 所有 JSON 可解析
- app.json 页面路径存在
- tabBar 路径存在
- JS 无明显语法错误
- 不存在引用缺失的本地资源
- 不存在无法到达的页面路径
- 不存在明显未处理 Promise/回调错误

如果 Node 可用，使用合适的语法检查；如果不可用，创建轻量验证脚本并执行。

### 安全
- 不得出现 AppSecret、数据库密码、真实广告位密钥被提交进仓库
- `.env` 必须在 `.gitignore`
- 代理接口不得成为任意 URL 开放代理
- 必须检查 SSRF
- 必须限制文件大小、连接时间、重定向次数和并发

## 8. 开发状态文件

仓库根目录长期维护：

- `STATUS.md`：当前进度
- `DECISIONS.md`：关键技术决策及原因
- `BLOCKERS.md`：硬阻塞
- `CHANGELOG.md`：重要变更

不得伪造“已测试”“已真机验证”“已上线”。

## 9. 完成定义

一个阶段只有同时满足以下条件才算完成：

- 对应代码存在
- 对应测试存在
- 自动化检查通过
- 与文档规范一致
- 无已知 P0/P1 缺陷
- STATUS.md 已更新

若不能满足，状态必须保持“进行中”或“阻塞”，不得标记完成。


---

## 文件：`docs/00_MASTER_EXECUTION.md`

# 微信视频提取小程序 Codex 全自动开发执行文档 V1.0

## 0. 文档目的

本项目不是让 Codex “一次生成所有代码后结束”，而是让其充当持续工作的主开发工程师：
自动识别仓库当前状态、读取规范、拆解任务、实现、测试、发现错误、修复错误、复验，直到阶段验收通过或遇到真正需要用户输入的硬阻塞。

Codex 的目标不是“代码量最大”，而是“最小可用闭环 + 可维护 + 可部署 + 可提审”。

---

## 1. 产品一句话定义

一个微信小程序，用户粘贴公开视频分享链接后，自动解析公开可访问的媒体资源，并允许用户预览和保存自己有权保存的视频、图片和标题文案；首版免费模式直接下载，未来可切换为完整观看激励视频广告后获得 24 小时下载权限。

---

## 2. 产品边界

### 必须实现
- 微信原生小程序
- 首页粘贴
- 自动从分享文案提取 URL
- 平台识别
- 24h 权限状态
- 微信激励视频广告解锁
- 解析进度和错误态
- 视频结果页
- 视频/图片/标题三个结果 Tab
- 多个真实视频源的安全切换
- 标题与分享文案复制
- 解析图片安全预览和保存
- 视频预览
- 保存视频到相册
- 教程
- FAQ
- 我的/权限状态页
- 后端解析服务
- 短时解析会话
- 安全下载/流媒体代理
- 服务端日志
- 基础限流
- 上线配置文档

### 首发平台
1. 抖音
2. 小红书
3. 快手
4. 微博
5. Bilibili
6. 普通公开网页

### 不做
- 不做付费会员
- 提取记录保留 24 小时，用于后台任务恢复和未下载结果再次打开；不做永久历史托管
- 不做用户收藏
- 不做账号密码
- 不做上传视频
- 不做批量下载
- 不做永久文件托管
- 不做去除作者烧录水印
- 不绕过 DRM
- 不绕过登录/付费/私密/审核/地区/年龄限制
- 不使用来历不明的第三方“万能解析 API”作为唯一核心依赖

---

## 3. 对“无水印/去水印”的工程定义

UI 和宣传用语应谨慎。

工程实现的优先级：
1. 平台或公开页面合法暴露的原始媒体源；
2. 公开页面中可解析的标准媒体资源；
3. 公开可访问但需要正常网络请求链路才能获得的媒体清单；
4. 如果只有平台水印版本可用，则返回该版本并明确提示；
5. 作者烧录在视频像素中的水印绝不做擦除或图像修复；
6. 不通过规避技术保护获得媒体。

因此 Parser 的职责是“找到公开媒体源”，不是“破解平台”。

---

## 4. 目标用户流程

首次进入：

首页
→ 粘贴分享文案
→ 开始提取
→ 解析中
→ 结果页
→ 选择视频源/查看图片/标题
→ 点击保存
→ 免费模式直接下载；`rewarded_ad` 模式此时才检查权限并在需要时观看广告
→ 下载进度
→ 保存成功

权限有效期间：

首页
→ 粘贴
→ 开始提取
→ 服务端确认仍在 24h 内
→ 直接解析
→ 结果
→ 保存

失败流程：
- 非法文本 → “未识别到有效链接”
- 未支持平台 → “暂不支持该链接”
- 私密/删除/付费 → “该内容不可公开访问”
- 平台结构变化 → “当前平台解析异常，请稍后再试”
- 视频过大 → 显示当前限制和建议
- 相册权限拒绝 → 引导用户去设置
- 网络断开 → 可重试，不重复消耗广告权益

---

## 5. 推荐仓库结构

```text
wechat-video-extractor/
├── AGENTS.md
├── README.md
├── STATUS.md
├── DECISIONS.md
├── BLOCKERS.md
├── CHANGELOG.md
├── .gitignore
├── docs/
├── miniprogram/
│   ├── app.js
│   ├── app.json
│   ├── app.wxss
│   ├── sitemap.json
│   ├── project.config.json.example
│   ├── pages/
│   │   ├── index/
│   │   ├── result/
│   │   ├── tutorial/
│   │   ├── faq/
│   │   └── mine/
│   ├── components/
│   │   ├── status-card/
│   │   ├── platform-badge/
│   │   └── progress-bar/
│   ├── services/
│   │   ├── api.js
│   │   ├── auth.js
│   │   ├── ad.js
│   │   └── download.js
│   ├── utils/
│   │   ├── config.js
│   │   ├── clipboard.js
│   │   ├── format.js
│   │   └── storage.js
│   └── assets/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── entitlement.py
│   │   │   ├── parse.py
│   │   │   ├── media.py
│   │   │   └── health.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── url_extractor.py
│   │   │   ├── platform_detector.py
│   │   │   ├── parse_service.py
│   │   │   ├── media_proxy.py
│   │   │   ├── entitlement_service.py
│   │   │   └── wechat_auth.py
│   │   ├── parsers/
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   ├── douyin.py
│   │   │   ├── xiaohongshu.py
│   │   │   ├── kuaishou.py
│   │   │   ├── weibo.py
│   │   │   ├── bilibili.py
│   │   │   └── generic.py
│   │   ├── security/
│   │   └── db/
│   ├── tests/
│   ├── pyproject.toml
│   ├── .env.example
│   └── Dockerfile
├── scripts/
│   ├── validate_miniprogram.py
│   └── smoke_test.py
└── deploy/
    ├── docker-compose.yml
    ├── Caddyfile.example
    └── DEPLOY_CHECKLIST.md
```

Codex 可以在不改变总体职责边界的前提下小幅调整结构，但必须在 `DECISIONS.md` 解释原因。

---

## 6. 关键设计原则

### 6.1 前端不承担平台解析
微信端只负责：
- 输入
- 状态
- 用户授权
- 广告
- 展示
- 下载和保存

平台 HTML/接口变化只能影响后端 Parser。

### 6.2 Parser 必须插件化
所有 Parser 使用统一接口和统一结果结构。
一个平台失效，不得导致其他平台不可用。

### 6.3 下载代理不得接受任意目标 URL
禁止设计：
`/download?url=https://任意地址`

必须设计为：
解析服务先创建 `parse_session_id` / `media_token`，
下载接口只接受服务端签发的短期 token，
服务端从受控会话中读取已验证媒体地址。

### 6.4 权限必须以服务端时间为准
客户端显示可以缓存，但最终权限判断由后端完成。

### 6.5 不长期存储媒体
普通情况使用流式代理。
若平台必须经过 ffmpeg 合并：
- 临时文件
- 随机会话目录
- 限时 TTL
- 自动删除
- 不进入数据库
- 不做永久归档

用户文案不得虚假写“绝不存储”，建议写：
“不会长期保存用户视频；部分内容为完成解析或合并可能产生短时缓存，并在任务结束或过期后自动清理。”

---

## 7. Codex 的总工作循环

每轮工作：

1. Inspect：读取仓库、STATUS、相关规范。
2. Plan：明确本轮要完成的 Phase 和验收条件。
3. Implement：最小范围实现。
4. Test：运行自动测试和静态检查。
5. Diagnose：失败则定位根因。
6. Repair：修复，不得用“跳过测试”掩盖。
7. Re-test：重复直到通过。
8. Review：对照验收标准做差异检查。
9. Security Review：涉及 URL、代理、文件、鉴权必须安全复核。
10. Update Docs：更新 STATUS/DECISIONS/CHANGELOG。
11. Continue：若无人工 Gate，可进入下一个 Phase。
12. Block：只有硬阻塞才写 BLOCKERS 并请求用户。

---

## 8. 人工 Gate

即使 Codex 可连续开发，也必须在以下位置标记“需要人工确认”，但不妨碍继续完成其他可并行事项：

### Gate A — UI
条件：Phase 03 完成。
用户需要用微信开发者工具看一次整体视觉。

### Gate B — 微信真实能力
条件：需要 AppID / adUnitId / 真机相册权限。
Codex 先完成 mock 和接口封装，待凭证补齐。

### Gate C — 第一个真实平台
条件：第一个 Parser 在公开测试 URL 上通过。
必须记录测试样例和结果，不得凭“代码看起来正确”判定。

### Gate D — 真机下载
至少 Android + iOS 各一次真实保存测试。

### Gate E — 提审
人工确认小程序类目、隐私指引、服务内容、备案、主体和广告资格。

---

## 9. 首发质量目标

- 首页可用时间 < 2 秒（不含网络慢环境）
- 解析请求有明确 loading
- 所有网络请求有超时
- 所有用户操作有明确结果反馈
- 错误不显示 Python traceback
- 后端错误有 request_id
- 媒体 token 短时有效
- 不存在任意 URL 代理
- 24h 权益不能仅靠本地时间修改
- 广告未完整观看不能解锁
- 同一用户重复点击不会无限创建解析任务
- 页面返回后状态不乱
- 服务端重启后权益仍可恢复（SQLite 持久化）
- 临时媒体能自动清理


---

## 文件：`docs/01_PRODUCT_SPEC.md`

# 01_PRODUCT_SPEC — 产品需求规格

## 1. 页面

### 首页
必须包含：
- 标题：视频提取
- 分享文本/URL 多行输入框
- 粘贴按钮
- 开始提取按钮
- 访问模式状态简洁提示（免费模式不展示广告文案）
- 使用教程
- 常见问题
- 权限说明
- 版权/存储说明
- 仅在 `rewarded_ad` 模式且配置真实广告单元时显示广告

不需要：
- 首页历史列表（记录入口放在任务/我的页面）
- 用户内容推荐
- 热门视频
- 搜索
- 信息流

### 结果页
必须包含：
- 视频、图片、标题三个 Tab
- 平台
- 标题
- 视频预览与源1/源2（按实际返回源数量展示）
- 图片预览与保存、无图片空状态
- 标题、分享文案、复制标题和复制全部
- 保存视频
- 重新提取
- 解析状态
- 保存进度
- 失败原因

### 教程页
7 步以内，说明：
分享 → 复制链接 → 返回 → 粘贴 → 开始提取 → 广告解锁（如需）→ 保存。

### FAQ
至少：
- 是否免费
- 为什么失败
- 为什么还有水印
- 为什么保存失败
- 保存到哪里
- 为什么需要广告
- 24 小时如何计算
- 是否保存我的视频

### 我的
只展示：
- 默认头像/应用名
- 当前权限状态
- 有效期
- 教程
- FAQ
- 隐私说明
- 联系/反馈入口（没有真实客服配置时不要伪造）
- 分享好友

---

## 2. 权限规则

- 未解锁：不能调用真实解析核心接口。
- 用户完整观看一次激励视频：从后端确认时间起增加/覆盖为 24h。
- 建议规则：`unlock_until = max(current_unlock_until, server_now) + 24h` 或 `server_now + 24h` 二选一。
- V1.0 默认采用 `server_now + 24h`，避免无限叠加。
- 权限有效期内不限“提取次数”，但受到合理限流保护。
- 广告加载失败不得扣除权益，也不得误解锁。
- 广告中途关闭不得解锁。
- 已解锁用户点击开始提取不得再次强制广告。

---

## 3. 解析结果结构

前端需要的最小字段：
- `session_id`
- `platform`
- `title`
- `cover_url`
- `media_type`
- `duration_seconds`（可空）
- `size_bytes`（可空）
- `quality_label`（可空）
- `preview_url`
- `download_url`
- `expires_at`
- `watermark_status`
- `notice`

V1.0 不要求多清晰度选择。
后端优先选取“质量合理且适合微信保存”的单一版本。

---

## 4. 用户提示原则

避免承诺：
- “100% 去水印”
- “全网都能下”
- “任何平台都能下”
- “绝不保存任何数据”
- “无限制”
- “永久免费永不变”

推荐：
- “支持常见公开视频链接”
- “仅处理公开可访问且你有权保存的内容”
- “作者已嵌入画面的水印不会被移除”
- “部分内容可能因平台限制、格式或文件大小无法保存”


---

## 文件：`docs/02_UI_SPEC.md`

# 02_UI_SPEC — 微信端 UI 与交互

## 1. 视觉基调

参考“简单工具型微信小程序”的信息密度和交互，不复制第三方产品的：
- 名称
- Logo
- 专属插画
- 具体广告素材
- 商标
- 独特视觉资产

主色：`#07C160`
背景：`#F7F8FA`
卡片：`#FFFFFF`
主文字：`#1F1F1F`
次文字：`#8A8A8A`
错误：使用系统警示色，不做夸张动画
圆角：16rpx–24rpx
阴影：极轻或不用

## 2. 首页布局

从上到下：

1. 导航栏
2. 可选广告区域/运营提示区
3. 轻提示条：“观看一次广告，24小时内可使用”
4. 输入区
5. 开始提取 + 粘贴
6. 版权/存储说明
7. 三个工具卡：
   - 使用教程
   - 常见问题
   - 我的权限
8. 底部 tab：首页 / 我的

输入区要求：
- 支持长文本
- 用户粘贴整段平台分享文案也能工作
- 粘贴后自动 trim
- 不自动提交，避免误触

## 3. 状态

首页主按钮至少有：
- idle：开始提取
- checking：检查权限…
- ad_required：弹窗，不直接改变按钮
- parsing：提取中…
- failed：恢复按钮，可重试

结果页：
- loading
- ready
- downloading
- saving
- success
- error

## 4. 广告交互

`rewarded_ad` 模式下未解锁时点击结果页保存：
弹窗：
标题：解锁 24 小时使用
正文：完整观看一次广告后，可在 24 小时内使用视频提取功能。
按钮：
- 观看广告
- 暂不

完整观看广告后：
- 不要求用户再次点击保存
- 自动继续此前选中的源的保存任务

广告加载失败：
“广告暂时加载失败，请稍后重试。”
不得伪装为用户错误。

## 5. 权限显示

首页/结果页：
- 未解锁：“观看广告可解锁 24 小时”
- 已解锁：“已解锁 · 剩余 12小时34分”
- 临近过期可显示到分钟
- 过期立即刷新为未解锁

我的：
- 当前权限
- 有效期至 YYYY-MM-DD HH:mm
- 使用服务器返回时间换算，不能以本机修改时间为最终依据

## 6. 保存体验

点击保存：
1. 检查当前选中源的结果 token 是否过期
2. 过期则重新解析，不强制重新看广告（若权益仍有效）
3. `wx.downloadFile`
4. 显示从 0% 到 100% 的进度
5. 请求/检查相册写入权限
6. 视频使用 `wx.saveVideoToPhotosAlbum`；图片使用 `wx.saveImageToPhotosAlbum`
7. 成功 toast/modal

相册权限拒绝：
给出明确操作：
“请在小程序设置中允许写入相册后重试。”

## 7. 响应式

至少适配：
- 常见 iPhone 宽度
- Android 360–430 CSS px 范围
- 刘海/灵动岛安全区
- 导航栏胶囊区域
- 字体放大一档时不严重溢出

禁止依赖固定截图像素定位。


---

## 文件：`docs/03_ARCHITECTURE.md`

# 03_ARCHITECTURE — 技术架构

## 1. 总体

微信小程序
→ HTTPS API
→ FastAPI
→ Auth / Entitlement / Parser Registry / Media Session
→ 平台 Adapter
→ 公共媒体源
→ 安全流式代理
→ 微信下载并保存

## 2. 认证

生产版使用：
`wx.login()` 获取临时 code
→ POST `/api/v1/auth/wechat`
→ 后端调用微信官方 code2session/jscode2session 能力
→ 得到 openid/session_key（session_key 不下发）
→ 后端创建自己的短期登录 token
→ 小程序保存 token

要求：
- AppSecret 只在服务器环境变量
- 不写入小程序
- 不提交 Git
- token 可轮换
- 401 时自动重新 wx.login 一次

## 3. 权益存储

表 `users`：
- id
- openid unique
- unlock_until nullable
- created_at
- updated_at

可增加 `ad_unlock_events` 用于审计：
- id
- user_id
- occurred_at
- source
- result

若微信广告没有服务器回调可直接确认观看完成，V1 可由客户端广告完成事件向后端申请解锁，但后端必须：
- 要求已登录
- 做频率限制
- 做幂等
- 记录事件
- 不信任客户端传入的 unlock_until
- 只由服务器计算 24h

## 4. 解析会话

表可不持久化，优先内存/TTL Cache；单机 V1 可用进程内 TTL + 签名 token。
若需要跨进程，迁移 Redis。

`ParseSession`：
- session_id
- user_id
- platform
- source_url
- resolved_media_url（只服务端）
- title
- cover
- expires_at
- allowed_hosts
- metadata

前端绝不能获得“可被当成任意代理参数”的未校验目标 URL。

## 5. 媒体代理

路径：
- `/api/v1/media/{token}/preview`
- `/api/v1/media/{token}/download`

要求：
- token 与当前用户/会话绑定或具有难猜的签名
- TTL
- 支持 Range（预览）
- 支持流式响应
- Content-Type 校验
- Content-Length 可用时提前检查
- 上游超时
- 重定向次数限制
- DNS/IP SSRF 检查
- 不能访问 localhost/内网/metadata IP
- 不允许 file:// ftp:// gopher:// 等协议

## 6. Bilibili 与音视频分离

如果公开媒体是 DASH：
- 允许使用 yt-dlp/ffmpeg 对公开视频进行正常格式合并
- 不使用浏览器 cookie 绕过登录/大会员/付费
- 输出 MP4（若编码兼容）
- 生成短时临时文件
- 返回 token
- TTL 清理
- 记录临时文件大小
- 超出服务端/微信端安全上限时拒绝并提示

## 7. 普通网页 Parser

只支持：
- 直接 MP4/WebM 等公开媒体 URL
- 标准 HTML `<video>` / `<source>`
- 公共 OpenGraph/JSON-LD 中媒体 URL
- 可公开读取的 HLS（若需要转封装则遵循限制）

不得执行任意页面 JS 作为默认行为。
不得通过浏览器自动化绕过验证码或登录。


---

## 文件：`docs/04_API_SPEC.md`

# 04_API_SPEC — API 契约

统一前缀：`/api/v1`

所有响应都包含：
- `request_id`
- `success`

错误格式：

```json
{
  "success": false,
  "request_id": "req_xxx",
  "error": {
    "code": "PARSE_UNSUPPORTED",
    "message": "暂不支持该链接",
    "retryable": false
  }
}
```

## 1. GET /health

返回服务状态和版本，不暴露密钥。

## 2. POST /auth/wechat

请求：
```json
{"code":"wx.login returned code"}
```

响应：
```json
{
  "success": true,
  "token": "app_session_token",
  "expires_in": 604800,
  "user": {
    "entitled": false,
    "unlock_until": null,
    "server_time": "..."
  }
}
```

## 3. GET /entitlement

Authorization: Bearer

响应：
```json
{
  "success": true,
  "entitled": true,
  "unlock_until": "2026-09-02T15:30:00+08:00",
  "server_time": "2026-09-01T16:00:00+08:00"
}
```

## 4. POST /entitlement/ad-complete

只在客户端收到“完整观看”事件后调用。

请求不要允许客户端传“加几小时”。

响应由服务器计算：
```json
{
  "success": true,
  "entitled": true,
  "unlock_until": "..."
}
```

必须幂等与限流。

## 5. POST /parse

请求：
```json
{
  "text": "用户粘贴的整段分享文本或URL"
}
```

后端流程：
1. 检查登录
2. 检查 entitlement
3. 提取 URL
4. 规范化
5. 识别平台
6. 选择 parser
7. 解析
8. 创建短期 media session
9. 返回前端安全 URL

成功：
```json
{
  "success": true,
  "request_id": "...",
  "result": {
    "session_id": "...",
    "platform": "douyin",
    "title": "...",
    "cover_url": "...",
    "media_type": "video",
    "duration_seconds": 42.3,
    "size_bytes": 12345678,
    "quality_label": "HD",
    "preview_url": "https://api.example.com/api/v1/media/<token>/preview",
    "download_url": "https://api.example.com/api/v1/media/<token>/download",
    "expires_at": "...",
    "watermark_status": "source_original",
    "notice": ""
  }
}
```

`watermark_status`：
- source_original
- platform_watermarked
- author_embedded
- unknown

## 6. GET /media/{token}/preview

支持 HTTP Range。
只允许受控会话解析出的上游地址。

## 7. GET /media/{token}/download

Content-Disposition attachment。
文件名服务端清洗：
`平台_标题_时间.mp4`

不得允许 CRLF 或目录穿越。

## 8. 错误码

至少：
- AUTH_REQUIRED
- AUTH_FAILED
- ENTITLEMENT_REQUIRED
- AD_CONFIRM_RATE_LIMITED
- URL_NOT_FOUND
- URL_INVALID
- PLATFORM_UNSUPPORTED
- CONTENT_NOT_PUBLIC
- CONTENT_REMOVED
- CONTENT_RESTRICTED
- PARSE_FAILED
- PARSE_TIMEOUT
- PLATFORM_CHANGED
- MEDIA_TOO_LARGE
- MEDIA_FORMAT_UNSUPPORTED
- MEDIA_SESSION_EXPIRED
- UPSTREAM_TIMEOUT
- DOWNLOAD_FAILED
- RATE_LIMITED
- INTERNAL_ERROR

前端根据 code 处理，不解析后端英文异常文本。


---

## 文件：`docs/05_IMPLEMENTATION_PLAN.md`

# 05_IMPLEMENTATION_PLAN — 全自动实施阶段

Codex 必须按阶段推进。允许一个工作回合连续完成多个阶段，但必须逐阶段验收并更新 STATUS。

## Phase 00 — 仓库体检
- 查现有文件
- 查 Git 状态
- 查现有 AGENTS
- 建 STATUS/DECISIONS/BLOCKERS/CHANGELOG
- 明确缺失依赖
验收：能准确描述当前仓库，不误删现有有效代码。

## Phase 01 — 微信小程序骨架
- app.js/app.json/app.wxss
- index/result/tutorial/faq/mine
- tabBar 首页/我的
- config 层
- 不接真实后端
验收：JSON/路径/资源校验通过。

## Phase 02 — 首页与辅助页 UI
- 首页输入、粘贴、主按钮
- 教程
- FAQ
- 我的
- 结果页 skeleton
验收：交互按钮可用，无死链。

## Phase 03 — 前端状态机
- idle/checking/parsing/error
- pendingInput
- result state
- toast/modal
- 页面返回状态
验收：使用 mock API 可完整模拟一次流程。
人工 Gate A。

## Phase 04 — 后端骨架
- FastAPI
- config
- request_id
- health
- 统一异常
- pytest/ruff
验收：测试通过，curl health 正常。

## Phase 05 — URL 提取与平台识别
覆盖：
- 整段中文分享文案
- 短链
- 参数
- 尾部标点
- 多 URL（明确取第一个合法候选）
- 非 http(s)
验收：单元测试覆盖所有目标平台域名常见形式。

## Phase 06 — 微信认证
- wx.login 前端
- 后端 code exchange
- 自有 token
- mock 模式
- 真实模式配置
验收：无凭证时 mock 可测；有凭证时准备真实测试。
硬阻塞：真实 AppID/AppSecret。

## Phase 07 — 权益系统
- SQLite
- user
- unlock_until
- GET entitlement
- server-time
- 幂等
验收：修改客户端时间不能影响服务器最终判定。

## Phase 08 — 激励视频广告封装
- RewardedVideoAd service
- 加载
- show
- onClose
- onError
- 完整观看才调用 ad-complete
- mock ad mode
验收：中途关闭不解锁；完成后自动继续 pending parse。
硬阻塞：真实 adUnitId。
人工 Gate B。

## Phase 09 — Parser 基础设施
- BaseParser
- ParserResult
- ParserRegistry
- timeout
- common http client
- redirect policy
- UA policy
- normalized errors
验收：FakeParser 集成测试通过。

## Phase 10 — Generic Parser
支持公开标准网页：
- 直接媒体 URL
- video/source
- OpenGraph/JSON-LD 媒体
验收：自建测试 fixture，不依赖不稳定外网也能测试。

## Phase 11 — 第一个真实平台 Parser
优先选择当前公开网页结构最稳定、无需登录即可验证的平台。
Codex 应先调查最新公开情况再选择，不要机械固定顺序。
实现：
- 公开 URL
- 标准请求
- 规范化错误
- 真实样例 smoke test（如果网络允许）
验收：至少 3 个公开样例或明确说明网络测试限制。
人工 Gate C。

## Phase 12 — 抖音
只处理公开作品。
不得绕过登录、风控、验证码。
优先官方/公开页面可用数据；如使用 yt-dlp，封装隔离。
验收：成功、删除、私密/限制、错误链接各一类。

## Phase 13 — 小红书
同上。

## Phase 14 — 快手
同上。

## Phase 15 — 微博
同上。

## Phase 16 — Bilibili
- 公开视频
- DASH 可用时正常音视频合并
- 不使用用户 cookie 绕过权限
- ffmpeg 临时文件 TTL
验收：普通公开视频；不可访问内容友好失败。

## Phase 17 — Media Session 与安全 Proxy
- token
- TTL
- preview
- download
- Range
- SSRF
- host/IP 检查
验收：不能代理 `127.0.0.1`、内网、metadata 地址、任意 URL。

## Phase 18 — 结果页真实接入
- title
- cover
- video
- error state
- token expiry
验收：Mock + 真实 parser 都能渲染。

## Phase 19 — 下载与保存
- wx.downloadFile
- progress
- saveVideoToPhotosAlbum
- 权限拒绝处理
- 下载失败重试
验收：开发工具 mock + 真机 checklist。
人工 Gate D。

## Phase 20 — 临时文件清理与限额
- TTL janitor
- 最大文件
- 最大任务时间
- 并发限制
- 磁盘空间保护
验收：过期文件删除，异常退出有补偿清理。

## Phase 21 — 安全加固
执行 `08_SECURITY_COMPLIANCE.md` 全项。
验收：安全测试通过，无开放代理。

## Phase 22 — 可观测性
- request_id
- 结构化日志
- parser latency
- error code
- 不记录 AppSecret/session_key
- 对分享 URL 做适度脱敏
验收：故障能定位到 parser 和 request_id。

## Phase 23 — Docker 部署
- Dockerfile
- compose
- reverse proxy
- HTTPS 配置样例
- env example
- healthcheck
验收：本机 docker 可启动（环境支持时）。

## Phase 24 — 微信生产配置文档
- request/download 合法域名
- HTTPS
- AppID
- 隐私
- 相册写入权限用途
- 广告位
- 类目/内容说明
- 备案/主体由用户确认
验收：形成 deploy checklist。
人工 Gate E。

## Phase 25 — 回归测试
完整路径：
未登录 → 登录 → 粘贴 → 解析 → 结果（视频/图片/标题）→ 选择源 → 保存；`rewarded_ad` 模式仅在保存时未解锁才看广告。
然后：
权限有效 → 第二次解析不看广告。
再测试所有错误态。
验收：自动测试 + 人工清单无 P0/P1。

## Phase 26 — Release Candidate
- VERSION
- CHANGELOG
- README
- 配置模板
- 生产变量清单
- 已知限制
- BLOCKERS 清零或明确
最终输出：
“可提审 / 不可提审”二选一，必须附原因。


---

## 文件：`docs/06_AD_UNLOCK_SPEC.md`

# 06_AD_UNLOCK_SPEC — 激励广告与 24 小时权限

## 1. 原则

广告是“解锁入口”，不是每次解析前置广告。
完整观看一次 → 24 小时内可使用解析。

## 2. 前端封装

建议 `services/ad.js` 提供：

- `initRewardedAd()`
- `showRewardedAd() -> Promise<{completed:boolean}>`
- `destroyRewardedAd()`

不得把广告业务逻辑散落多个页面。

## 3. 广告完成判断

Codex 在实现时必须查询当前微信官方小程序文档，确认：
- createRewardedVideoAd 当前 API
- onClose 返回结构
- 基础库兼容要求
- show/load 行为
- adUnitId 配置要求

不得凭旧博客复制过时代码。

## 4. 解锁

广告完成事件后：
POST `/entitlement/ad-complete`

服务器：
- 使用服务器当前时间
- 设置 `unlock_until = now + 24h`
- 不采用客户端传时间
- 返回 server_time 和 unlock_until

## 5. 防滥用

V1 不需要复杂反作弊，但至少：
- 已解锁用户不允许频繁触发 ad-complete 来无限续期
- 同一用户短时间大量调用限流
- 幂等键/时间窗口
- 记录异常频率
- 不允许匿名调用

## 6. 广告不可用

若用户账号/地区/广告位暂无填充：
- 不得自动“假装看完”
- 开发模式可通过明确的 MOCK_AD=true 模拟
- 生产模式不得开启 mock
- 给用户提示“广告暂时不可用，请稍后重试”

是否提供其他免费解锁方式属于产品决策，V1 不擅自增加。


---

## 文件：`docs/07_PARSER_SPEC.md`

# 07_PARSER_SPEC — 多平台解析器规范

## 1. BaseParser

统一接口概念：

```python
class BaseParser(ABC):
    platform: Platform

    @abstractmethod
    async def can_handle(self, url: str) -> bool: ...

    @abstractmethod
    async def parse(self, url: str, context: ParseContext) -> ParserResult: ...
```

ParserResult：
- platform
- canonical_url
- title
- cover_url
- media_type
- upstream_media_url 或 temporary_file
- mime_type
- duration
- size
- quality
- watermark_status
- required_headers（若公开媒体上游要求常规 Referer/UA）
- expires_at
- notices

## 2. 解析策略优先级

1. 平台官方公开能力/页面公开元数据
2. 公开 HTML / JSON-LD / OpenGraph
3. 公开页面正常网络请求可获得的数据
4. 稳定开源解析器（例如 yt-dlp）作为隔离依赖
5. 无法在不绕过限制的情况下获得 → 失败

禁止：
- 导入用户浏览器 cookie 以访问私密/付费内容
- 模拟登录绕过权限
- 验证码绕过
- DRM 破解
- 注入/执行不可信页面脚本以规避限制
- 购买/调用来源不明“去水印 API”作为黑盒核心
- 将第三方签名绕过代码直接散落业务层

## 3. 平台变化处理

任何 parser 真实样例持续失败时：
- 先判断平台变化 vs 网络问题
- 记录 `PLATFORM_CHANGED`
- 该 parser 熔断一定时间，避免打爆上游
- 不影响其他 parser
- STATUS 标记 degraded
- 更新 fixture/tests 后修复

## 4. 短链

短链可跟随有限次重定向：
- 仅 http/https
- 每次 redirect 都重新做 SSRF 检查
- 最大重定向次数配置化
- 最终 URL 再判断平台

## 5. yt-dlp 使用规则

允许将 yt-dlp 封装为一个可替换 adapter，用于其支持的公开媒体。
要求：
- 固定最低版本策略
- 捕获稳定错误类型
- 禁止直接把完整 stderr 返回用户
- 不依赖用户 cookie
- 不开启绕过地域/年龄/登录的选项
- 版本升级要跑 parser 回归测试

## 6. ffmpeg

仅：
- 容器重封装
- 公开视频音视频合并
- 格式兼容处理

禁止：
- DRM 解密
- 擦除作者水印
- 修改画面以隐藏标识

## 7. 普通网页

GenericParser 要严防 SSRF。
用户输入 URL 不能因为“普通网页”就获得服务器任意网络访问能力。


---

## 文件：`docs/08_SECURITY_COMPLIANCE.md`

# 08_SECURITY_COMPLIANCE — 安全、隐私与合规

## 1. SSRF（P0）

必须拦截：
- localhost
- 127.0.0.0/8
- 10.0.0.0/8
- 172.16.0.0/12
- 192.168.0.0/16
- link-local
- IPv6 loopback / unique-local / link-local
- 云 metadata 地址
- 非 http/https
- DNS rebinding 风险

DNS 解析后检查 IP；重定向后重新检查。

## 2. 开放代理（P0）

绝不允许：
`GET /proxy?url=<user-input>`

代理只能引用服务端已经解析、验证、绑定 TTL 的 media token。

## 3. 文件安全

- 临时目录使用随机 ID
- 无用户控制路径
- 文件名 sanitize
- 最大文件大小
- 最大临时磁盘占用
- 任务结束删除
- 后台 janitor 删除过期残留
- 下载 Content-Type 白名单/合理检查

## 4. 密钥

环境变量：
- WECHAT_APP_ID
- WECHAT_APP_SECRET
- APP_TOKEN_SECRET
- DATABASE_URL
- AD_UNIT_ID（前端配置中的广告位 ID 不等同 AppSecret，但仍区分开发/生产）

`.env` 不提交。
日志不得出现：
- AppSecret
- session_key
- 完整 Authorization
- 数据库密码

## 5. 日志隐私

默认不长期记录完整分享 URL。
可以记录：
- platform
- hostname
- hash/correlation id
- error code
- latency
- bytes
- request_id

需要调试完整 URL 时仅在显式 DEBUG 环境短期启用，并写清风险。

## 6. 用户数据

最小化：
- openid（后端必要）
- unlock_until
- 必要审计时间
- 不获取昵称头像手机号，除非未来产品需求明确需要

## 7. 媒体存储声明

如果存在临时合并/缓存，隐私文案必须真实披露“短时处理缓存并自动删除”，不能写绝对“不存储任何文件”。

## 8. 版权与访问控制

仅处理：
- 公开可访问
- 用户有权保存
- 无需绕过技术保护

错误态必须能区分“不可访问”而不是尝试不断规避。

## 9. 依赖安全

- 锁定依赖版本或合理范围
- 定期升级
- 不从未知脚本一键 curl|bash
- 不引入来源不明二进制
- ffmpeg 使用可信发行包
- yt-dlp 来源必须可靠

## 10. 微信审核

Codex 只能准备代码和 checklist，不能声称一定通过审核。
提交前人工核对：
- 小程序服务类目
- 业务资质
- 隐私保护指引
- 相册写入权限用途
- 广告能力资格
- 域名备案/HTTPS
- 用户协议/版权说明
- 平台最新审核要求


---

## 文件：`docs/09_TESTING_ACCEPTANCE.md`

# 09_TESTING_ACCEPTANCE — 测试和验收

## 1. 后端单元测试

### URL extractor
- 纯 URL
- 中文分享文案
- 前后换行
- 中文标点
- query 参数
- 多 URL
- 无 URL
- javascript/file/ftp 拒绝

### platform detector
每个平台：
- 主域
- 短链常见域
- 子域
- 伪造域名（如 douyin.com.attacker.com）不能误判

### entitlement
- 未解锁
- 正好过期
- 有效
- server time
- 重复 ad-complete
- 客户端时间无影响

### media security
- 127.0.0.1
- 内网
- IPv6 本地
- metadata
- redirect 到内网
- 超大文件
- 超时
- token 过期
- token 篡改

## 2. Parser contract tests

每个 Parser 必须通过统一 contract：
- 返回统一模型
- timeout 可控
- 不抛裸异常到 API
- 无法访问时返回规范错误
- 不修改其他 parser 状态

真实平台 smoke test 单独标记，可因 CI 无网络而跳过，但必须：
- 明确 skip 原因
- 不能把“没跑”写成“通过”

## 3. 前端验收

首页：
- 粘贴
- 空输入
- 长分享文案
- 网络错误
- 重复点击防抖

广告：
- 加载失败
- 用户中途关闭
- 完整观看
- 已解锁不重复广告
- 广告结束自动继续解析

结果：
- 标题过长
- 无封面
- token 过期
- 视频加载失败
- 下载进度
- 保存成功
- 相册权限拒绝

## 4. E2E 核心用例

E2E-01 首次用户：
登录 → 粘贴 → 开始 → 解析 → 结果 → 选择源 → 保存；必要时广告 → 完整观看 → 解锁 → 下载 → 保存。

E2E-02 24h 内：
再次打开 → 粘贴 → 直接解析，不看广告。

E2E-03 广告未看完：
关闭 → 不解锁 → 不解析。

E2E-04 不可访问内容：
友好提示，不重试绕过。

E2E-05 token 过期：
提示重新提取；权益有效时不重新广告。

## 5. 缺陷等级

P0：
- SSRF
- 任意代理
- 密钥泄露
- 广告没看完仍解锁
- 保存错文件/越权下载
- 小程序完全无法启动

P1：
- 核心平台全部无法解析
- 权益判断错误
- 真机无法保存
- 临时文件不清理造成磁盘风险

P2：
- 单平台结构变化
- UI 局部错位
- 个别提示不准确

Release Candidate 不允许存在已知 P0/P1。


---

## 文件：`docs/10_DEPLOYMENT_REVIEW.md`

# 10_DEPLOYMENT_REVIEW — 部署与微信提审

## 1. 推荐首发部署

单机 Docker：
- Caddy/Nginx
- FastAPI
- SQLite volume
- tmp media volume（带容量限制）
- HTTPS

如果流量增长：
- PostgreSQL
- Redis TTL sessions
- 对象存储/受控临时文件
- 多实例
这些不是 V1 强制项。

## 2. 域名

建议统一：
`api.example.com`

同时承载：
- API
- preview
- download

减少微信后台需要配置的域名数量。

Codex 在最终生产前必须查询微信官方最新文档，确认：
- request 合法域名
- downloadFile 合法域名
- video 媒体请求限制
- HTTPS/证书
- 域名备案和主体要求

不得只依赖旧博客。

## 3. 环境变量

`.env.example`：
- APP_ENV
- API_BASE_URL
- WECHAT_APP_ID
- WECHAT_APP_SECRET
- APP_TOKEN_SECRET
- DATABASE_URL
- MAX_VIDEO_BYTES
- PARSE_TIMEOUT_SECONDS
- MEDIA_SESSION_TTL_SECONDS
- TEMP_FILE_TTL_SECONDS
- MAX_REDIRECTS
- MOCK_WECHAT_AUTH
- MOCK_REWARDED_AD

生产：
- MOCK_* 必须 false

## 4. 上线前真实测试

至少：
- 微信开发者工具
- Android 真机
- iOS 真机
- 4G/5G
- Wi-Fi
- 相册权限首次拒绝后再开启
- 视频 10MB / 50MB / 接近配置上限
- 目标平台各至少 2 个公开内容
- 权益跨重启

## 5. 提审材料建议

准备：
- 功能说明
- 使用教程
- 隐私政策
- 用户协议
- 版权/授权提示
- 临时缓存说明
- 联系方式
- 测试账号若平台要求（本项目通常无账号密码）
- 小程序类目/资质材料
- 广告位配置

## 6. 发布判断

Codex 最终输出 `RELEASE_READINESS.md`：

必须列：
- Build：PASS/FAIL
- Backend tests
- Security tests
- Mini Program validation
- Real-device Android
- Real-device iOS
- Ads real test
- Real WeChat auth
- Production domain
- Parser status by platform
- Privacy checklist
- Known limitations

任何未真实验证项必须写 `NOT VERIFIED`，不得写 PASS。


---

## 文件：`docs/11_SELF_CORRECTION_PROTOCOL.md`

# 11_SELF_CORRECTION_PROTOCOL — Codex 自我识别、自检、自修复协议

这是本项目最重要的自主开发规则之一。

## 1. 不允许的行为

Codex 不得：
- 因第一次测试失败就停止
- 把 failing test 删除掉来“变绿”
- 用 try/except: pass 隐藏错误
- 把真实功能替换成永久 mock 却声称完成
- 遇到平台解析失败就自动改用不透明第三方 API
- 将安全检查关闭来让测试通过
- 因一个平台失败而重写所有架构
- 未运行命令就声称测试通过
- 未真机测试就声称“保存功能已验证”
- 未部署就声称“已上线”

## 2. 失败分类

每次失败先分类：

A. 代码缺陷
→ 自行修复

B. 测试/fixture 缺陷
→ 证明测试本身错误后修测试；不能只因实现失败就改预期

C. 环境缺陷
→ 修开发环境/依赖/脚本

D. 外部平台变化
→ 隔离 parser、更新 adapter、标记 degraded

E. 缺凭证
→ 写 BLOCKERS，同时完成 mock/其余任务

F. 合规/技术边界
→ 停止该路径，不尝试绕过；给出合法替代方案

## 3. 自修复循环

最多不要机械限定“3次”，而是：
只要仍有新的诊断信息且修复合理，就继续。

标准循环：

```
observe failure
→ capture command/output
→ locate smallest root cause
→ inspect related code/docs
→ make minimal fix
→ run focused test
→ run full relevant suite
→ regression review
```

如果连续多轮没有新信息：
- 停止盲改
- 回退到最后已知良好状态
- 写出假设清单
- 做最小实验
- 若仍无法判定再列 BLOCKER

## 4. 架构自检

每完成 3–5 个 Phase，执行一次：
- 有没有业务逻辑泄漏到页面
- parser 是否相互耦合
- API schema 是否漂移
- 错误码是否重复/不一致
- 安全代理是否可被绕过
- 配置是否硬编码
- 测试是否依赖真实平台过多
- 是否出现无用功能膨胀

发现技术债：
写 `DECISIONS.md` / `STATUS.md`，在不扩大需求的前提下修复。

## 5. 平台解析自检

如果某平台突然失败：
1. 确认 URL 仍公开可访问；
2. 确认不是网络/DNS/证书；
3. 确认不是短链重定向；
4. 确认页面/元数据结构是否变化；
5. 检查依赖解析器版本；
6. 更新 fixture；
7. 最小修复 adapter；
8. 回归该平台；
9. 回归其他平台。

绝不从“解析失败”直接跳到“绕过验证码/登录”。

## 6. 交付自检模板

每阶段结束必须回答：

- 我改了什么？
- 为什么这样改？
- 哪些文件受影响？
- 运行了哪些测试？
- 哪些测试通过？
- 哪些未运行，为什么？
- 是否有安全影响？
- 是否有兼容性影响？
- 是否需要用户提供外部信息？
- STATUS 是否更新？

只有答案完整，阶段才可结束。


---

## 文件：`prompts/START_HERE.md`

# 给 Codex 的启动指令

将整个文档包放进项目根目录后，对 Codex 发送：

---

请把当前仓库视为一个长期软件工程项目。

首先完整阅读根目录 `AGENTS.md` 和 `docs/00_MASTER_EXECUTION.md`，然后根据其中要求按需读取其他 docs。

你的职责不是只回答我“应该怎么做”，而是直接检查当前仓库并执行开发。

请先执行 Phase 00 仓库体检，创建或更新 STATUS.md、DECISIONS.md、BLOCKERS.md、CHANGELOG.md，然后从当前实际进度开始，严格按照 `docs/05_IMPLEMENTATION_PLAN.md` 逐阶段实施。

工作要求：

1. 不要假设仓库为空，先识别已有代码。
2. 不要重复实现已经正确完成的功能。
3. 发现普通代码错误、测试错误、配置错误、依赖问题时自行诊断和修复，不要因为普通工程问题停下来问我。
4. 每个 Phase 完成后运行对应测试；失败则继续修复直到通过。
5. 不得通过删除测试、关闭安全检查、永久使用 mock 等方式伪造完成。
6. 只有需要真实 AppID、AppSecret、adUnitId、服务器/域名凭证、微信后台人工配置，或遇到无法在合规边界内实现的平台限制时，才作为硬阻塞写入 BLOCKERS.md 并向我询问。
7. 遇到硬阻塞时继续完成所有不受影响的任务。
8. 不要绕过 DRM、登录、付费、私密、审核、验证码或其他访问控制。
9. “无水印”只表示优先获取公开可访问的原始媒体源；作者已嵌入画面的水印不处理。
10. 所有“已通过”“已验证”“已部署”必须有实际测试或环境证据，不能推测。

现在先输出：
- 你识别到的仓库现状
- 当前应从哪个 Phase 开始
- 预计本轮可完成哪些 Phase
- 当前已知硬阻塞

然后立即开始执行，不需要等待我再次确认。
