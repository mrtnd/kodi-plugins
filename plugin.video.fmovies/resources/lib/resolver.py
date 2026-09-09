"""Browser-like stream resolution for fmovies.

Playback chain (reverse-engineered from the site's own player JS):
  film page (#mid[data-mid], .episode buttons, .server buttons)
    -> AES-GCM token (key = SHA256(geo loc from /cdn-cgi/trace))
    -> netoda.tech /watch/?v{srv}{eps}#token
    -> netoda /get/{salt}-{iv}-{ct}  (PBKDF2 "player" + AES-GCM)
    -> decrypt `info` -> "movie/<vid>-<ts>" (or "tv/<vid>-<ts>")
    -> vidnest (new.vidnest.fun) server APIs, custom-b64 decrypted
    -> direct master.m3u8

No yt-dlp, no iframe scraping: the old approach returned None because
fmovies pages contain no <iframe> until the JS player builds one.
"""
import re
import time
from urllib.parse import urljoin

import requests  # kept: tests patch resources.lib.resolver.requests.Session.get
from bs4 import BeautifulSoup

from resources.lib.http import GENERIC_HEADERS, decode_html, make_session, normalize_base_url
from resources.lib.info import clean_film_title
from resources.lib.kodi_utils import get_setting
from resources.lib.media import verify_m3u8
from resources.lib import netoda as _netoda
from resources.lib import vidnest as _vidnest
from resources.lib.subtitles import fetch_vdrk, pick_subtitles, OpenSubtitles

NETODA_BASE = 'https://netoda.tech'

# Re-exported helpers so existing imports keep working:
#   from resources.lib.resolver import netoda_hash, vidnest_decode, ...
netoda_hash = _netoda.build_watch_fragment
netoda_get_path = _netoda.build_get_path
netoda_decrypt_info = _netoda.decrypt_info
_pbkdf2_key = _netoda.pbkdf2_key
_b64url_encode = _netoda._b64url_encode
vidnest_decode = _vidnest.decode_payload
VIDNEST_API = _vidnest.VIDNEST_API
VIDNEST_B64 = _vidnest.VIDNEST_B64
VIDNEST_SERVERS = _vidnest.VIDNEST_SERVERS

__all__ = [
    'ResolveError', 'ResolvedURL', 'StreamResolver',
    'clean_film_title', 'pick_subtitles',
    'netoda_hash', 'netoda_get_path', 'netoda_decrypt_info',
    'vidnest_decode',
]


class ResolveError(Exception):
    pass


class ResolvedURL(str):
    """Stream URL string carrying subtitle URLs for the Kodi handoff."""
    subtitles = ()


class StreamResolver:
    def __init__(self):
        self.session = make_session(GENERIC_HEADERS)
        self.base_url = normalize_base_url(get_setting('base_url'))
        self._os = OpenSubtitles(self.session)

    # -- stage 1: film page -> playback ids -------------------------------
    def get_ids(self, page_url):
        """Scrape (mid, eps, mode) from a film page like a browser would."""
        response = self.session.get(page_url, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(decode_html(response), 'html.parser')
        mid_el = soup.select_one('#mid[data-mid]')
        if not mid_el:
            raise ResolveError('film page has no player (#mid missing)')
        mid = mid_el.get('data-mid')
        mode = mid_el.get('data-mode', 'movie')
        title = ''
        og = soup.select_one('meta[property="og:title"]')
        if og and og.get('content'):
            title = og['content']
        if not title and soup.title and soup.title.string:
            title = soup.title.string
        title = clean_film_title(title or '')
        episodes = []
        for el in soup.select('.episode'):
            el_id = el.get('id', '')
            num = el_id.split('-').pop() if '-' in el_id else ''
            episodes.append({
                'num': num or el.get_text(strip=True),
                'title': el.get('title', '') or el.get_text(strip=True),
            })
        return {'mid': mid, 'mode': mode, 'episodes': episodes, 'title': title}

    def get_servers(self, page_url):
        """Scrape available stream servers on the movie/episode page."""
        response = self.session.get(page_url, timeout=12)
        soup = BeautifulSoup(decode_html(response), 'html.parser')
        servers = []
        for el in soup.select('#srv-list .server, button.server'):
            el_id = el.get('id', '')
            num = el_id.split('-').pop() if '-' in el_id else ''
            servers.append({
                'name': el.get_text(strip=True) or 'Server {}'.format(len(servers) + 1),
                'id': el_id,
                'num': num,
                'page_url': page_url,
            })
        if not servers:
            servers.append({'name': 'Server 2 (Default)', 'id': 'srv-2',
                            'num': '2', 'page_url': page_url})
        return servers

    # -- stage 2: geo loc --------------------------------------------------
    def get_loc(self):
        for url in (self.base_url + '/cdn-cgi/trace', NETODA_BASE + '/cdn-cgi/trace'):
            try:
                res = self.session.get(url, timeout=10)
                for line in res.text.strip().split():
                    if line.startswith('loc='):
                        return line.split('=', 1)[1].strip()
            except Exception:
                continue
        raise ResolveError('could not determine geo loc (trace failed)')

    def _get_json(self, url, **kwargs):
        """GET with retries for the flaky embed hosts (502/429/empty bodies)."""
        last = None
        for attempt in range(3):
            try:
                res = self.session.get(url, timeout=12, **kwargs)
                if res.status_code != 200:
                    last = 'http {}'.format(res.status_code)
                    continue
                try:
                    return res.json()
                except ValueError:
                    last = 'bad json ({!r}...)'.format(res.text[:60])
                    continue
            except Exception as exc:
                last = str(exc)
            time.sleep(1 + attempt)
        raise ResolveError('{} ({})'.format(url.split('?')[0].rsplit('/', 1)[0], last))

    # -- stage 3: netoda -> video id --------------------------------------
    def netoda_video_id(self, mid, eps, srv, loc):
        frag = _netoda.build_watch_fragment(mid, eps, srv, loc)
        page_url = '{}?v{}{}#{}'.format(NETODA_BASE + '/watch/', srv, eps, frag)
        path = _netoda.build_get_path(mid, eps, srv)
        try:
            payload = self._get_json(
                NETODA_BASE + '/get/' + path,
                headers={'Referer': page_url},
            )
        except ResolveError as exc:
            raise ResolveError('netoda /get/ failed: {}'.format(exc))
        if payload.get('code') != 200 or not payload.get('info'):
            raise ResolveError('netoda returned no stream info')
        try:
            plain = _netoda.decrypt_info(payload['info'])
        except Exception as exc:
            raise ResolveError('netoda decrypt failed: {}'.format(exc))
        return self._parse_video_ref(plain)

    @staticmethod
    def _parse_video_ref(plain):
        # plain looks like 'movie/1443200-1788798062',
        # 'tv/329471/1-1-1788799072', a bare id (other providers),
        # or a full embed URL (e.g. vidara.to).
        if plain.startswith('http'):
            return 'embed', plain.split('-')[0].rsplit('#', 1)[0].strip(), None, None
        try:
            kind, rest = plain.split('/', 1)
        except ValueError:
            raise ResolveError('unsupported server payload')
        if kind == 'movie':
            vid = rest.split('-')[0].split('+')[0]
            if not vid.isdigit():
                raise ResolveError('unsupported server payload')
            return kind, vid, None, None
        if kind == 'tv':
            # 'vid/season-episode-ts'
            segs = rest.split('/')
            vid = segs[0]
            sub = segs[1].split('-') if len(segs) > 1 else []
            season = sub[0] if len(sub) > 2 else None
            episode = '-'.join(sub[1:-1]) if len(sub) > 2 else (sub[0] if sub else None)
            if not vid.isdigit():
                raise ResolveError('unsupported server payload')
            return kind, vid, season, episode
        raise ResolveError('unsupported server payload')

    # -- stage 4: vidnest -> m3u8 -----------------------------------------
    def _vidnest_candidates(self, kind, vid, season=None, episode=None):
        for name, _type in VIDNEST_SERVERS:
            url = _vidnest.build_url(name, kind, vid, season, episode)
            try:
                res = self.session.get(
                    url,
                    headers={'Referer': 'https://vidnest.fun/',
                             'Accept': 'application/json'},
                    timeout=12,
                )
                # NB: error payloads (e.g. http 400) can still carry streams
                try:
                    payload = res.json()
                except ValueError:
                    continue
            except Exception:
                continue
            yield name, _vidnest.maybe_decrypt(payload)

    _extract_streams = staticmethod(_vidnest.extract_streams)

    def _verify_m3u8(self, url, headers):
        return verify_m3u8(self.session, url, headers)

    def vidnest_stream(self, kind, vid, season=None, episode=None,
                       title=None, sub_dir=None):
        errors = []
        sub_entries = []
        winner = None
        for name, payload in self._vidnest_candidates(kind, vid, season, episode):
            if isinstance(payload, dict) and payload.get('subtitles'):
                sub_entries.extend(payload['subtitles'])
            if winner is not None:
                continue  # stream found: keep harvesting subtitles only
            streams = _vidnest.extract_streams(payload)
            if not streams:
                errors.append('{}: no streams'.format(name))
                continue
            for url, headers in streams:
                # content-sniffed: providers use .m3u8, master.txt, .mp4, ...
                if verify_m3u8(self.session, url, headers):
                    winner = (url, headers)
                    break
                errors.append('{}: dead link'.format(name))
        if winner is None:
            raise ResolveError('vidnest: ' + ('; '.join(errors) if errors else 'no servers answered'))
        url, headers = winner
        subs = pick_subtitles(sub_entries)
        if not subs:
            subs = self._vdrk_subtitles(kind, vid, season, episode)
        if not subs:
            subs = self._opensubtitles_subs(
                kind, vid, title=title, season=season, episode=episode,
                dest_dir=sub_dir)
        return url, headers, subs

    # -- subtitles (delegated, back-compat wrappers) -----------------------
    def _vdrk_subtitles(self, kind, vid, season=None, episode=None):
        return fetch_vdrk(self.session, kind, vid, season, episode)

    def _os_login(self):
        return self._os.login()

    def _os_imdb_id(self, kind, vid):
        return self._os.imdb_id(kind, vid)

    def _os_download_best(self, candidates, dest_dir, tag):
        return self._os.download_best(candidates, dest_dir, tag)

    def _opensubtitles_subs(self, kind, vid, title=None, season=None,
                            episode=None, dest_dir=None):
        # Implemented here (not delegated) so the _os_* wrappers stay
        # patchable by tests; OpenSubtitles.search mirrors this logic
        # for standalone use.
        import xmlrpc.client
        if not dest_dir:
            return []
        try:
            token = self._os_login()
            server = xmlrpc.client.ServerProxy(
                'https://api.opensubtitles.org/xml-rpc', allow_none=True)
            query = {'sublanguageid': 'eng'}
            imdb = self._os_imdb_id(kind, vid)
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
            return self._os_download_best(data, dest_dir, tag)
        except Exception:
            return []

    def _resolve_embed_url(self, embed_url, page_url):
        """Generic fallback: scrape a direct m3u8/mp4 out of an embed page."""
        try:
            res = self.session.get(embed_url, headers={'Referer': page_url}, timeout=12)
        except Exception as exc:
            raise ResolveError('embed fetch failed: {}'.format(exc))
        hits = re.findall(r'(https?://[^\s\'"]+\.(?:m3u8|mp4)[^\s\'"]*)', res.text)
        if not hits:
            raise ResolveError('embed has no direct stream')
        url = hits[0]
        if verify_m3u8(self.session, url, None):
            return url, {}
        raise ResolveError('embed link is dead')

    # -- full chain ---------------------------------------------------------
    def _resolve_one(self, page_url, ids, eps, srv, sub_dir=None):
        loc = self.get_loc()
        kind, vid, season, episode = self.netoda_video_id(ids['mid'], eps, srv, loc)
        if kind == 'embed':
            url, headers = self._resolve_embed_url(vid, page_url)
            return url, headers, []
        if kind == 'tv' and not (season and episode):
            # fall back to season from the series page URL (e.g. ...-season-1-...)
            m = re.search(r'season-(\d+)', page_url)
            season = season or (m.group(1) if m else '1')
            episode = episode or eps
        return self.vidnest_stream(kind, vid, season, episode,
                                   title=ids.get('title'), sub_dir=sub_dir)

    def resolve_stream_any(self, servers, eps=None, sub_dir=None):
        """Try each server in order; return the first verified stream URL."""
        if not servers:
            raise ResolveError('no stream servers found')
        page_url = servers[0].get('page_url', self.base_url)
        ids = self.get_ids(page_url)
        eps = eps or (ids['episodes'][0]['num'] if ids['episodes'] else '1')
        errors = []
        for srv_data in servers:
            srv = srv_data.get('num') or '2'
            try:
                url, headers, subs = self._resolve_one(page_url, ids, eps, srv, sub_dir)
                break
            except ResolveError as exc:
                errors.append('{}: {}'.format(srv_data.get('name', srv), exc))
        else:
            raise ResolveError(' // '.join(errors))
        kodi_headers = dict(GENERIC_HEADERS)
        kodi_headers.update(headers or {})
        # Per-stream headers win: several hosts enforce their own Referer.
        referer = (headers or {}).get('Referer') or NETODA_BASE + '/'
        suffix = 'Referer={}&User-Agent={}'.format(
            referer, kodi_headers.get('User-Agent', GENERIC_HEADERS['User-Agent']))
        resolved = ResolvedURL('{}|{}'.format(url, suffix))
        resolved.subtitles = tuple(subs or ())
        return resolved

    def resolve_stream(self, server_data):
        """Resolve a server dict (from get_servers, with mid/eps) to a stream URL."""
        return self.resolve_stream_any([server_data], server_data.get('eps'))
