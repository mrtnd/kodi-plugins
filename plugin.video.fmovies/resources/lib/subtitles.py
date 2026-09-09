"""Subtitle picking + download clients (vdrk, opensubtitles.org)."""
from __future__ import annotations

import base64 as _b64
import gzip
import os
import re

OS_UA = 'FMoviesKodi'


def is_english(label) -> bool:
    label = (label or '').strip().lower()
    return label in ('english', 'en', 'eng') or 'english' in label


def pick_subtitles(entries, limit: int = 3) -> list:
    """Pick English subtitle URLs from vidnest/vdrk-style entries."""
    english, other = [], []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        url = entry.get('url') or entry.get('file')
        if not url or not url.startswith('http'):
            continue
        label = entry.get('lang') or entry.get('label') or entry.get('display') or ''
        (english if is_english(label) else other).append(url)
    seen = set()
    out = []
    for url in english + other:
        if url not in seen:
            seen.add(url)
            out.append(url)
        if len(out) >= limit:
            break
    return out


def fetch_vdrk(session, kind: str, vid: str,
               season=None, episode=None) -> list:
    """Fallback subtitle source (vdrk API, keyed by vidnest id)."""
    if kind == 'tv' and season and episode:
        url = 'https://sub.vdrk.site/v2/tv/{}/{}/{}'.format(vid, season, episode)
    else:
        url = 'https://sub.vdrk.site/v2/{}/{}'.format(kind, vid)
    try:
        res = session.get(url, headers={'Accept': 'application/json'}, timeout=10)
        if res.status_code != 200:
            return []
        data = res.json()
        entries = data if isinstance(data, list) else data.get('subtitles', [])
        return pick_subtitles(entries)
    except Exception:
        return []


class OpenSubtitles:
    """Anonymous opensubtitles.org XML-RPC client downloading best .srt."""

    def __init__(self, session):
        self.session = session
        self._token = None

    def login(self):
        import xmlrpc.client
        if self._token:
            return self._token
        server = xmlrpc.client.ServerProxy(
            'https://api.opensubtitles.org/xml-rpc', allow_none=True)
        res = server.LogIn('', '', 'en', OS_UA)
        if res.get('status') != '200 OK':
            raise ValueError('opensubtitles login failed')
        self._token = res['token']
        return self._token

    def imdb_id(self, kind: str, vid: str):
        if kind != 'movie':
            return None
        try:
            res = self.session.get(
                'https://data.vidsrcme.ru/api.php?type=movie&tmdb={}'.format(vid),
                headers={'Accept': 'application/json'}, timeout=10)
            imdb = (res.json().get('data') or {}).get('imdb_id', '')
            return imdb.replace('tt', '') or None
        except Exception:
            return None

    def search(self, kind: str, vid: str, title=None,
               season=None, episode=None, dest_dir=None) -> list:
        import xmlrpc.client
        if not dest_dir:
            return []
        try:
            token = self.login()
            server = xmlrpc.client.ServerProxy(
                'https://api.opensubtitles.org/xml-rpc', allow_none=True)
            query = {'sublanguageid': 'eng'}
            imdb = self.imdb_id(kind, vid)
            if imdb:
                query['imdbid'] = imdb
            elif title:
                clean = re.sub(r'\s+-\s+Season\s+\d+\s*$', '', title,
                               flags=re.IGNORECASE).strip()
                query['query'] = clean
                if kind == 'tv' and season and episode:
                    query['season'] = str(season)
                    query['episode'] = str(episode)
            else:
                return []
            res = server.SearchSubtitles(token, [query])
            data = res.get('data') or []
            tag = '{}{}{}'.format(vid, season or '', episode or '')
            return self.download_best(data, dest_dir, tag)
        except Exception:
            return []

    def download_best(self, candidates, dest_dir: str, tag: str) -> list:
        """Download the most-downloaded candidate sub to dest_dir."""
        import xmlrpc.client
        if not candidates or not dest_dir:
            return []
        best = sorted(candidates, key=lambda c: int(c.get('SubDownloadsCnt') or 0),
                      reverse=True)[0]
        try:
            server = xmlrpc.client.ServerProxy(
                'https://api.opensubtitles.org/xml-rpc', allow_none=True)
            res = server.DownloadSubtitles(self.login(), [best['IDSubtitleFile']])
            blob = (res.get('data') or [{}])[0].get('data')
            if not blob:
                return []
            raw = gzip.decompress(_b64.b64decode(blob))
        except Exception:
            return []
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception:
            return []
        path = os.path.join(dest_dir, 'os_{}_{}.srt'.format(tag, best['IDSubtitleFile']))
        try:
            with open(path, 'wb') as fh:
                fh.write(raw)
        except Exception:
            return []
        return [path]
