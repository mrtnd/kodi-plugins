"""Unit tests for plugin.video.p2pbg (sanitized fixtures, no session data)."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from resources.lib.p2pbg import (
    CATEGORIES, P2PBGClient, parse_details, parse_next_page,
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

# Homepage markup as the tracker serves it: the CSRF token lives in a meta
# tag, not in a form field (that is what the reference plugin parses).
HOME_HTML = """
<html><head><meta name="csrf-token" content="TOKEN123"></head>
<body><a href="/logout">logout</a></body></html>
"""


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

    def test_new_style_preview_rows(self):
        from resources.lib.p2pbg import _row_identity
        from bs4 import BeautifulSoup
        html = ('<table class="torrent-index__table"><thead><tr><th>Кат</th>'
                '<th>Име на файл</th><th>Свали</th><th>Ком</th><th>Добавен</th>'
                '<th>Размер</th><th>S</th><th>L</th><th>D</th></tr></thead><tbody>'
                '<tr class="torrent-index__row" data-preview-card="' + 'd' * 40 + '">'
                '<td class="torrent-index__col-icon">x</td>'
                '<td class="torrent-index__name-cell"><div><a href="/torrents?search=silo" '
                'onclick="showPreview(\'' + 'd' * 40 + '\'); return false;">Silo S03 1080p</a></div></td>'
                '<td>dl</td><td>---</td><td>13/09/2026</td><td>4.42 GB</td>'
                '<td>21</td><td>1</td><td>108</td></tr>'
                '</tbody></table>')
        soup = BeautifulSoup(html, 'html.parser')
        items = parse_search_rows(html, 'https://www.p2pbg.com')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], 'd' * 40)
        self.assertEqual(items[0]['title'], 'Silo S03 1080p')
        self.assertEqual(items[0]['seeders'], 21)
        tid, title = _row_identity(soup.select_one('tr.torrent-index__row'))
        self.assertEqual((tid, title), ('d' * 40, 'Silo S03 1080p'))

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

    def test_listing_url_keeps_separators(self):
        from resources.lib.p2pbg import P2PBGClient
        client = P2PBGClient()
        url = client.listing_url(query='silo s03', bgaudio=True)
        self.assertIn('category=68;60;67;34;14;24', url)
        self.assertIn('bgaudio=1', url)
        self.assertIn('search=silo s03', url)
        self.assertNotIn('%3B', url)

    def test_filter_relevant(self):
        from resources.lib.p2pbg import filter_relevant
        items = [{'title': 'Silo S03 1080p'}, {'title': 'Gentlemen S02'},
                 {'title': 'Silo S02 720p'}]
        out = filter_relevant(items, 'silo')
        self.assertEqual(len(out), 2)
        self.assertEqual(filter_relevant(items, 'zzz-no-match'), items)
        self.assertEqual(len(filter_relevant(items, '')), 3)


class TestDetailsParse(unittest.TestCase):
    def test_details(self):
        details = parse_details(DETAILS_HTML, 'https://www.p2pbg.com', 'a' * 40)
        self.assertIn('download.php?id=' + 'a' * 40, details['torrent_url'])
        self.assertNotIn('&amp;', details['torrent_url'])
        self.assertEqual(details['info_hash'], 'a' * 40)
        self.assertEqual(len(details['files']), 2)


class TestEnrich(unittest.TestCase):
    """Listing rows are enriched with their details-page download link."""

    def test_attaches_download_link_and_plot(self):
        from resources.lib.playback import _enrich
        client = MagicMock()
        client.details.return_value = {
            'torrent_url': 'https://x/download.php?id=1', 'imdb': 'tt1',
            'info_hash': 'f' * 40, 'meta': {'Година': '2026'},
            'files': [{'name': 'a.mkv'}, {'name': 'b.mkv'}]}
        items = [{'id': 'a' * 40, 'title': 'Silo'}]
        _enrich(client, items)
        self.assertEqual(items[0]['torrent_url'],
                         'https://x/download.php?id=1')
        self.assertEqual(items[0]['imdb'], 'tt1')
        self.assertIn('2026', items[0]['plot'])
        self.assertIn('2', items[0]['plot'])

    def test_one_bad_row_keeps_the_rest(self):
        from resources.lib.playback import _enrich
        client = MagicMock()
        client.details.side_effect = [
            Exception('boom'),
            {'torrent_url': 'https://x/d', 'info_hash': '', 'meta': {},
             'files': []}]
        items = [{'id': 'a' * 40, 'title': 'A'}, {'id': 'b' * 40, 'title': 'B'}]
        _enrich(client, items)
        self.assertEqual(items[0].get('torrent_url', ''), '')
        self.assertEqual(items[1]['torrent_url'], 'https://x/d')

    def test_auth_error_is_not_swallowed(self):
        from resources.lib.playback import _enrich
        from resources.lib.p2pbg import AuthError
        client = MagicMock()
        client.details.side_effect = AuthError('expired')
        with self.assertRaises(AuthError):
            _enrich(client, [{'id': 'a' * 40, 'title': 'A'}])


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


class TestPlayback(unittest.TestCase):
    """VPN gate -> .torrent bytes -> staged file -> Elementum resolve."""

    def _client(self, raw=b'd4:infod4:name4:teste', error=''):
        client = MagicMock()
        client.details.return_value = {
            'torrent_url': 'https://x/download.php?id=' + 'a' * 40,
            'info_hash': 'a' * 40, 'meta': {}, 'files': [{'name': 'x.mkv'}]}
        client.download_torrent.return_value = (raw, error)
        return client

    def _play(self, client, **kwargs):
        from resources.lib import playback
        args = {'tid': 'a' * 40, 'title': 'Show',
                'torrent_url': 'https://x/download.php?id=1'}
        args.update(kwargs)
        with patch('resources.lib.playback.VPNGate') as gate_cls, \
                patch('resources.lib.playback.get_profile_dir',
                      return_value='/tmp/p2pbgtest'), \
                patch('resources.lib.playback._stage_torrent',
                      return_value='/tmp/p2pbgtest/a.torrent'), \
                patch('resources.lib.playback.show_blocking') as blocked, \
                patch('resources.lib.kodi_utils.resolve_play') as resolved:
            gate_cls.return_value.check.return_value = (True, 'BG')
            playback.play(client, **args)
        self.blocked = blocked
        return resolved

    def test_resolves_elementum_with_staged_torrent(self):
        from resources.lib import playback
        raw = b'd4:infod4:name4:teste'
        with patch('resources.lib.playback.VPNGate') as gate_cls, \
                patch('resources.lib.playback.get_profile_dir',
                      return_value='/tmp/p2pbgtest'), \
                patch('resources.lib.playback._stage_torrent',
                      return_value='/tmp/p2pbgtest/a.torrent') as stage, \
                patch('resources.lib.kodi_utils.resolve_play') as resolved:
            gate_cls.return_value.check.return_value = (True, 'BG')
            playback.play(self._client(raw), 'a' * 40, 'Show',
                          'https://x/download.php?id=1')
        stage.assert_called_once_with(raw, 'a' * 40)
        self.assertEqual(resolved.call_args[0][0],
                         'file:///tmp/p2pbgtest/a.torrent')
        self.assertEqual(resolved.call_args[0][1], 'Show')

    def test_stages_real_bytes_into_the_profile_dir(self):
        import tempfile
        from resources.lib import playback
        raw = b'd4:infod4:name4:teste'
        with tempfile.TemporaryDirectory() as tmp:
            with patch('resources.lib.playback.get_profile_dir',
                       return_value=tmp):
                path = playback._stage_torrent(raw, 'b' * 40)
            with open(path, 'rb') as handle:
                self.assertEqual(handle.read(), raw)
        self.assertTrue(path.endswith('b' * 40 + '.torrent'))

    def test_resolves_details_when_url_is_missing(self):
        client = self._client()
        resolved = self._play(client, torrent_url='')
        self.assertTrue(client.details.called)
        self.assertTrue(resolved.called)
        self.assertEqual(resolved.call_args[0][0],
                         'file:///tmp/p2pbgtest/a.torrent')

    def test_vpn_gate_blocks_playback(self):
        from resources.lib import playback
        client = self._client()
        with patch('resources.lib.playback.VPNGate') as gate_cls, \
                patch('resources.lib.playback.show_blocking') as blocked:
            gate_cls.return_value.check.return_value = (False, 'DE')
            playback.play(client, 'a' * 40, 'Show', 'https://x/d.torrent')
        self.assertTrue(blocked.called)
        self.assertFalse(client.download_torrent.called)

    def test_bad_download_falls_back_to_magnet(self):
        client = self._client(raw=b'<html>error', error='not a torrent file')
        client.details.return_value = {
            'torrent_url': '', 'info_hash': 'a' * 40, 'meta': {}, 'files': []}
        resolved = self._play(client)
        self.assertTrue(resolved.call_args[0][0].startswith(
            'magnet:?xt=urn:btih:' + 'a' * 40))

    def test_missing_download_link_blocks(self):
        from resources.lib import playback
        client = self._client()
        client.details.return_value = {'torrent_url': '', 'info_hash': '',
                                       'meta': {}, 'files': []}
        with patch('resources.lib.playback.VPNGate') as gate_cls, \
                patch('resources.lib.playback.show_blocking') as blocked:
            gate_cls.return_value.check.return_value = (True, 'BG')
            playback.play(client, 'a' * 40, 'Show', '')
        self.assertTrue(blocked.called)

    def test_build_plot_from_details(self):
        from resources.lib.playback import build_plot
        plot = build_plot({'imdb': 'tt7126948',
                           'meta': {'Година': '2020', 'Жанр': 'Action',
                                    'Релийз': 'BDRip', 'Резюме': 'A woman.'},
                           'files': [{'name': 'a.mkv'}]})
        self.assertIn('Релийз: BDRip', plot)
        self.assertIn('2020', plot)
        self.assertIn('IMDb: tt7126948', plot)
        self.assertIn('A woman.', plot)
        self.assertEqual(build_plot({}), '')


class TestLogin(unittest.TestCase):
    def test_token_extraction_and_post(self):
        from resources.lib.p2pbg import P2PBGClient
        client = P2PBGClient(username='u', password='p')
        get_resp = MagicMock()
        get_resp.text = HOME_HTML
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
