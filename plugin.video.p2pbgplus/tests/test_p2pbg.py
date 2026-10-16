"""Tests for plugin.video.p2pbgplus.

The tracker/session/playback code is a fork of the working reference add-on
plugin.video.p2pbg 2026.09.24.01, so the network paths are exercised on the
real device; here the pure logic (URLs, parsing, filtering, ordering) and
the fork-fidelity invariants are tested offline.
"""
import ast
import os
import re
import sys
import unittest
from unittest.mock import MagicMock

ADDON = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ADDON)

from bs4 import BeautifulSoup

from resources.lib import p2pbg
from resources.lib.vpngate import VPNGate, parse_country

LIB = os.path.join(ADDON, 'resources', 'lib')


def _read(name):
    with open(os.path.join(LIB, name), encoding='utf-8') as handle:
        return handle.read()


def _function(source, name):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.unparse(node)
    raise AssertionError('function {} not found'.format(name))


# Lines that make up the working hand-off to Elementum, verbatim.
REQUIRED_PLAY_LINES = (
    "torrent_path = os.path.join(__profile__, \"elementum_temp.torrent\")",
    "uri = urllib.parse.quote_plus(torrent_path)",
    "elementum_url = f'plugin://plugin.video.elementum/play?uri={uri}'",
    "li = xbmcgui.ListItem(path=elementum_url)",
    "li.setProperty('IsPlayable', 'true')",
    "xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, li)",
)

# Tracker session set-up that the reference relies on.
REQUIRED_SESSION_LINES = (
    "'referer': 'https://www.p2pbg.com/'",
    "'host': 'www.p2pbg.com'",
    "data_token = r.text",
    "match_token = re.search('token\".+?\"(.+?)\"', data_token)",
    "s.post(baseurl + loginurl, data=values, headers=headers_new)",
)

SETTING_IDS = ('p2pbg_user', 'p2pbg_password', 'prefer_bgaudio', 'show_xxx',
               'vpn_country', 'firstrun', 'search_history', 'last_error',
               'last_play', 'last_listing', 'last_category', 'last_call',
               'last_table', 'last_items')


class TestForkFidelity(unittest.TestCase):
    def test_elementum_handoff_matches_reference(self):
        source = _read('playback.py')
        for line in REQUIRED_PLAY_LINES:
            self.assertIn(line, source, 'play path diverged: ' + line)

    def test_session_setup_matches_reference(self):
        source = _read('tracker.py')
        for line in REQUIRED_SESSION_LINES:
            self.assertIn(line, source, 'session setup diverged: ' + line)

    def test_play_writes_torrent_through_xbmcvfs(self):
        play_src = _function(_read('playback.py'), 'play')
        self.assertIn("xbmcvfs.File(torrent_path, 'wb')", play_src)

    def test_vpn_gate_runs_before_the_download(self):
        play_src = _function(_read('playback.py'), 'play')
        self.assertLess(play_src.index('vpn_check()'),
                        play_src.index('fetch_torrent'))

    def test_settings_ids_match_settings_xml(self):
        kodi_utils = _read('kodi_utils.py')
        with open(os.path.join(ADDON, 'resources', 'settings.xml'),
                  encoding='utf-8') as handle:
            settings_xml = handle.read()
        for setting_id in SETTING_IDS:
            self.assertIn('id="{}"'.format(setting_id), settings_xml)
            self.assertIn("'{}'".format(setting_id), kodi_utils)

    def test_listings_are_never_served_from_disk_cache(self):
        with open(os.path.join(ADDON, 'main.py'), encoding='utf-8') as handle:
            main_source = handle.read()
        self.assertIn('cacheToDisc=cache_to_disc', _read('kodi_utils.py'))
        self.assertIn('cache_to_disc=False', main_source)

    def test_no_dead_magnet_helper(self):
        for name in os.listdir(LIB):
            if name.endswith('.py'):
                source = _read(name)
                self.assertNotIn('def find_info_hash', source)
                self.assertNotIn('def torrent_url_to_magnet', source)

    def test_no_stale_setting_ids(self):
        source = '\n'.join(_read(name) for name in os.listdir(LIB)
                           if name.endswith('.py'))
        for stale in ("getSetting('username')", "getSetting('password')",
                      "getSetting('bg_aud')", "getSetting('xxx')",
                      "getSetting('searchlist')"):
            self.assertNotIn(stale, source, 'stale setting id: ' + stale)


class TestListingUrls(unittest.TestCase):
    """Listing/search URLs must mirror the tracker's own search form."""

    def test_category_url_matches_confirmed_form(self):
        self.assertEqual(
            p2pbg.listing_url('68'),
            'https://www.p2pbg.com/torrents?fakeusernameremembered=&'
            'fakepasswordremembered=&search=&category=68&active=1&hidexxx=1')

    def test_form_fields_always_present(self):
        url = p2pbg.listing_url('68')
        for field in ('fakeusernameremembered=', 'fakepasswordremembered=',
                      'search=', 'category=', 'active=1', 'hidexxx='):
            self.assertIn(field, url)

    def test_category_separators_stay_literal(self):
        url = p2pbg.listing_url('14;15;24')
        self.assertIn('category=14;15;24', url)
        self.assertNotIn('%3B', url)

    def test_bgaudio_and_xxx_flags(self):
        self.assertIn('bgaudio=1', p2pbg.listing_url('68', bgaudio=True))
        self.assertNotIn('bgaudio', p2pbg.listing_url('68'))
        self.assertIn('hidexxx=0', p2pbg.listing_url('68', show_xxx=True))
        self.assertIn('hidexxx=1', p2pbg.listing_url('68'))

    def test_4k_category_is_not_offered(self):
        self.assertNotIn('60', p2pbg.ALL_CATEGORIES.split(';'))
        self.assertNotIn('60', [cid for cid, _ in p2pbg.CATEGORIES])

    def test_search_value_and_replacement(self):
        base = p2pbg.listing_url('68;60', bgaudio=True)
        self.assertEqual(p2pbg.search_value(base), '')
        searched = p2pbg.with_search(base, 'silo s03')
        self.assertIn('search=silo s03', searched)
        self.assertIn('category=68;60', searched)
        self.assertIn('active=1', searched)
        self.assertIn('hidexxx=1', searched)
        self.assertEqual(p2pbg.search_value(searched), 'silo s03')

    def test_search_replacement_appends_when_absent(self):
        self.assertEqual(
            p2pbg.with_search('https://x/torrents?category=68', 'a'),
            'https://x/torrents?category=68&search=a')

    def test_to_int_never_raises(self):
        for value, expected in (('21', 21), ('---', 0), ('', 0), ('  ', 0),
                                (None, 0), ('1 234', 1234), ('1,024', 1024)):
            self.assertEqual(p2pbg.to_int(value), expected)


class TestQualityFilter(unittest.TestCase):
    def test_4k_is_excluded(self):
        for title in ('Movie.2024.2160p.WEB-DL', 'Movie.2024.4K.HDR',
                      'Movie.UHD.BluRay', 'Movie.2024.3840p'):
            self.assertTrue(p2pbg.is_excluded(title), title)

    def test_hd_is_kept(self):
        for title in ('Movie.2024.1080p.WEB-DL', 'Movie.2024.720p',
                      'Show.S03E10.1080p', 'Movie.1080i'):
            self.assertFalse(p2pbg.is_excluded(title), title)

    def test_parse_row_drops_4k(self):
        row = BeautifulSoup(
            '<tr><td>x</td><td><a onclick="showPreview(\''
            + 'a' * 40 + '\')" href="#">Movie.2024.2160p</a></td><td>dl</td>'
            '<td>1</td><td>04/09/2026</td><td>8 GB</td><td>15</td><td>0</td>'
            '<td>2</td></tr>', 'html.parser').find('tr')
        details = {'torrent_url': 'https://www.p2pbg.com/download.php?id=x'}
        self.assertIsNone(p2pbg.parse_row(row, details))


class TestSorting(unittest.TestCase):
    def test_rows_sorted_by_seeders_then_leechers(self):
        rows = [
            {'title': 'b', 'seeders': 5, 'leechers': 1},
            {'title': 'a', 'seeders': 5, 'leechers': 9},
            {'title': 'c', 'seeders': 20, 'leechers': 0},
            {'title': 'd', 'seeders': 0, 'leechers': 0},
        ]
        ordered = [r['title'] for r in p2pbg.sort_rows(rows)]
        self.assertEqual(ordered, ['c', 'a', 'b', 'd'])


class TestParseDetails(unittest.TestCase):
    HTML = ('<a href="https://www.imdb.com/title/tt7126948/">imdb</a>'
            '<a href="https://www.p2pbg.com/download.php?id=abc&amp;'
            'f=Movie.torrent">dl</a>'
            '<div class="torrent-preview-fact__label">Година</div>'
            '<div class="torrent-preview-fact__value">2020</div>'
            '<div class="torrent-preview-fact__label">Жанр</div>'
            '<div class="torrent-preview-fact__value">Action</div>')

    def test_fields(self):
        details = p2pbg.parse_details(self.HTML)
        self.assertEqual(details['imdb_id'], 'tt7126948')
        self.assertIn('download.php?id=abc', details['torrent_url'])
        self.assertEqual(details['year'], '2020')
        self.assertEqual(details['genre'], 'Action')


class TestQueryRecovery(unittest.TestCase):
    """A listing address must be recoverable from a mangled plugin query."""

    def setUp(self):
        self.listing = ('https://www.p2pbg.com/torrents?'
                        'fakeusernameremembered=&fakepasswordremembered=&search=&'
                        'category=68&active=1&hidexxx=1')

    def _enc(self, url):
        for char, code in ((':', '%3A'), ('/', '%2F'), ('?', '%3F'),
                           ('&', '%26'), ('=', '%3D'), (' ', '%20')):
            url = url.replace(char, code)
        return url

    def test_normal_query(self):
        self.assertEqual(
            p2pbg.recover_listing_url('?url=' + self._enc(self.listing)),
            self.listing)

    def test_mode_lost(self):
        self.assertEqual(
            p2pbg.recover_listing_url(
                '?url=%s&mode=1&name=x' % self._enc(self.listing)),
            self.listing)

    def test_double_encoded_query(self):
        mangled = self._enc(self.listing).replace('%3D', '%253D') \
            .replace('%3F', '%253F')
        self.assertEqual(
            p2pbg.recover_listing_url('?url=' + mangled), self.listing)

    def test_query_with_spaces_kept(self):
        listing = self.listing.replace('search=', 'search=silo s03')
        self.assertEqual(
            p2pbg.recover_listing_url('?url=' + self._enc(listing)),
            listing)

    def test_nothing_to_recover(self):
        for query in ('', '?mode=1&name=x', '?url=not-a-url&mode=1'):
            self.assertEqual(p2pbg.recover_listing_url(query), '')


class TestRowParsing(unittest.TestCase):
    """Column layout of the current results table."""

    HTML = ('<table class="torrent-index__table">'
            '<thead><tr>' + ''.join('<th>%s</th>' % h for h in
                                    ['Кат', 'Име на файл', 'Свали', 'Ком',
                                     'Добавен', 'Размер', 'S', 'L', 'D'])
            + '</tr></thead><tbody>'
            '<tr><td>x</td><td><a onclick="showPreview(\'' + 'a' * 40 +
            '\')" href="#">Silo.S03E10.1080p</a></td><td>Свали</td><td>4</td>'
            '<td>04/09/2026</td><td>8.98 GB</td><td>15</td><td>0</td>'
            '<td>289</td></tr>'
            '<tr><td colspan="9">spacer</td></tr>'
            '</tbody></table>')

    def test_column_indices(self):
        source = _read('p2pbg.py')
        self.assertIn("'size': cols[5]", source)
        self.assertIn("'seeders': to_int(cols[6]", source)
        self.assertIn("'leechers': to_int(cols[7]", source)
        self.assertNotIn("'size': cols[6]", source)

    def test_rows_shorter_than_nine_cells_are_skipped(self):
        self.assertIn('if len(cols) < 9:', _read('p2pbg.py'))

    def test_malformed_row_cannot_abort_the_listing(self):
        source = _read('tracker.py')
        self.assertIn('except Exception as exc:', source)
        self.assertIn('row skipped', source)

    def test_results_table_prefers_the_full_table(self):
        soup = BeautifulSoup(
            '<table class="torrent-index__table '
            'torrent-index__table--recommended"><tbody>'
            '<tr><td colspan="9">a</td></tr></tbody></table>'
            + self.HTML, 'html.parser')
        table = p2pbg.find_results_table(soup)
        self.assertEqual(p2pbg.data_row_count(table), 1)

    def test_parse_row_reads_columns_and_flags(self):
        row = BeautifulSoup(self.HTML, 'html.parser').find_all('tr')[1]
        details = {'torrent_url': 'https://www.p2pbg.com/download.php?id=x',
                   'imdb_id': 'tt1', 'year': '2020', 'genre': 'Action',
                   'release': 'R', 'video': 'V', 'synopsis': 'S'}
        parsed = p2pbg.parse_row(row, details)
        self.assertEqual(parsed['title'], 'Silo.S03E10.1080p')
        self.assertEqual(parsed['seeders'], 15)
        self.assertEqual(parsed['leechers'], 0)
        self.assertEqual(parsed['size'], '8.98 GB')
        self.assertEqual(parsed['imdb_id'], 'tt1')


class TestVPNGate(unittest.TestCase):
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

    def test_custom_country(self):
        gate = VPNGate(country='us', cache_ttl=0)
        fake = MagicMock()
        fake.json.return_value = {'country': 'US'}
        gate._get = MagicMock(return_value=fake)
        self.assertEqual(gate.check(), (True, 'US'))


if __name__ == '__main__':
    unittest.main()
