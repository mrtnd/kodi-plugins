"""p2pbg.com tracker client: login (CSRF), search, details, .torrent fetch."""
from __future__ import annotations

import re
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
)

# Video categories worth searching by default (Movies HD/4K/SD/BG + TV/TV BG).
DEFAULT_CATEGORIES = '68;60;67;34;14;24'

HEX_ID = re.compile(r'/torrents/([a-f0-9]{40})')


class AuthError(Exception):
    pass


class P2PBGClient:
    def __init__(self, base_url='https://www.p2pbg.com', username='',
                 password=''):
        self.base_url = (base_url or '').rstrip('/') or 'https://www.p2pbg.com'
        self.username = username or ''
        self.password = password or ''
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': USER_AGENT})
        self._logged_in = False

    # -- auth ---------------------------------------------------------
    def login(self):
        """Login with CSRF token; raises AuthError on failure."""
        if not self.username or not self.password:
            raise AuthError('tracker username/password are not configured')
        page = self.session.get(self.base_url + '/login', timeout=12)
        page.raise_for_status()
        token = re.search(r'name="_token" value="([^"]+)"', page.text)
        if not token:
            raise AuthError('login form token not found (site changed?)')
        res = self.session.post(
            self.base_url + '/login', timeout=12,
            data={'_token': token.group(1), 'returnto': '',
                  'uid': self.username, 'pwd': self.password,
                  'remember': '1'},
            headers={'Referer': self.base_url + '/login'},
            allow_redirects=True)
        res.raise_for_status()
        if '/logout' not in res.text and 'logout' not in res.text.lower():
            raise AuthError('login failed (check username/password)')
        self._logged_in = True

    def _get(self, url, **kwargs):
        """GET with one transparent re-login on session expiry."""
        res = self.session.get(url, timeout=12, **kwargs)
        if self._looks_logged_out(res):
            self._logged_in = False
            self.login()
            res = self.session.get(url, timeout=12, **kwargs)
        res.raise_for_status()
        return res

    @staticmethod
    def _looks_logged_out(response) -> bool:
        url = getattr(response, 'url', '') or ''
        if '/login' in url:
            return True
        text = getattr(response, 'text', '') or ''
        return 'name="pwd"' in text and 'name="uid"' in text

    # -- search -------------------------------------------------------
    def search(self, query, categories=DEFAULT_CATEGORIES, active='1',
               bgaudio=False):
        params = {'search': query, 'category': categories, 'active': active}
        if bgaudio:
            params['bgaudio'] = '1'
        res = self._get(self.base_url + '/torrents?' + urlencode(params))
        return parse_search_rows(res.text, self.base_url)

    # -- details + download -------------------------------------------
    def details(self, tid):
        res = self._get('{}/torrents/{}'.format(self.base_url, tid))
        return parse_details(res.text, self.base_url, tid)

    def download_torrent(self, url):
        res = self._get(urljoin(self.base_url, url))
        data = res.content
        if not data.startswith(b'd'):
            raise ValueError('response is not a torrent file')
        return data


def parse_search_rows(html_page, base_url):
    """Rows from the listing table: id, title, date, size, S/L/D, details url."""
    soup = BeautifulSoup(html_page, 'html.parser')
    table = None
    for candidate in soup.select('table'):
        heads = [th.get_text(strip=True) for th in candidate.select('thead th')]
        if any('Размер' in h for h in heads) and any(h == 'S' for h in heads):
            table = candidate
            break
    if table is None:
        return []
    items = []
    for tr in table.select('tbody tr'):
        # Direct cells only: the layout nests tables for side blocks.
        cells = tr.find_all('td', recursive=False)
        link = None
        for cell in cells:
            link = cell.select_one('a[href*="/torrents/"]')
            if link:
                break
        if not link:
            continue
        match = HEX_ID.search(link.get('href', ''))
        if not match:
            continue
        texts = [c.get_text(' ', strip=True) for c in cells]
        size_idx = next(
            (i for i, t in enumerate(texts)
             if re.fullmatch(r'[\d.,]+\s*(GB|MB|KB|B)', t, re.IGNORECASE)),
            None)
        if size_idx is None:
            continue
        # Seeders/leechers/snatched are the last three numeric (or '---')
        # cells after the size cell; comment counts may precede them.
        tail = [t for t in texts[size_idx + 1:]
                if t == '---' or re.fullmatch(r'[\d.,]+', t)]
        seeders = _to_int(tail[-3]) if len(tail) > 2 else 0
        leechers = _to_int(tail[-2]) if len(tail) > 2 else 0
        snatched = _to_int(tail[-1]) if len(tail) > 2 else 0
        date = ''
        for t in texts[:size_idx]:
            if re.fullmatch(r'\d{2}/\d{2}/(\d{2}|\d{4})', t) or t == 'Вчера':
                date = t
        items.append({
            'id': match.group(1),
            'title': link.get_text(' ', strip=True),
            'url': urljoin(base_url, '/torrents/' + match.group(1)),
            'date': date,
            'size': texts[size_idx],
            'seeders': seeders,
            'leechers': leechers,
            'snatched': snatched,
        })
    return items


def parse_details(html_page, base_url, tid):
    """Details page: title, .torrent url, info hash, files, stats."""
    soup = BeautifulSoup(html_page, 'html.parser')
    title_el = soup.select_one('h1')
    title = title_el.get_text(' ', strip=True) if title_el else tid
    dl = soup.select_one('a[href*="download.php"]')
    torrent_url = (urljoin(base_url, dl['href'].replace('&amp;', '&'))
                   if dl and dl.get('href') else '')
    info_hash = ''
    hash_el = soup.select_one('.torrent-show__info-hash, [class*="info-hash"]')
    if hash_el:
        match = re.search(r'[a-f0-9]{40}', hash_el.get_text())
        if match:
            info_hash = match.group(0)
    files = []
    for row in soup.select('.torrent-show__file-row'):
        name_el = row.select_one('.torrent-show__file-name')
        size_el = row.select_one('.torrent-show__file-size')
        files.append({
            'name': name_el.get_text(' ', strip=True) if name_el else '',
            'size': size_el.get_text(' ', strip=True) if size_el else '',
        })
    return {'id': tid, 'title': title, 'torrent_url': torrent_url,
            'info_hash': info_hash, 'files': files}


def _to_int(text):
    try:
        return int(text.replace('.', '').replace(',', ''))
    except (TypeError, ValueError):
        return 0


def rank_items(items, min_seeders=1, prefer_bgaudio=True):
    """Filter by seeders; Bulgarian-audio markers first, then most seeders."""
    out = [it for it in items if it.get('seeders', 0) >= min_seeders]
    if prefer_bgaudio:
        out.sort(key=lambda it: (
            0 if re.search(r'\bbg\b|bgaudio|бг', it.get('title', ''),
                           re.IGNORECASE) else 1,
            -it.get('seeders', 0)))
    else:
        out.sort(key=lambda it: -it.get('seeders', 0))
    return out


def build_magnet(info_hash, name, announce, file_index=None):
    """Private-tracker magnet: info-hash + tracker announce only (no DHT leak)."""
    from urllib.parse import quote
    parts = ['xt=urn:btih:{}'.format(info_hash), 'dn={}'.format(quote(name))]
    if announce:
        parts.append('tr={}'.format(quote(announce, safe='')))
    magnet = 'magnet:?' + '&'.join(parts)
    return magnet, file_index
