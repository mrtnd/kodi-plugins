"""Unit tests for plugin.video.p2pbg (sanitized fixtures, no session data)."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from resources.lib import torrentfile
from resources.lib.p2pbg import (
    CATEGORIES, parse_details, parse_next_page,
    parse_search_rows, rank_items,
)
from resources.lib.vpngate import VPNGate, parse_country

SEARCH_HTML = '''
<html><body><table>
<thead><tr><th>Кат</th><th>Име на файл</th><th>Свали</th><th>Ком</th>
<th>Добавен</th><th>Размер</th><th>S</th><th>L</th><th>D</th></tr></thead>
<tbody>
<tr><td>1</td>
<td><div><a href="https://www.p2pbg.com/torrents/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa">Example.Show.S01.1080p.WEB.H264-GRP</a><div><img src="/img/bgaudio.gif"></div></div></td>
<td>dl</td><td>2</td><td>01/09/26</td><td>4.20 GB</td><td>15</td><td>3</td><td>100</td></tr>
<tr><td>1</td>
<td><a href="https://www.p2pbg.com/torrents/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb">Example.Show.S01.1080p.BG.AUDIO-WEB</a></td>
<td>dl</td><td>0</td><td>02/09/26</td><td>4.50 GB</td><td>7</td><td>1</td><td>20</td></tr>
<tr><td>1</td>
<td><a href="https://www.p2pbg.com/torrents/cccccccccccccccccccccccccccccccccccccccc">Dead.Show.S01.480p-OLD</a></td>
<td>dl</td><td>0</td><td>01/01/20</td><td>700 MB</td><td>0</td><td>0</td><td>5</td></tr>
</tbody></table></body></html>
'''

DETAILS_HTML = '''
<html><body><h1>Example Show S01</h1>
<a href="https://www.p2pbg.com/download.php?id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&amp;f=Example.torrent">dl</a>
<span class="torrent-show__info-hash">aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa</span>
<div class="torrent-show__file-row"><span class="torrent-show__file-name">show.s01e01.mkv</span><span class="torrent-show__file-size">4.20 GB</span></div>
<div class="torrent-show__file-row"><span class="torrent-show__file-name">sample.mkv</span><span class="torrent-show__file-size">50 MB</span></div>
</body></html>
'''

LOGIN_HTML = '''
<html><body><form method="post" action="https://www.p2pbg.com/login">
<input type="hidden" name="_token" value="TOKEN123">
<input type="text" name="uid"><input type="password" name="pwd">
</form></body></html>
'''


def _benc(value):
    if isinstance(value, int):
        return b'i' + str(value).encode() + b'e'
    if isinstance(value, bytes):
        return str(len(value)).encode() + b':' + value
    if isinstance(value, str):
        raw = value.encode()
        return str(len(raw)).encode() + b':' + raw
    if isinstance(value, list):
        return b'l' + b''.join(_benc(v) for v in value) + b'e'
    if isinstance(value, dict):
        out = b'd'
        for key in sorted(value):
            out += _benc(key) + _benc(value[key])
        return out + b'e'
    raise TypeError(type(value))


def _sample_torrent():
    info = {b'name': b'show', b'piece length': 262144, b'pieces': b'0' * 20,
            b'files': [{b'path': [b'show.s01e01.mkv'], b'length': 100},
                        {b'path': [b'sample.mkv'], b'length': 5}]}
    return _benc({b'announce': b'https://tracker.example/announce?passkey=KP',
                  b'info': info})


class TestSearchParse(unittest.TestCase):
    def test_rows(self):
        items = parse_search_rows(SEARCH_HTML, 'https://www.p2pbg.com')
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]['id'], 'a' * 40)
        self.assertIn('Example.Show', items[0]['title'])
        self.assertEqual(items[0]['seeders'], 15)
        self.assertEqual(items[0]['leechers'], 3)
        self.assertEqual(items[0]['size'], '4.20 GB')

    def test_rank_filters_dead_and_prefers_bg(self):
        items = parse_search_rows(SEARCH_HTML, 'https://www.p2pbg.com')
        ranked = rank_items(items, min_seeders=1, prefer_bgaudio=True)
        self.assertEqual(len(ranked), 2)
        self.assertIn('BG', ranked[0]['title'])

    def test_empty_table(self):
        self.assertEqual(parse_search_rows('<html></html>', 'https://x'), [])

    def test_poster_flags_and_next_page(self):
        from resources.lib.p2pbg import _row_has_flag, _row_poster, BGAUDIO_FLAGS
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(SEARCH_HTML, 'html.parser')
        tr = soup.select('tbody tr')[0]
        self.assertTrue(_row_has_flag(tr, BGAUDIO_FLAGS))
        self.assertEqual(_row_poster(tr), '')
        page = ('<html><body><a href="/torrents?search=x&page=2">&gt;</a>'
                '</body></html>')
        self.assertEqual(
            parse_next_page(page, 'https://www.p2pbg.com'),
            'https://www.p2pbg.com/torrents?search=x&page=2')
        self.assertEqual(parse_next_page('<html></html>', 'https://x'), '')

    def test_categories_cover_video(self):
        ids = ';'.join(cat for cat, _ in CATEGORIES)
        for want in ['68', '60', '14', '24', '5', '57']:
            self.assertIn(want, ids)


class TestDetailsParse(unittest.TestCase):
    def test_details(self):
        details = parse_details(DETAILS_HTML, 'https://www.p2pbg.com', 'a' * 40)
        self.assertIn('download.php?id=' + 'a' * 40, details['torrent_url'])
        self.assertNotIn('&amp;', details['torrent_url'])
        self.assertEqual(details['info_hash'], 'a' * 40)
        self.assertEqual(len(details['files']), 2)


class TestTorrentFile(unittest.TestCase):
    def test_roundtrip_and_video_files(self):
        raw = _sample_torrent()
        meta = torrentfile.bdecode(raw)
        entries = torrentfile.file_entries(meta)
        self.assertEqual(len(entries), 2)
        videos = torrentfile.video_files(entries)
        self.assertEqual([v[0] for v in videos], [0, 1])
        self.assertTrue(videos[0][1].endswith('.mkv'))

    def test_no_video(self):
        entries = [('readme.txt', 10), ('cover.jpg', 20)]
        self.assertEqual(torrentfile.video_files(entries), [])


class TestGate(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_country({'country': 'bg'}), 'BG')
        self.assertEqual(parse_country({}), '')
        self.assertEqual(parse_country(None), '')

    def test_match_and_cache(self):
        gate = VPNGate(country='BG', cache_ttl=300)
        fake = MagicMock()
        fake.json.return_value = {'country': 'BG'}
        gate._get = MagicMock(return_value=fake)
        self.assertEqual(gate.check(), (True, 'BG'))
        fake.json.return_value = {'country': 'DE'}
        self.assertEqual(gate.check(), (True, 'BG'))  # cached

    def test_mismatch_and_fail_closed(self):
        gate = VPNGate(country='BG', cache_ttl=0)
        fake = MagicMock()
        fake.json.return_value = {'country': 'DE'}
        gate._get = MagicMock(return_value=fake)
        self.assertEqual(gate.check()[0], False)
        gate._get = MagicMock(side_effect=ConnectionError('down'))
        self.assertEqual(gate.check(), (False, 'check failed'))


class TestFileSelection(unittest.TestCase):
    def _client(self, raw):
        client = MagicMock()
        client.details.return_value = {'torrent_url': 'https://x/y.torrent'}
        client.download_torrent.return_value = raw
        return client

    def _boxset_raw(self):
        info = {b'name': b'pack', b'piece length': 262144, b'pieces': b'0' * 20,
                b'files': [{b'path': [b'show.s03e01.mkv'], b'length': 100},
                            {b'path': [b'show.s03e02.mkv'], b'length': 200},
                            {b'path': [b'cover.jpg'], b'length': 3}]}
        return _benc({b'announce': b'https://t/x', b'info': info})

    def test_single_video_autoplays(self):
        from resources.lib import playback
        seen = {}

        class FakeItem:
            def __init__(self, path=None):
                seen['path'] = path

        with patch('resources.lib.playback.VPNGate') as gate_cls, \
                patch('resources.lib.playback.get_profile_dir',
                      return_value='/tmp'), \
                patch('xbmcgui.ListItem', FakeItem), \
                patch('xbmcplugin.setResolvedUrl') as resolved, \
                patch('builtins.open', unittest.mock.mock_open()):
            gate_cls.return_value.check.return_value = (True, 'BG')
            playback.play_torrent(self._client(_sample_torrent()),
                                  'a' * 40, 'Show')
        self.assertIn('plugin://plugin.video.elementum/play?uri=', seen['path'])
        self.assertTrue(resolved.called)

    def test_multi_video_lists_files(self):
        from resources.lib import playback
        listed = []
        with patch('resources.lib.playback.VPNGate') as gate_cls:
            gate_cls.return_value.check.return_value = (True, 'BG')
            with patch('resources.lib.kodi_utils.add_dir_item',
                       side_effect=lambda *a, **k: listed.append(a)):
                with patch('resources.lib.kodi_utils.end_directory'):
                    playback.list_files(self._client(self._boxset_raw()),
                                        'b' * 40, 'Pack')
        titles = [call[0] for call in listed]
        self.assertEqual(len(titles), 2)
        self.assertTrue(any('s03e01' in t for t in titles))
        self.assertTrue(any('s03e02' in t for t in titles))

    def test_no_video_blocks(self):
        from resources.lib import playback
        info = {b'name': b'x', b'piece length': 1, b'pieces': b'0' * 20,
                b'files': [{b'path': [b'readme.txt'], b'length': 5}]}
        raw = _benc({b'announce': b'https://t/x', b'info': info})
        with patch('resources.lib.playback.VPNGate') as gate_cls, \
                patch('resources.lib.playback.show_blocking') as blocked:
            gate_cls.return_value.check.return_value = (True, 'BG')
            playback.list_files(self._client(raw), 'c' * 40, 'Pack')
        self.assertTrue(blocked.called)


class TestLogin(unittest.TestCase):
    def test_token_extraction_and_post(self):
        from resources.lib.p2pbg import P2PBGClient
        client = P2PBGClient(username='u', password='p')
        get_resp = MagicMock()
        get_resp.text = LOGIN_HTML
        get_resp.raise_for_status = lambda: None
        post_resp = MagicMock()
        post_resp.text = '<a href="/logout">out</a>'
        post_resp.raise_for_status = lambda: None
        client.session.get = MagicMock(return_value=get_resp)
        client.session.post = MagicMock(return_value=post_resp)
        client.login()
        _, kwargs = client.session.post.call_args
        self.assertEqual(kwargs['data']['_token'], 'TOKEN123')
        self.assertEqual(kwargs['data']['uid'], 'u')
        self.assertEqual(kwargs['data']['pwd'], 'p')


if __name__ == '__main__':
    unittest.main()
