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
