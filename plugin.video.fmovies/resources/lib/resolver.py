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
import base64
import hashlib
import json
import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from resources.lib.aesgcm import gcm_encrypt, gcm_decrypt
from resources.lib.kodi_utils import get_setting
from resources.lib.scraper import decode_html

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': '*/*',
}

NETODA_BASE = 'https://netoda.tech'
VIDNEST_API = 'https://new.vidnest.fun'
# Custom base64 alphabet used by vidnest's decryptCipherResponse
VIDNEST_B64 = 'RB0fpH8ZEyVLkv7c2i6MAJ5u3IKFDxlS1NTsnGaqmXYdUrtzjwObCgQP94hoeW+/='
_STD_B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/='

# vidnest servers, in the same order/preference as the vidnest web UI
VIDNEST_SERVERS = (
    ('rogflix', 'movie'),            # filxer: {"url": ...}
    ('videasy', 'movie'),            # alfa: {"url": ..., "headers": {...}}
    ('vidrock', 'movie'),            # prime: {"sources": [...]}
    ('vidzee', 'movie'),             # gama: {"streams": [...]}
    ('vidxyz', 'movie'),             # beta: {"streams": [...]}
    ('klikxxi', 'movie'),            # ophim: {"sources": [...]}
    ('buzz', 'movie'),               # catflix: {"url": ..., "headers": {...}}
    ('nextgencloudfabric', 'movie'),  # zeta: {"url", "all_urls": [...]}
    ('hollymoviehd', 'movie'),       # sigma: {"streams": [...]}
)


class ResolveError(Exception):
    pass


class ResolvedURL(str):
    """Stream URL string carrying subtitle URLs for the Kodi handoff."""
    subtitles = ()


def _is_english(label):
    label = (label or '').strip().lower()
    return label in ('english', 'en', 'eng') or 'english' in label


def clean_film_title(title):
    """Reduce a film page title ('Watch X - Season 1 Full Movie on ...')
    to the plain work title ('X - Season 1') for subtitle search."""
    title = re.sub(r'^(watch\s+)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+on\s+fmovies.*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+full\s+(movie|serie|series|episode).*?$', '', title,
                   flags=re.IGNORECASE)
    title = re.sub(r'\s*[|]\s*Fmovies.*$', '', title)
    title = re.sub(r'\s+online\s*$', '', title, flags=re.IGNORECASE)
    return title.strip()


def pick_subtitles(entries, limit=3):
    """Pick English subtitle URLs from vidnest/vdrk-style entries."""
    english, other = [], []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        url = entry.get('url') or entry.get('file')
        if not url or not url.startswith('http'):
            continue
        label = entry.get('lang') or entry.get('label') or entry.get('display') or ''
        (english if _is_english(label) else other).append(url)
    seen = set()
    out = []
    for url in english + other:
        if url not in seen:
            seen.add(url)
            out.append(url)
        if len(out) >= limit:
            break
    return out


def _b64url_encode(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip('=')


def vidnest_decode(data):
    """Decode vidnest's custom-alphabet base64 payload (their decryptCipherResponse)."""
    std = data.translate(str.maketrans(VIDNEST_B64, _STD_B64))
    return base64.b64decode(std)


def netoda_hash(mid, eps, srv, loc, ts=None):
    """Build the netoda #watch fragment exactly like app-single.min.js be()."""
    ts = ts if ts is not None else int(time.time())
    plain = '{}+{}+{}+{}+{}'.format(mid, eps, srv, loc, ts).encode()
    key = hashlib.sha256(loc.encode()).digest()
    iv = os.urandom(12)
    ct, tag = gcm_encrypt(key, iv, plain)
    token = base64.b64encode(iv + ct + tag).decode()
    return _b64url_encode(token)


def _pbkdf2_key(salt):
    return hashlib.pbkdf2_hmac('sha256', b'player', salt, 1000, 32)


def netoda_get_path(mid, eps, srv, ts=None):
    """Build the netoda /get/{salt}-{iv}-{ct} path (PBKDF2 'player' + AES-GCM)."""
    ts = ts if ts is not None else int(time.time())
    plain = '{}+{}+{}+{}'.format(mid, eps, srv, ts).encode()
    salt = os.urandom(8)
    key = _pbkdf2_key(salt)
    iv = os.urandom(12)
    ct, tag = gcm_encrypt(key, iv, plain)
    return '{}-{}-{}'.format(salt.hex(), iv.hex(), (ct + tag).hex())


def netoda_decrypt_info(info):
    """Decrypt a netoda /get/ `info` token -> e.g. 'movie/1443200-1788798062'."""
    salt_hex, iv_hex, ct_hex = info.split('-')
    key = _pbkdf2_key(bytes.fromhex(salt_hex))
    data = bytes.fromhex(ct_hex)
    return gcm_decrypt(key, bytes.fromhex(iv_hex), data[:-16], data[-16:]).decode()


class StreamResolver:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.base_url = get_setting('base_url').rstrip('/') or 'https://fmoviess.org'

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
        eps_els = soup.select('.episode')
        episodes = []
        for el in eps_els:
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
            servers.append({'name': 'Server 2 (Default)', 'id': 'srv-2', 'num': '2', 'page_url': page_url})
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
        frag = netoda_hash(mid, eps, srv, loc)
        page_url = '{}?v{}{}#{}'.format(NETODA_BASE + '/watch/', srv, eps, frag)
        path = netoda_get_path(mid, eps, srv)
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
            plain = netoda_decrypt_info(payload['info'])
        except Exception as exc:
            raise ResolveError('netoda decrypt failed: {}'.format(exc))
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
            if kind == 'tv' and season and episode:
                url = '{}/{}/tv/{}/{}/{}'.format(VIDNEST_API, name, vid, season, episode)
            else:
                url = '{}/{}/{}/{}'.format(VIDNEST_API, name, kind, vid)
            try:
                res = self.session.get(
                    url,
                    headers={'Referer': 'https://vidnest.fun/', 'Accept': 'application/json'},
                    timeout=12,
                )
                # NB: error payloads (e.g. http 400) can still carry streams
                try:
                    payload = res.json()
                except ValueError:
                    continue
            except Exception:
                continue
            if payload.get('encrypted'):
                try:
                    payload = json.loads(vidnest_decode(payload['data']).decode())
                except Exception:
                    continue
            yield name, payload

    @staticmethod
    def _extract_streams(name, payload):
        """Normalize the per-server vidnest response shapes to [(url, headers)]."""
        if not isinstance(payload, dict):
            return []
        fallback_headers = payload.get('headers') or {}
        if payload.get('referer') and 'Referer' not in fallback_headers:
            fallback_headers = dict(fallback_headers, Referer=payload['referer'])
        out = []
        if payload.get('url'):
            out.append((payload['url'], fallback_headers))
        for key in ('streams', 'sources', 'all_urls'):
            items = payload.get(key)
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict) and it.get('url'):
                        out.append((it['url'], it.get('headers') or fallback_headers))
                    elif isinstance(it, str) and it.startswith('http'):
                        out.append((it, fallback_headers))
        # prefer hls manifests
        out.sort(key=lambda u: (0 if 'm3u8' in u[0] else 1))
        return out

    # Byte signatures of real media segments (hosts often lie about MIME).
    _MEDIA_MAGICS = (b'\x47', b'ID3')

    @classmethod
    def _looks_like_media(cls, head, content_type=''):
        ctype = (content_type or '').split(';')[0].strip().lower()
        if ctype.startswith('image/'):
            return False
        if head[:1] == b'\x47' and len(head) >= 188:
            return True  # MPEG-TS sync byte
        if len(head) >= 8 and head[4:8] == b'ftyp':
            return True  # fragmented MP4
        if head[:3] == b'ID3':
            return True
        if ctype.startswith(('video/', 'application/vnd.apple.mpegurl',
                              'application/x-mpegurl', 'audio/')):
            return True
        return False

    def _playlist_urls(self, text, base):
        urls = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            urls.append(urljoin(base, line))
        return urls

    def _verify_m3u8(self, url, headers):
        """Verify a manifest AND its first media segment (rejects ad-pixel
        poisoned playlists whose segments are 1x1 tracking images)."""
        try:
            res = self.session.get(url, headers=headers or None, timeout=12)
            if '#EXTM3U' not in res.text[:2000]:
                if self._looks_like_media(res.content[:8], res.headers.get('content-type', '')):
                    return True  # direct media file
                return False
            if '.mp4' in url.split('?')[0]:
                return True
            urls = self._playlist_urls(res.text, url)
            if not urls:
                return False
            seg_url = urls[0]
            if '#EXT-X-STREAM-INF' in res.text:
                # variant playlist: the first URL is another playlist
                # regardless of its extension. Descend one level.
                vres = self.session.get(seg_url, headers=headers or None, timeout=12)
                if '#EXTM3U' not in vres.text[:2000]:
                    return False
                vurls = self._playlist_urls(vres.text, seg_url)
                if not vurls:
                    return False
                seg_url = vurls[0]
                if '#EXT-X-STREAM-INF' in vres.text:
                    return False  # nested variants: give up
            try:
                seg_headers = dict(headers or {})
                seg_headers['Range'] = 'bytes=0-2047'
                sres = self.session.get(seg_url, headers=seg_headers, timeout=12)
            except Exception:
                return False
            return self._looks_like_media(sres.content[:2048], sres.headers.get('content-type', ''))
        except Exception:
            return False

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
            streams = self._extract_streams(name, payload)
            if not streams:
                errors.append('{}: no streams'.format(name))
                continue
            for url, headers in streams:
                # content-sniffed: providers use .m3u8, master.txt, .mp4, ...
                if self._verify_m3u8(url, headers):
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

    # -- opensubtitles.org (free, anonymous) -> downloaded .srt files ----
    _OS_UA = 'FMoviesKodi'
    _os_token = None

    def _os_login(self):
        import xmlrpc.client
        if self._os_token:
            return self._os_token
        server = xmlrpc.client.ServerProxy(
            'https://api.opensubtitles.org/xml-rpc', allow_none=True)
        res = server.LogIn('', '', 'en', self._OS_UA)
        if res.get('status') != '200 OK':
            raise ResolveError('opensubtitles login failed')
        self._os_token = res['token']
        return self._os_token

    def _os_imdb_id(self, kind, vid):
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

    def _os_download_best(self, candidates, dest_dir, tag):
        """Download the most-downloaded candidate sub to dest_dir. Returns [path]."""
        import gzip
        import base64 as _b64
        import xmlrpc.client
        if not candidates or not dest_dir:
            return []
        best = sorted(candidates, key=lambda c: int(c.get('SubDownloadsCnt') or 0),
                      reverse=True)[0]
        try:
            server = xmlrpc.client.ServerProxy(
                'https://api.opensubtitles.org/xml-rpc', allow_none=True)
            res = server.DownloadSubtitles(
                self._os_login(), [best['IDSubtitleFile']])
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

    def _opensubtitles_subs(self, kind, vid, title=None, season=None,
                            episode=None, dest_dir=None):
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

    def _vdrk_subtitles(self, kind, vid, season=None, episode=None):
        """Fallback subtitle source (vdrk API, keyed by vidnest id)."""
        if kind == 'tv' and season and episode:
            url = 'https://sub.vdrk.site/v2/tv/{}/{}/{}'.format(vid, season, episode)
        else:
            url = 'https://sub.vdrk.site/v2/{}/{}'.format(kind, vid)
        try:
            res = self.session.get(url, headers={'Accept': 'application/json'}, timeout=10)
            if res.status_code != 200:
                return []
            data = res.json()
            entries = data if isinstance(data, list) else data.get('subtitles', [])
            return pick_subtitles(entries)
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
        if self._verify_m3u8(url, None):
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
        kodi_headers = dict(DEFAULT_HEADERS)
        kodi_headers.update(headers or {})
        # Per-stream headers win: several hosts enforce their own Referer.
        referer = (headers or {}).get('Referer') or NETODA_BASE + '/'
        suffix = 'Referer={}&User-Agent={}'.format(
            referer, kodi_headers.get('User-Agent', DEFAULT_HEADERS['User-Agent']))
        resolved = ResolvedURL('{}|{}'.format(url, suffix))
        resolved.subtitles = tuple(subs or ())
        return resolved

    def resolve_stream(self, server_data):
        """Resolve a server dict (from get_servers, with mid/eps) to a stream URL."""
        return self.resolve_stream_any([server_data], server_data.get('eps'))
