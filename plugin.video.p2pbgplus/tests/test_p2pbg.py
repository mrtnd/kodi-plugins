"""Tests for plugin.video.p2pbgplus.

The browsing/search/playback code is a fork of the working reference add-on
plugin.video.p2pbg 2026.09.24.01, so it is exercised on the real device rather
than here (it performs a tracker login at import time). What is tested
offline:

* the VPN country gate, which is the only behaviour added on the play path;
* fork fidelity - the Elementum hand-off in main.py must keep matching the
  reference, since every divergence from it cost playback in the field.
"""
import ast
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from resources.lib.vpngate import VPNGate, parse_country

MAIN = os.path.join(os.path.dirname(__file__), '..', 'main.py')

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


def _source():
    with open(MAIN, encoding='utf-8') as handle:
        return handle.read()


def _function(name):
    tree = ast.parse(_source())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError('function {} not found in main.py'.format(name))


def _load(*names):
    """Execute pure helper functions from main.py without importing it.

    main.py logs into the tracker at import time, so the offline-checkable
    helpers are lifted out of the AST instead.
    """
    from bs4 import BeautifulSoup  # noqa: F401  (used by the helpers)
    import urllib.parse
    namespace = {'baseurl': 'https://www.p2pbg.com', 'urllib': urllib.parse}
    for name in names:
        node = _function(name)
        exec(compile(ast.Module([node], []), 'main.py', 'exec'), namespace)
    return namespace


class TestForkFidelity(unittest.TestCase):
    def test_elementum_handoff_matches_reference(self):
        source = _source()
        for line in REQUIRED_PLAY_LINES:
            self.assertIn(line, source, 'play path diverged: ' + line)

    def test_session_setup_matches_reference(self):
        source = _source()
        for line in REQUIRED_SESSION_LINES:
            self.assertIn(line, source, 'session setup diverged: ' + line)

    def test_play_writes_torrent_through_xbmcvfs(self):
        play_src = ast.unparse(_function('PLAY'))
        self.assertIn("xbmcvfs.File(torrent_path, 'wb')", play_src)

    def test_vpn_gate_runs_before_the_download(self):
        play_src = ast.unparse(_function('PLAY'))
        self.assertLess(play_src.index('VPN_CHECK()'),
                        play_src.index('s.get(torrent_url'))

    def test_settings_ids_match_settings_xml(self):
        source = _source()
        with open(os.path.join(os.path.dirname(MAIN), 'resources',
                               'settings.xml'), encoding='utf-8') as handle:
            settings_xml = handle.read()
        for setting_id in ('p2pbg_user', 'p2pbg_password', 'prefer_bgaudio',
                           'show_xxx', 'vpn_country', 'search_history',
                           'firstrun', 'last_error', 'last_play'):
            self.assertIn('id="{}"'.format(setting_id), settings_xml)
            self.assertIn("getSetting('{}')".format(setting_id), source)

    def test_no_dead_magnet_helper(self):
        self.assertNotIn('def find_info_hash', _source())
        self.assertNotIn('def torrent_url_to_magnet', _source())

    def test_no_stale_setting_ids(self):
        source = _source()
        for stale in ("getSetting('username')", "getSetting('password')",
                      "getSetting('bg_aud')", "getSetting('xxx')",
                      "getSetting('searchlist')"):
            self.assertNotIn(stale, source, 'stale setting id: ' + stale)


class TestListingUrls(unittest.TestCase):
    """Listing/search URLs must mirror the tracker's own search form."""

    def setUp(self):
        self.ns = _load('listing_url', 'search_value', 'with_search', 'to_int')

    def test_category_url_matches_confirmed_form(self):
        url = self.ns['listing_url']('68')
        self.assertEqual(
            url,
            'https://www.p2pbg.com/torrents?fakeusernameremembered=&'
            'fakepasswordremembered=&search=&category=68&active=1&hidexxx=1')

    def test_form_fields_always_present(self):
        url = self.ns['listing_url'](self.ns['latest_categories'] if
                                      'latest_categories' in self.ns else '68')
        for field in ('fakeusernameremembered=', 'fakepasswordremembered=',
                      'search=', 'category=', 'active=1', 'hidexxx='):
            self.assertIn(field, url)

    def test_category_separators_stay_literal(self):
        url = self.ns['listing_url']('14;15;24')
        self.assertIn('category=14;15;24', url)
        self.assertNotIn('%3B', url)

    def test_bgaudio_and_xxx_flags(self):
        self.assertIn('bgaudio=1', self.ns['listing_url']('68', bgaudio=True))
        self.assertNotIn('bgaudio', self.ns['listing_url']('68'))
        self.assertIn('hidexxx=0', self.ns['listing_url']('68', show_xxx=True))
        self.assertIn('hidexxx=1', self.ns['listing_url']('68'))

    def test_search_value_and_replacement(self):
        base = self.ns['listing_url']('68;60', bgaudio=True)
        self.assertEqual(self.ns['search_value'](base), '')
        searched = self.ns['with_search'](base, 'silo s03')
        self.assertIn('search=silo s03', searched)
        self.assertIn('category=68;60', searched)
        self.assertIn('active=1', searched)
        self.assertIn('hidexxx=1', searched)
        self.assertEqual(self.ns['search_value'](searched), 'silo s03')

    def test_search_replacement_appends_when_absent(self):
        self.assertEqual(
            self.ns['with_search']('https://x/torrents?category=68', 'a'),
            'https://x/torrents?category=68&search=a')

    def test_to_int_never_raises(self):
        for value, expected in (('21', 21), ('---', 0), ('', 0), ('  ', 0),
                                (None, 0), ('1 234', 1234), ('1,024', 1024)):
            self.assertEqual(self.ns['to_int'](value), expected)


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

    def setUp(self):
        self.ns = _load('data_row_count', 'find_results_table', 'to_int')

    def test_column_indices(self):
        play_src = _source()
        self.assertIn("size = cols[5]", play_src)
        self.assertIn("seeds = to_int(cols[6]", play_src)
        self.assertIn("leeches = to_int(cols[7]", play_src)
        self.assertNotIn("size = cols[6]", play_src)

    def test_rows_shorter_than_nine_cells_are_skipped(self):
        self.assertIn('if len(cols) < 9:', _source())

    def test_malformed_row_cannot_abort_the_listing(self):
        index_src = ast.unparse(_function('INDEXPAGES'))
        self.assertIn("except Exception as exc:", index_src)
        self.assertIn("Log('row skipped", index_src)

    def test_results_table_prefers_the_full_table(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(
            '<table class="torrent-index__table '
            'torrent-index__table--recommended"><tbody>'
            '<tr><td colspan="9">a</td></tr></tbody></table>'
            + self.HTML, 'html.parser')
        table = self.ns['find_results_table'](soup)
        self.assertEqual(self.ns['data_row_count'](table), 1)


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
