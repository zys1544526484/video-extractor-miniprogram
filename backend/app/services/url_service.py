from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from ..errors import AppError

URL_PATTERN = re.compile(r"https?://[^\s<>\u2e80-\u9fff]+", re.IGNORECASE)
TRAILING_PUNCTUATION = "。．，,；;：:！!？?、）)]}】》〉'\""

PLATFORM_DOMAINS = {
    "bilibili": {"bilibili.com", "b23.tv"},
    "weibo": {"weibo.com", "weibo.cn", "t.cn"},
    "xiaohongshu": {"xiaohongshu.com", "xhslink.com"},
    "douyin": {"douyin.com", "iesdouyin.com"},
    "kuaishou": {"kuaishou.com", "kuaishouapp.com", "gifshow.com", "kwai.com"},
}


def extract_first_http_url(text: str) -> str:
    for match in URL_PATTERN.finditer(text or ""):
        candidate = match.group(0).rstrip(TRAILING_PUNCTUATION)
        try:
            parsed = urlsplit(candidate)
        except ValueError:
            continue
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            normalized = parsed._replace(fragment="")
            return urlunsplit(normalized)
    raise AppError("URL_NOT_FOUND", "未识别到有效链接")


def host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def detect_platform(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").rstrip(".").lower()
    except ValueError as error:
        raise AppError("URL_INVALID", "链接格式无效") from error
    if not host:
        raise AppError("URL_INVALID", "链接缺少域名")
    for platform, domains in PLATFORM_DOMAINS.items():
        if any(host_matches(host, domain) for domain in domains):
            return platform
    return "generic"
