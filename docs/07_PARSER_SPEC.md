# Parser 规范

每个 Parser 实现 `can_handle(url)` 与 `parse(url, context)`，返回统一 `ParserResult`。策略依次为公开元数据、标准 HTML/JSON-LD/OpenGraph、正常公开网络请求、隔离的 yt-dlp；不可合规获取则失败。

禁止浏览器 Cookie、模拟登录、验证码、DRM、地域/年龄/付费绕过和来源不明第三方解析 API。

yt-dlp 运行在受超时控制的独立子进程中，禁用第三方插件、用户 site-packages 与环境代理；子进程逐次校验 DNS 结果只能是公网 IP，并受文件、内存、CPU 和文件描述符限制。异常、取消和超时会终止整个子进程树，遗留临时目录由 TTL 清理任务补偿。工作进程禁止向 JSON 协议的标准输出写下载进度。

Bilibili 公开 DASH 在下载前读取各轨道的公开元数据和预计大小，只处理用户选择的原视频、720P 或 540P 档，优先选择 H.264 视频与 AAC 音频。公开视频与音频可在 2GiB 源文件暂存边界内分段下载并合并；成品超过 180MiB 时进入统一 FFmpeg 压缩管道，按时长计算码率并输出单个 H.264 + AAC MP4。最终分辨率和“自动压缩”状态必须如实展示。没有可公开访问的兼容源时明确返回受限或格式错误，不尝试 Cookie、登录或风控绕过。真实平台 smoke test未达到每平台 3 个公开样例前保持 `PARTIAL` 或 `NOT VERIFIED`。
