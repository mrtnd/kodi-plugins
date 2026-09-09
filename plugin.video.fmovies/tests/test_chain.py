"""Browser-like chain tests: crypto, vidnest decode, netoda codec, full resolve.

Uses recorded fixtures (tests/fixtures) captured from real browser sessions,
so they replay exactly what a working browser playback produces.
"""
import base64
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import MagicMock, patch

FIX = os.path.join(os.path.dirname(__file__), 'fixtures')


def _mock_addon():
    class MockXbmcAddon:
        def __init__(self, id='plugin.video.fmovies'):
            pass

        def getSetting(self, id):
            return 'https://fmoviess.org'

        def setSetting(self, id, value):
            pass

        def getAddonInfo(self, id):
            return 'mock_value'

    sys.modules.setdefault('xbmc', type('obj', (object,), {}))
    sys.modules.setdefault('xbmcaddon', type('obj', (object,), {'Addon': MockXbmcAddon}))


_mock_addon()

from resources.lib.aesgcm import gcm_encrypt, gcm_decrypt  # noqa: E402
from resources.lib.resolver import (  # noqa: E402
    StreamResolver,
    netoda_hash,
    netoda_get_path,
    netoda_decrypt_info,
    vidnest_decode,
    _pbkdf2_key,
)


def _b64url_decode(frag):
    return base64.urlsafe_b64decode(frag + '=' * (-len(frag) % 4))


class TestAesGcm(unittest.TestCase):
    def test_nist_zero_vector(self):
        # NIST SP800-38D test case 1
        _, tag = gcm_encrypt(b'\x00' * 16, b'\x00' * 12, b'')
        self.assertEqual(tag.hex(), '58e2fccefa7e3061367f1d57a4e7455a')

    def test_browser_captured_vector(self):
        # Captured via instrumented headless browser on netoda.tech:
        # key = SHA256('BG'), decrypts the location.hash payload.
        iv = bytes.fromhex('e732ff1305104968eb4ba15d')
        data = bytes.fromhex(
            '1cd4ca31f01406532332ebb6e075998980a5c18e4bf59e8363'
            'ca7987ed47f074aae30e96cef7'
        )
        pt = gcm_decrypt(hashlib.sha256(b'BG').digest(), iv, data[:-16], data[-16:])
        self.assertEqual(pt, b'1423+1+2+BG+1788796522')

    def test_roundtrip_and_tag_auth(self):
        import os as _os
        key, iv = _os.urandom(32), _os.urandom(12)
        ct, tag = gcm_encrypt(key, iv, b'movie/1443200-1788798062')
        self.assertEqual(gcm_decrypt(key, iv, ct, tag), b'movie/1443200-1788798062')
        with self.assertRaises(ValueError):
            gcm_decrypt(key, iv, ct, b'\x00' * 16)


class TestNetodaCodec(unittest.TestCase):
    def test_hash_decrypts_like_browser(self):
        frag = netoda_hash('1423', '1', '2', 'BG', ts=1788796522)
        token = _b64url_decode(frag).decode()
        raw = base64.b64decode(token)
        pt = gcm_decrypt(hashlib.sha256(b'BG').digest(), raw[:12], raw[12:-16], raw[-16:])
        self.assertEqual(pt, b'1423+1+2+BG+1788796522')

    def test_get_path_and_info_roundtrip(self):
        path = netoda_get_path('1423', '1', '2', ts=1788797993)
        salt_hex, iv_hex, ct_hex = path.split('-')
        key = _pbkdf2_key(bytes.fromhex(salt_hex))
        data = bytes.fromhex(ct_hex)
        pt = gcm_decrypt(key, bytes.fromhex(iv_hex), data[:-16], data[-16:])
        self.assertEqual(pt, b'1423+1+2+1788797993')

        # info token decrypt (same PBKDF2 scheme as the live /get/ responses)
        salt = bytes.fromhex('0123456789abcdef')
        key2 = _pbkdf2_key(salt)
        iv2 = bytes.fromhex('00112233445566778899aabb')
        ct2, tag2 = gcm_encrypt(key2, iv2, b'movie/969681-1788798024')
        info = '{}-{}-{}'.format(salt.hex(), iv2.hex(), (ct2 + tag2).hex())
        self.assertEqual(netoda_decrypt_info(info), 'movie/969681-1788798024')


class TestVidnestDecode(unittest.TestCase):
    def test_recorded_rogflix_payload(self):
        with open(os.path.join(FIX, 'rogflix_969681.json')) as fh:
            payload = json.load(fh)
        self.assertTrue(payload.get('encrypted'))
        decoded = json.loads(vidnest_decode(payload['data']).decode())
        self.assertIn('akcloud.animanga.fun', decoded['url'])
        self.assertTrue(decoded['url'].endswith('/master.m3u8'))

    def test_recorded_videasy_payload(self):
        with open(os.path.join(FIX, 'videasy_1443200.json')) as fh:
            payload = json.load(fh)
        decoded = json.loads(vidnest_decode(payload['data']).decode())
        self.assertIn('tiktoks.animanga.fun', decoded['url'])
        self.assertIn('headers', decoded)


def _fixture_router(url, *args, **kwargs):
    resp = MagicMock()
    resp.status_code = 200
    if url.endswith('/cdn-cgi/trace'):
        with open(os.path.join(FIX, 'trace.txt')) as fh:
            resp.text = fh.read()
        resp.json = lambda: {}
        return resp
    if '/film/' in url:
        with open(os.path.join(FIX, 'film_burt.html')) as fh:
            resp.text = fh.read()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {}
        return resp
    if '/netoda.tech/get/' in url:
        # Live-shaped response: encrypt movie/969681 with a fresh salt,
        # exercising the real decrypt path in the resolver.
        import os as _os
        salt = _os.urandom(8)
        iv = _os.urandom(12)
        ct, tag = gcm_encrypt(_pbkdf2_key(salt), iv, b'movie/969681-1788798024')
        info = '{}-{}-{}'.format(salt.hex(), iv.hex(), (ct + tag).hex())
        resp.text = json.dumps({'code': 200, 'info': info, 'mode': 'embed'})
        resp.json = lambda: {'code': 200, 'info': info, 'mode': 'embed'}
        return resp
    if '/rogflix/movie/969681' in url:
        with open(os.path.join(FIX, 'rogflix_969681.json')) as fh:
            resp.text = fh.read()
        resp.status_code = 200
        resp.json = lambda: json.loads(resp.text)
        return resp
    if 'master' in url and url.endswith('.m3u8'):
        with open(os.path.join(FIX, 'master_969681.m3u8')) as fh:
            resp.text = fh.read()
        resp.content = resp.text.encode()
        resp.headers = {}
        resp.status_code = 200
        return resp
    if 'index-v1' in url:
        with open(os.path.join(FIX, 'variant_969681.m3u8')) as fh:
            resp.text = fh.read()
        resp.content = resp.text.encode()
        resp.headers = {}
        resp.status_code = 200
        return resp
    if 'seg0.ts' in url or 'seg1.ts' in url:
        resp.content = b'\x47' + b'\x00' * 2047  # MPEG-TS sync byte
        resp.text = ''
        resp.headers = {'content-type': 'video/mp2t'}
        resp.status_code = 200
        return resp
    if 'pixel' in url:
        resp.content = ('\x89PNG\r\n\x1a\n' + '\x00' * 2040).encode('latin1')
        resp.text = ''
        resp.headers = {'content-type': 'image/png'}
        resp.status_code = 200
        return resp
    resp.status_code = 502
    resp.text = ''
    resp.json = lambda: {}
    return resp


class TestSubtitles(unittest.TestCase):
    def test_pick_english_first(self):
        from resources.lib.resolver import pick_subtitles
        entries = [
            {'lang': 'Spanish', 'url': 'https://x/es.vtt'},
            {'lang': 'English', 'url': 'https://x/en.vtt'},
            {'label': 'EN', 'file': 'https://x/en2.vtt'},
            {'lang': 'English', 'url': 'https://x/en.vtt'},  # dup
        ]
        subs = pick_subtitles(entries)
        self.assertEqual(subs[0], 'https://x/en.vtt')
        self.assertIn('https://x/en2.vtt', subs)
        self.assertEqual(len(subs), 3)

    @patch('resources.lib.resolver.requests.Session.get', side_effect=_fixture_router)
    def test_subtitles_harvested_from_later_servers(self, _mock):
        from resources.lib.resolver import StreamResolver
        r = StreamResolver()
        with patch.object(StreamResolver, '_vidnest_candidates') as mc:
            mc.return_value = iter([
                ('rogflix', {'url': 'https://cdn.test/a/master.m3u8'}),
                ('vidxyz', {'streams': [{'url': 'https://cdn.test/b/master.m3u8'}],
                            'subtitles': [{'lang': 'English',
                                           'url': 'https://cdn.test/en.vtt'}]}),
            ])
            with patch.object(StreamResolver, '_verify_m3u8', return_value=True):
                with patch.object(StreamResolver, '_vdrk_subtitles',
                                  return_value=[]) as vd:
                    url, _headers, subs = r.vidnest_stream('movie', '1')
                    self.assertEqual(url, 'https://cdn.test/a/master.m3u8')
                    self.assertEqual(list(subs), ['https://cdn.test/en.vtt'])
                    vd.assert_not_called()

    @patch('resources.lib.resolver.requests.Session.get', side_effect=_fixture_router)
    def test_vidnest_subtitles_flow_into_resolve(self, _mock):
        from resources.lib.resolver import StreamResolver
        r = StreamResolver()
        with patch.object(StreamResolver, '_vidnest_candidates') as mc:
            mc.return_value = iter([('vidxyz', {
                'streams': [{'url': 'https://akcloud.animanga.fun/hls/xyz/master.m3u8',
                             'type': 'hls'}],
                'subtitles': [{'lang': 'English',
                               'url': 'https://box.netrocdn.site/vtt/03/00003/x_eng.vtt'}],
            })])
            with patch.object(StreamResolver, '_verify_m3u8', return_value=True):
                url, _headers, subs = r.vidnest_stream('movie', '969681')
                self.assertEqual(url, 'https://akcloud.animanga.fun/hls/xyz/master.m3u8')
                self.assertEqual(list(subs), ['https://box.netrocdn.site/vtt/03/00003/x_eng.vtt'])

    @patch('resources.lib.resolver.requests.Session.get', side_effect=_fixture_router)
    def test_resolved_url_carries_subtitles(self, _mock):
        r = StreamResolver()
        url = r.resolve_stream({
            'name': 'Server 2', 'id': 'srv-2', 'num': '2',
            'page_url': 'https://fmoviess.org/film/burt-1423/',
        })
        self.assertTrue(hasattr(url, 'subtitles'))


class TestFilmMeta(unittest.TestCase):
    def test_parse_burt_fixture(self):
        from bs4 import BeautifulSoup
        from resources.lib.scraper import FMoviesScraper
        with open(os.path.join(FIX, 'film_burt.html'), encoding='utf-8') as fh:
            soup = BeautifulSoup(fh.read(), 'html.parser')
        meta = FMoviesScraper.parse_film_meta(soup, 'https://fmoviess.org/film/burt-1423/')
        self.assertEqual(meta['genres'], ['Comedy', 'Drama'])
        self.assertIn('Joe Burke', meta['directors'])
        self.assertTrue(any('Burton Berger' in a for a in meta['actors']))
        self.assertEqual(meta['countries'], ['United States'])
        self.assertEqual(meta['duration'], 1 * 3600 + 18 * 60)
        self.assertEqual(meta['year'], 2025)
        self.assertEqual(meta['rating'], 10.0)
        self.assertIn('musician', meta['synopsis'])
        self.assertTrue(meta['backdrop'].startswith('https://'))

    def test_add_dir_item_sets_rich_info(self):
        import sys as _sys
        recorded = {}

        class FakeTag:
            def __init__(self):
                self.set = {}
            def __getattr__(self, name):
                if name.startswith('set'):
                    def _set(value, _n=name):
                        self.set[_n] = value
                    return _set
                raise AttributeError(name)

        class FakeItem:
            def __init__(self, label=None):
                recorded['label'] = label
                self.props = {}
                self.tag = FakeTag()
            def setProperty(self, k, v):
                self.props[k] = v
            def setArt(self, art):
                recorded['art'] = art
            def setInfo(self, *a):
                recorded['setInfo'] = a
            def getVideoInfoTag(self):
                return self.tag
            def addContextMenuItems(self, items):
                pass

        added = {}

        class FakeGui:
            NOTIFICATION_INFO = 0
            ListItem = FakeItem
            def Dialog(self):
                return self

        class FakePlugin:
            @staticmethod
            def addDirectoryItem(handle=None, url=None, listitem=None, isFolder=None):
                added.update(url=url, item=listitem, isFolder=isFolder)

        prev_gui = _sys.modules.get('xbmcgui')
        prev_plugin = _sys.modules.get('xbmcplugin')
        _sys.modules['xbmcgui'] = FakeGui()
        _sys.modules['xbmcplugin'] = FakePlugin
        try:
            import importlib
            import resources.lib.kodi_utils as ku
            importlib.reload(ku)
            ku.add_dir_item(
                'Burt', {'action': 'play'}, is_folder=False, is_playable=True,
                art={'poster': 'p', 'fanart': 'f'},
                info={'title': 'Burt', 'mediatype': 'movie', 'plot': 'A story',
                      'genre': ['Comedy'], 'cast': ['Joe'],
                      'director': ['Dir'], 'country': ['US'],
                      'duration': 4680, 'year': 2025, 'rating': 8.1})
        finally:
            if prev_gui is not None:
                _sys.modules['xbmcgui'] = prev_gui
            if prev_plugin is not None:
                _sys.modules['xbmcplugin'] = prev_plugin
        tag = added['item'].tag.set
        self.assertEqual(tag.get('setPlot'), 'A story')
        self.assertEqual(tag.get('setGenres'), ['Comedy'])
        self.assertEqual(tag.get('setYear'), 2025)
        self.assertEqual(tag.get('setDuration'), 4680)
        self.assertEqual(tag.get('setRating'), 8.1)
        self.assertEqual(recorded['art']['fanart'], 'f')

    def test_enrich_items_uses_cache(self):
        import tempfile
        import main as _main
        from unittest.mock import patch as _patch
        tmp = tempfile.mkdtemp(prefix='fmovies_cache_')
        items = [{'title': 'Burt', 'url': 'https://fmoviess.org/film/burt-1423/',
                  'thumb': 't', 'mediatype': 'movie'}]
        fake_details = {'synopsis': 'Plot!', 'genres': ['Drama'], 'actors': [],
                        'directors': [], 'countries': [], 'duration': None,
                        'year': 2025, 'rating': None, 'backdrop': 'http://x/f.jpg'}
        with _patch.object(_main, 'get_cache_dir', return_value=tmp):
            with _patch('resources.lib.scraper.FMoviesScraper.get_details_and_seasons',
                        return_value=fake_details) as mg:
                out = _main.enrich_items([dict(i) for i in items])
                self.assertEqual(out[0]['plot'], 'Plot!')
                self.assertEqual(mg.call_count, 1)
                # second run: cache hit, no HTTP
                out2 = _main.enrich_items([dict(i) for i in items])
                self.assertEqual(out2[0]['plot'], 'Plot!')
                self.assertEqual(mg.call_count, 1)


class TestInfoDisplay(unittest.TestCase):
    def test_decode_html_fixes_mojibake(self):
        from resources.lib.scraper import decode_html
        resp = MagicMock()
        resp.content = 'Chloé Zhao – Parkinson’s'.encode('utf-8')
        resp.headers = {}
        resp.text = resp.content.decode('latin-1')
        self.assertEqual(decode_html(resp), 'Chloé Zhao – Parkinson’s')

    def test_build_display_plot_header(self):
        import main as _main
        plot = _main.build_display_plot({
            'plot': 'A story.',
            'genre': ['Biography', 'Drama', 'History'],
            'cast': ['Jessie Buckley', 'Paul Mescal'],
            'director': ['Chloé Zhao'],
            'country': ['United Kingdom', 'United States'],
            'duration': 7500,
            'year': 2025,
            'rating': 7.8,
            'quality': 'HD',
        })
        self.assertIn('Genre: Biography, Drama, History', plot)
        self.assertIn('Cast: Jessie Buckley, Paul Mescal', plot)
        self.assertIn('Director: Chloé Zhao', plot)
        self.assertIn('Country: United Kingdom, United States', plot)
        self.assertIn('2h 5m', plot)
        self.assertIn('2025', plot)
        self.assertIn('7.8/10', plot)
        self.assertTrue(plot.endswith('A story.'))
        self.assertEqual(_main.build_display_plot({}), '')


class TestTitleCleaning(unittest.TestCase):
    def test_clean_film_title(self):
        from resources.lib.resolver import clean_film_title
        self.assertEqual(
            clean_film_title('Watch The Gentlemen - Season 1 Full Movie on Fmovies.to'),
            'The Gentlemen - Season 1')
        self.assertEqual(clean_film_title('Watch Burt online | Fmovies'), 'Burt')
        self.assertEqual(clean_film_title('Spider-Man: Brand New Day 2026'),
                         'Spider-Man: Brand New Day 2026')


class TestOpenSubtitles(unittest.TestCase):
    @patch('resources.lib.resolver.requests.Session.get', side_effect=_fixture_router)
    def test_downloads_english_srt(self, _mock):
        import gzip
        import base64 as _b64
        import tempfile
        from resources.lib.resolver import StreamResolver
        srt = b'1\n00:00:01,000 --> 00:00:02,000\nHi\n'
        blob = _b64.b64encode(gzip.compress(srt)).decode()

        class FakeOS:
            def LogIn(self, *a):
                return {'status': '200 OK', 'token': 'tok'}
            def SearchSubtitles(self, tok, queries):
                q = queries[0]
                assert q.get('imdbid') == '123', q
                assert q.get('sublanguageid') == 'eng'
                return {'status': '200 OK', 'data': [
                    {'IDSubtitleFile': '11', 'SubDownloadsCnt': '5'},
                    {'IDSubtitleFile': '22', 'SubDownloadsCnt': '99'},
                ]}
            def DownloadSubtitles(self, tok, ids):
                assert ids == ['22'], ids
                return {'data': [{'data': blob}]}

        r = StreamResolver()
        with patch('xmlrpc.client.ServerProxy', return_value=FakeOS()):
            with patch.object(StreamResolver, '_os_imdb_id', return_value='123'):
                dest = tempfile.mkdtemp(prefix='fmovies_subs_')
                subs = r._opensubtitles_subs('movie', '999', dest_dir=dest)
                self.assertEqual(len(subs), 1)
                self.assertTrue(subs[0].endswith('.srt'))
                with open(subs[0], 'rb') as fh:
                    self.assertEqual(fh.read(), srt)

    @patch('resources.lib.resolver.requests.Session.get', side_effect=_fixture_router)
    def test_get_ids_reports_title(self, _mock):
        from resources.lib.resolver import StreamResolver
        ids = StreamResolver().get_ids('https://fmoviess.org/film/burt-1423/')
        self.assertIn('burt', ids['title'].lower())


class TestSegmentSniffing(unittest.TestCase):
    @patch('resources.lib.resolver.requests.Session.get')
    def test_rejects_pixel_poisoned_playlist(self, mock_get):
        # Variant playlist whose segments are 1x1 tracking PNGs (as seen
        # live on akcloud.animanga.fun) must be rejected.
        def route(u, *a, **k):
            resp = MagicMock()
            resp.status_code = 200
            if u.endswith('.m3u8'):
                resp.text = ('#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10.0,\n'
                             'https://cdn.test/pixel0.ts\n')
                resp.content = resp.text.encode()
                resp.headers = {}
            else:
                resp.content = ('\x89PNG\r\n\x1a\n' + '\x00' * 2040).encode('latin1')
                resp.text = ''
                resp.headers = {'content-type': 'image/png'}
            return resp
        mock_get.side_effect = route
        r = StreamResolver()
        self.assertFalse(r._verify_m3u8('https://cdn.test/master.m3u8', None))

    @patch('resources.lib.resolver.requests.Session.get', side_effect=_fixture_router)
    def test_accepts_real_media_segments(self, _mock):
        r = StreamResolver()
        self.assertTrue(r._verify_m3u8(
            'https://akcloud.animanga.fun/hls/xyz/master.m3u8', None))


class TestFullChain(unittest.TestCase):
    @patch('resources.lib.resolver.requests.Session.get', side_effect=_fixture_router)
    def test_get_ids_and_servers_from_real_film_page(self, _mock):
        r = StreamResolver()
        ids = r.get_ids('https://fmoviess.org/film/burt-1423/')
        self.assertEqual(ids['mid'], '1423')
        self.assertEqual(ids['mode'], 'movie')
        self.assertEqual(ids['episodes'][0]['num'], '1')
        servers = r.get_servers('https://fmoviess.org/film/burt-1423/')
        self.assertTrue(any(s['num'] == '2' for s in servers))

    @patch('resources.lib.resolver.requests.Session.get', side_effect=_fixture_router)
    def test_resolve_stream_end_to_end(self, _mock):
        r = StreamResolver()
        url = r.resolve_stream({
            'name': 'Server 2', 'id': 'srv-2', 'num': '2',
            'page_url': 'https://fmoviess.org/film/burt-1423/',
        })
        stream, _, _headers = url.partition('|')
        self.assertIn('akcloud.animanga.fun', stream)
        self.assertTrue(stream.startswith('https://'))
        self.assertIn('Referer=', _headers)


if __name__ == '__main__':
    unittest.main()
