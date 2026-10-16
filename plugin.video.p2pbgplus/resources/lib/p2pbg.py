# -*- coding: utf-8 -*-
"""Pure p2pbg.com logic: URL shapes, HTML parsing, filtering and ordering.

Nothing in this module imports Kodi, so it can be exercised offline and
reused by the tracker client.
"""
from __future__ import annotations

import re
import urllib.parse

BASE_URL = 'https://www.p2pbg.com'
SUBPAGE = BASE_URL + '/torrents/'
LOGIN_URL = '/login'

# English names, taken from the tracker's own <select name="category">.
CATEGORIES = (
    ('7', 'Movies Documentary'),
    ('11', 'Movies DVD'),
    ('14', 'TV Shows'),
    ('15', 'TV Boxset'),
    ('24', 'TV BG'),
    ('34', 'Movies BG'),
    ('35', 'Movies GSM'),
    ('38', 'Cartoons'),
    ('59', 'Movies VHS'),
    ('67', 'Movies SD'),
    ('68', 'Movies HD'),
    ('69', 'Movies Pack'),
)

# 4K is deliberately absent: listings and searches drop 2160p releases.
ALL_CATEGORIES = '7;11;14;15;24;34;35;38;59;67;68;69'
SEARCH_CATEGORIES = '0'

# Titles matching this are never listed (4K/UHD cannot be streamed reliably).
EXCLUDED_QUALITY = re.compile(r'(?i)(\b2160p\b|\b3840p\b|\b4k\b|\buhd\b)')

BG_SUBS_FLAGS = (
    'subs.gif',
    'torrent-flag-subs-in-torrent.png',
    'torrent-flag-external-subs.png',
    'torrent-flag-subs-in-video.png',
)
BG_AUDIO_FLAGS = ('bgaudio.gif', 'torrent-flag-bg-audio.png')


def listing_url(categories, search='', bgaudio=False, show_xxx=False):
    """Listing/search URL in the exact shape of the site's search form.

    The tracker only honours the filters when the whole form query is
    present (fake*remembered fields, search, category, active, bgaudio,
    hidexxx), and hidexxx is a boolean flag (1/0), not on/off.
    """
    url = (BASE_URL + '/torrents?fakeusernameremembered=&fakepasswordremembered=&search='
           + search + '&category=' + categories + '&active=1')
    if bgaudio:
        url += '&bgaudio=1'
    return url + '&hidexxx=' + ('0' if show_xxx else '1')


def all_url():
    """All movies, TV shows and boxsets: the bare category URL."""
    return BASE_URL + '/torrents?category=' + ALL_CATEGORIES


def search_url(text, bgaudio=False, show_xxx=False):
    """Search over all categories, spaces plus-encoded as confirmed."""
    return listing_url(SEARCH_CATEGORIES,
                       search=urllib.parse.quote_plus(text or ''),
                       bgaudio=bgaudio, show_xxx=show_xxx)


def to_int(text):
    """Never raise on '---' or empty cells; a dead row must not kill the
    whole listing (Kodi then keeps showing the previous menu)."""
    try:
        return int(str(text).replace('\u00a0', '').replace(' ', '')
                   .replace(',', '').strip())
    except (TypeError, ValueError):
        return 0


def is_excluded(title):
    """True for 4K/UHD releases, which this add-on does not list."""
    return bool(EXCLUDED_QUALITY.search(title or ''))


def sort_rows(rows):
    """Most active first: seeders desc, then leechers desc, then title."""
    return sorted(rows, key=lambda row: (
        -to_int(row.get('seeders')),
        -to_int(row.get('leechers')),
        (row.get('title') or '').lower(),
    ))


def search_value(url):
    """Current value of the search= parameter ('' when absent)."""
    _head, sep, tail = url.partition('&search=')
    if not sep:
        return ''
    return tail.partition('&')[0]


def with_search(url, text=''):
    """Replace only the search= value.

    The tracker honours the filters only when the whole form query is
    present (category/active/hidexxx) with literal ';' separators, so the
    query must not be rebuilt with urlencode.
    """
    head, sep, tail = url.partition('&search=')
    if not sep:
        return url + ('&search=' + text if text else '')
    rest = tail.partition('&')
    return head + '&search=' + text + ('&' + rest[2] if rest[1] else '')


def recover_listing_url(paramstring):
    """Dig a listing URL out of a (possibly mangled) plugin query.

    The listing address is part of the item URL, so it survives even when the
    mode/url parameters do not. Understands the plain and the (double)
    percent-encoded form and stops at the plugin's own parameters
    (mode/name/iconimage), so a listing query is never truncated.
    """
    if not paramstring:
        return ''
    flat = urllib.parse.unquote_plus(paramstring)
    # a query that was encoded twice keeps '?' and '=' percent-encoded
    flat = flat.replace('%3F', '?').replace('%3f', '?')
    head = flat.find('https://')
    if head < 0:
        return ''
    marker = '/torrents?'
    found = flat.find(marker, head)
    if found < 0:
        return ''
    tail = flat[found + len(marker):]
    stop = len(tail)
    for name in ('&mode=', '&name=', '&iconimage=', '&groupid=', '&count=',
                 '&ytpass='):
        pos = tail.lower().find(name)
        if pos >= 0:
            stop = min(stop, pos)
    url = urllib.parse.unquote_plus(
        flat[head:found + len(marker)] + tail[:stop])
    if 'category=' not in url and 'search=' not in url:
        return ''
    return url


def data_row_count(table):
    """Rows that look like real torrent rows (9 cells)."""
    return sum(1 for row in table.find_all('tr')
               if len(row.find_all('td')) >= 9)


def find_results_table(soup):
    """The results table, not the 'recommended' block above it.

    The proven exact match first; if the site changes attributes, fall back
    to the torrent-index table holding the most torrent rows.
    """
    exact = next(
        (
            t for t in soup.find_all("table")
            if t.get("width") == "100%"
               and t.get("class") == ["lista"]
               and len(t.attrs) == 2
        ),
        None
    )
    if exact:
        return exact
    exact = next(
        (
            t for t in soup.find_all("table")
            if t.get("class") == ["torrent-index__table"]
               and len(t.attrs) == 1
        ),
        None
    )
    if exact:
        return exact
    candidates = [t for t in soup.find_all("table")
                  if t.get("class") and 'torrent-index__table' in t.get("class")
                  and data_row_count(t)]
    if not candidates:
        return None
    return max(candidates, key=data_row_count)


def next_page_url(soup):
    """Address behind the pager's '>' link, or None."""
    for anchor in soup.find_all('a', href=True):
        if anchor.get_text(strip=True) == '>':
            return anchor['href']
    return None


def row_download_id(row):
    """Tracker preview id embedded in a results row, or None."""
    match = re.search(r"showPreview\('(.+?)'", str(row))
    return match.group(1) if match else None


def row_image(row):
    """Poster URL from the row's overlib markup, or None."""
    for anchor in row.find_all("a", onmouseover=True):
        if "img src=" in anchor["onmouseover"]:
            match = re.search(r"img src=([^ >]+)", anchor["onmouseover"])
            if match:
                return match.group(1)
    match = re.search('data-overlib=\'&lt;img src="(.+?)"', str(row))
    return match.group(1) if match else None


def _field(html, label, *value_classes):
    """Value of a details fact, first matching markup shape wins."""
    for value_class in value_classes:
        match = re.search(label + u'.+?class="' + value_class + u'">(.+?)<',
                          html)
        if match:
            return match.group(1)
    return ''


def parse_details(html):
    """Metadata scraped from a torrent's details page."""
    imdb = re.search(u'imdb.+?(tt.+?)/', html)
    torrent = re.search(
        re.escape(BASE_URL) + r'/download\.php.+?\.torrent', html)
    year = re.search(r'Година.+?(\d{4})', html)
    return {
        'imdb_id': imdb.group(1) if imdb else '',
        'torrent_url': torrent.group(0) if torrent else '',
        'year': year.group(1) if year else '',
        'genre': _field(html, u'Жанр', 'fieldValue',
                        'torrent-preview-fact__value'),
        'release': _field(html, u'Релийз', 'fieldValue',
                          'torrent-preview-fact__value'),
        'video': _field(html, u'Видео поток', 'fieldValue',
                        'torrent-preview-fact__value'),
        'synopsis': _field(html, u'Резюме', 'fieldValue',
                           'torrent-preview-fact__value'),
    }


def parse_row(row, details):
    """A results row plus its details page -> torrent dict (or None).

    Malformed rows return None instead of raising; the caller skips them.
    """
    cols = row.find_all('td')
    if len(cols) < 9:
        return None
    download_id = row_download_id(row)
    if not download_id:
        return None
    title_anchor = cols[1].find('a', onclick=True)
    if title_anchor is None:
        return None
    title = title_anchor.get_text(' ', strip=True)
    if is_excluded(title):
        return None
    details = details or {}
    if not details.get('torrent_url'):
        return None
    return {
        'download_id': download_id,
        'title': title,
        'torrent_url': details.get('torrent_url', ''),
        'size': cols[5].get_text(' ', strip=True),
        'seeders': to_int(cols[6].get_text(strip=True)),
        'leechers': to_int(cols[7].get_text(strip=True)),
        'bg_subs': bool(row.find('img', src=lambda x: x and any(
            x.endswith(s) for s in BG_SUBS_FLAGS))),
        'bg_audio': bool(row.find('img', src=lambda x: x and any(
            x.endswith(s) for s in BG_AUDIO_FLAGS))),
        'image': row_image(row),
        'imdb_id': details.get('imdb_id', ''),
        'year': details.get('year', ''),
        'genre': details.get('genre', ''),
        'release': details.get('release', ''),
        'video': details.get('video', ''),
        'synopsis': details.get('synopsis', ''),
    }
