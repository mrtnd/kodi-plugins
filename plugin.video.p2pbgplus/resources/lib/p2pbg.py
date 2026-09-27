"""p2pbg.com tracker client: login (CSRF), search, details, .torrent fetch."""
from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
)

# Video categories worth searching by default (Movies HD/4K/SD/BG + TV/TV BG).
DEFAULT_CATEGORIES = '68;60;67;34;14;24'

# Browse folders (Bulgarian labels, incl. sports added after user feedback).
CATEGORIES = [
    ('60', 'Филми 4K'),
    ('68', 'Филми HD'),
    ('67', 'Филми SD'),
    ('59', 'Филми VHS'),
    ('11', 'Филми DVD-R'),
    ('69', 'Филми Pack'),
    ('34', 'Български Филми'),
    ('24', 'Български Сериали'),
    ('14;15', 'Сериали'),
    ('38', 'Анимации'),
    ('7', 'Документални'),
    ('64', 'Футбол'),
    ('5', 'Формула 1'),
    ('57', 'Формула 2'),
]

SUBS_FLAGS = ('subs.gif', 'torrent-flag-subs-in-torrent.png',
              'torrent-flag-external-subs.png', 'torrent-flag-subs-in-video.png')
BGAUDIO_FLAGS = ('bgaudio.gif', 'torrent-flag-bg-audio.png')

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

    def fetch(self, url):
        """Authenticated GET returning text (re-login once on expiry)."""
        return self._get(url).text

    # -- search -------------------------------------------------------
    def _listing_url(self, query=None, categories=DEFAULT_CATEGORIES,
                     active='1', bgaudio=False, show_xxx=False):
        """Query string built exactly like the site's own form: literal
        ';' category separators and raw spaces (NOT urlencode, which turns
        ';' into %3B and spaces into '+' and the site then ignores filters).
        """
        from urllib.parse import quote_plus
        parts = ['category=' + categories, 'active=' + active,
                 'hidexxx=' + ('off' if show_xxx else 'on')]
        if bgaudio:
            parts.append('bgaudio=1')
        if query:
            parts.append('search=' + quote_plus(query).replace('+', ' '))
        return self.base_url + '/torrents?' + '&'.join(parts)

    def search(self, query, categories=DEFAULT_CATEGORIES, active='1',
               bgaudio=False, show_xxx=False):
        res = self._get(self._listing_url(query, categories, active,
                                          bgaudio, show_xxx))
        items = parse_search_rows(res.text, self.base_url)
        return filter_relevant(items, query), parse_next_page(
            res.text, self.base_url)

    def browse(self, categories, active='1', bgaudio=False, show_xxx=False):
        """Category listing without a text query (same table, same parser)."""
        res = self._get(self._listing_url(None, categories, active,
                                          bgaudio, show_xxx))
        return parse_search_rows(res.text, self.base_url), parse_next_page(
            res.text, self.base_url)

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


SHOW_PREVIEW = re.compile(r'''showPreview\(['"]([a-f0-9]{40})['"]\)''')
HEX40 = re.compile(r'[a-f0-9]{40}')


def _row_identity(tr):
    """(tid, title) supporting both row markups.

    New markup: ``tr.torrent-index__row[data-preview-card]`` whose title
    anchor points back at the search URL with ``onclick=showPreview(id)``.
    Legacy markup: title anchor with a ``/torrents/<40hex>`` href.
    """
    tid = (tr.get('data-preview-card') or '').strip()
    if not HEX40.fullmatch(tid):
        tid = ''
    title, anchor = '', None
    name_cell = tr.select_one('td.torrent-index__name-cell')
    scope = name_cell if name_cell is not None else tr
    for cand in scope.select('a[href]'):
        text = cand.get_text(' ', strip=True)
        if not text or len(text) < 3:
            continue
        href = cand.get('href', '')
        if HEX_ID.search(href):
            return HEX_ID.search(href).group(1), text
        if 'showPreview(' in (cand.get('onclick', '') or ''):
            anchor = cand
            title = text
    if not tid and anchor is not None:
        match = SHOW_PREVIEW.search(anchor.get('onclick', ''))
        if match:
            tid = match.group(1)
    if tid and not title and anchor is not None:
        title = anchor.get_text(' ', strip=True)
    if tid and title:
        return tid, title
    return None, ''


def parse_search_rows(html_page, base_url):
    """Rows from the listing table: id, title, date, size, S/L/D, details url."""
    soup = BeautifulSoup(html_page, 'html.parser')
    table = _results_table(soup)
    if table is None:
        return []
    items = []
    for tr in table.select('tbody tr'):
        # Direct cells only: the layout nests tables for side blocks.
        cells = tr.find_all('td', recursive=False)
        tid, title = _row_identity(tr)
        if not tid:
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
            'id': tid,
            'title': title,
            'url': urljoin(base_url, '/torrents/' + tid),
            'date': date,
            'size': texts[size_idx],
            'seeders': seeders,
            'leechers': leechers,
            'snatched': snatched,
            'poster': _row_poster(tr),
            'bg_subs': _row_has_flag(tr, SUBS_FLAGS),
            'bg_audio': _row_has_flag(tr, BGAUDIO_FLAGS),
        })
    return items


def _row_poster(tr):
    for anchor in tr.select('a[onmouseover]'):
        match = re.search(r'img src=([^ >"\']+)', anchor.get('onmouseover', ''))
        if match:
            return match.group(1)
    overlibs = tr.select('[data-overlib]')
    for overlib in overlibs:
        match = re.search(r'img src="([^"]+)"',
                          overlib.get('data-overlib', ''))
        if match:
            return match.group(1)
    return ''


def _row_has_flag(tr, names):
    for img in tr.select('img[src]'):
        src = img.get('src', '')
        if any(src.endswith(name) for name in names):
            return True
    return False


def _results_table(soup):
    """The results table below the filter form; header heuristic as fallback.

    Listing pages mix a latest-additions block (same headers, mostly
    unrelated rows) with the real results table, so first-match wins wrong.
    The results table renders after the filter form.
    """
    form = soup.select_one('form[name="torrent_search"]')
    if form is not None:
        for table in form.find_all_next('table'):
            classes = table.get('class', [])
            if 'torrent-index__table' not in classes:
                continue
            if _table_has_rows(table):
                return table
    indexed = [t for t in soup.select('table.torrent-index__table')
               if _table_has_rows(t)]
    if indexed:
        return indexed[0]
    for candidate in soup.select('table'):
        heads = [th.get_text(strip=True) for th in candidate.select('thead th')]
        if any('Размер' in h for h in heads) and any(h == 'S' for h in heads):
            if _table_has_rows(candidate):
                return candidate
    return None


def _table_has_rows(table):
    for tr in table.select('tbody tr'):
        tid, _title = _row_identity(tr)
        if tid:
            return True
    return False


def parse_next_page(html_page, base_url):
    """Next-page link ('>' anchor) or '' when the listing ends."""
    soup = BeautifulSoup(html_page, 'html.parser')
    for anchor in soup.select('a[href]'):
        if anchor.get_text(strip=True) == '>':
            return urljoin(base_url, anchor['href'])
    return ''


def parse_details(html_page, base_url, tid):
    """Details page: title, .torrent url, info hash, files, stats, meta."""
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
    imdb = ''
    match = re.search(r'imdb.+?(tt\d+)', html_page)
    if match:
        imdb = match.group(1)
    meta = {}
    for label in ('Година', 'Жанр', 'Релийз', 'Видео поток', 'Резюме'):
        match = re.search(label + r'.+?fieldValue">(.+?)<', html_page)
        if not match:
            match = re.search(
                label + r'.+?torrent-preview-fact__value">(.+?)<', html_page)
        if match:
            meta[label] = re.sub(r'<[^>]+>', '', match.group(1)).strip()
    return {'id': tid, 'title': title, 'torrent_url': torrent_url,
            'info_hash': info_hash, 'files': files, 'imdb': imdb,
            'meta': meta}


def filter_relevant(items, query):
    """Client-side relevance guard: the tracker sometimes answers a search
    with an unfiltered listing. Keep items matching every query word;
    fall back to the full list when nothing matches (never hide all)."""
    words = [w.lower() for w in re.split(r'\s+', query or '') if w]
    if not words:
        return items
    matched = [it for it in items
               if all(w in it.get('title', '').lower() for w in words)]
    return matched or items


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
