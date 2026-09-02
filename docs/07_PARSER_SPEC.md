# Parser 规范

每个 Parser 实现 `can_handle(url)` 与 `parse(url, context)`，返回统一 `ParserResult`。策略依次为公开元数据、标准 HTML/JSON-LD/OpenGraph、正常公开网络请求、隔离的 yt-dlp；不可合规获取则失败。

禁止浏览器 Cookie、模拟登录、验证码、DRM、地域/年龄/付费绕过和来源不明第三方解析 API。

