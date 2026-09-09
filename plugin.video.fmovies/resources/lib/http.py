"""Shared HTTP helpers: session factory, decoding, soup fetching."""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
)

HTML_HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept': ('text/html,application/xhtml+xml,application/xml;q=0.9,'
               'image/avif,image/webp,image/apng,*/*;q=0.8'),
    'Accept-Language': 'en-US,en;q=0.9',
}

GENERIC_HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept': '*/*',
}

DEFAULT_TIMEOUT = 12


def make_session(headers: dict | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update(GENERIC_HEADERS)
    if headers:
        session.headers.update(headers)
    return session


def decode_html(response) -> str:
    """Decode response bytes as UTF-8.

    requests falls back to ISO-8859-1 for text/html without an explicit
    charset, which mangles names like 'Chloé' into 'ChloÃ©'.
    """
    content = getattr(response, 'content', None)
    if isinstance(content, (bytes, bytearray)):
        try:
            content_type = response.headers.get('content-type', '') or ''
        except Exception:
            content_type = ''
        if not isinstance(content_type, str):
            content_type = ''
        if 'charset' not in content_type.lower():
            try:
                return bytes(content).decode('utf-8')
            except UnicodeDecodeError:
                pass
    text = getattr(response, 'text', '')
    return text if isinstance(text, str) else ''


def fetch_soup(session: requests.Session, url: str,
               timeout: int = DEFAULT_TIMEOUT) -> BeautifulSoup:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return BeautifulSoup(decode_html(response), 'html.parser')


def normalize_base_url(raw: str | None,
                       fallback: str = 'https://fmoviess.org') -> str:
    return (raw or '').rstrip('/') or fallback
