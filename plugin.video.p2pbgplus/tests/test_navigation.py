"""Navigation tests for plugin.video.p2pbgplus.

Kodi is stubbed and the tracker session is faked, so main.router can be
executed offline and the routing verified. The regression these guard
against: a category/search click that arrives without its `mode` parameter
used to fall through to the root menu, so every selection re-rendered the
main menu.
"""
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ADDON = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ADDON)

LISTING_HTML = (
    '<table class="torrent-index__table"><tbody>'
    '<tr><td>x</td><td><a onclick="showPreview(\'' + 'b' * 40 + '\')" href="#">'
    'Silo.S03E10.1080p</a></td><td>Свали</td><td>1</td><td>04/09/2026</td>'
    '<td>8.98 GB</td><td>15</td><td>0</td><td>289</td></tr>'
    '</tbody></table>')
DETAILS_HTML = ('<h1>Silo S03E10</h1><a href="https://www.p2pbg.com/download.php?id='
                + 'b' * 40 + '&amp;f=x.torrent">dl</a>')

MENU = ['Search', 'Movies HD', 'TV Shows', 'TV Boxsets',
        'All movies and shows', 'Diagnostics']

SETTINGS = {
    'p2pbg_user': 'user', 'p2pbg_password': 'pass', 'vpn_country': 'BG',
    'prefer_bgaudio': 'true', 'show_xxx': 'false', 'firstrun': 'false',
    'search_history': '',
}

ITEMS = []


class ListItem:
    def __init__(self, label=None, path=None):
        self.label = label
        self.path = path

    def setProperty(self, *args, **kwargs):
        pass

    def setArt(self, *args, **kwargs):
        pass

    def setInfo(self, *args, **kwargs):
        pass

    def getVideoInfoTag(self):
        return self


class _Dialog:
    answer = ''

    def notification(self, *args, **kwargs):
        pass

    def ok(self, *args, **kwargs):
        pass

    def input(self, *args, **kwargs):
        return self.answer


DIALOG = _Dialog()


def _install_kodi_stubs():
    if sys.modules.get('xbmc') is not None and \
            getattr(sys.modules['xbmc'], '_p2pbg_stub', False):
        return

    xbmcplugin = types.ModuleType('xbmcplugin')
    xbmcplugin.setContent = lambda *a, **k: None
    xbmcplugin.setPluginCategory = lambda *a, **k: None
    xbmcplugin.addDirectoryItem = (
        lambda handle, url, listitem, isFolder: ITEMS.append(
            (listitem.label, isFolder, url)))
    xbmcplugin.endOfDirectory = lambda *a, **k: None
    xbmcplugin.setResolvedUrl = MagicMock()

    xbmcgui = types.ModuleType('xbmcgui')
    xbmcgui.NOTIFICATION_INFO = 0
    xbmcgui.ListItem = ListItem
    xbmcgui.Dialog = lambda *a, **k: DIALOG

    xbmc = types.ModuleType('xbmc')
    xbmc._p2pbg_stub = True
    xbmc.LOGINFO = 0
    xbmc.log = lambda *a, **k: None
    xbmc.executebuiltin = lambda *a, **k: None

    class Addon:
        def __init__(self, id='plugin.video.p2pbgplus'):
            pass

        def getSetting(self, key):
            return SETTINGS.get(key, '')

        def setSetting(self, key, value):
            SETTINGS[key] = value

        def getAddonInfo(self, key):
            return '/tmp/fake_' + key

        def openSettings(self):
            pass

    xbmcaddon = types.ModuleType('xbmcaddon')
    xbmcaddon.Addon = Addon

    xbmcvfs = types.ModuleType('xbmcvfs')
    xbmcvfs.translatePath = lambda path: path
    xbmcvfs.exists = lambda path: False
    xbmcvfs.mkdirs = lambda path: None
    xbmcvfs.File = MagicMock()

    sys.modules.update({'xbmc': xbmc, 'xbmcgui': xbmcgui,
                        'xbmcplugin': xbmcplugin, 'xbmcaddon': xbmcaddon,
                        'xbmcvfs': xbmcvfs})


_install_kodi_stubs()


def _session():
    session = MagicMock()

    def get(url, **kwargs):
        res = MagicMock()
        res.url = url
        res.text = LISTING_HTML if '/torrents?' in url else DETAILS_HTML
        res.content = b'd4:infod4:name4:teste'
        return res

    session.get = get
    session.post = MagicMock()
    return session


class TestNavigation(unittest.TestCase):
    def setUp(self):
        from resources.lib import kodi_utils
        ITEMS.clear()
        DIALOG.answer = ''
        SETTINGS.clear()
        SETTINGS.update({'p2pbg_user': 'user', 'p2pbg_password': 'pass',
                         'vpn_country': 'BG', 'prefer_bgaudio': 'true',
                         'show_xxx': 'false', 'firstrun': 'false',
                         'search_history': ''})
        vfs = sys.modules['xbmcvfs']
        vfs.exists = lambda path: False
        vfs.File = MagicMock()
        self.kodi_utils = kodi_utils
        LISTING_URL = ('https://www.p2pbg.com/torrents?fakeusernameremembered=&'
                       'fakepasswordremembered=&search=&category=68&active=1&'
                       'hidexxx=1')
        self.listing = LISTING_URL
        self.encoded = LISTING_URL.replace(':', '%3A').replace('/', '%2F') \
            .replace('?', '%3F').replace('&', '%26').replace('=', '%3D')

    def run_plugin(self, paramstring):
        """Execute main.router once with the given plugin query."""
        del ITEMS[:]
        argv = ['plugin://plugin.video.p2pbgplus/', '1', paramstring]
        with patch.object(sys, 'argv', argv):
            if 'main' not in sys.modules:
                with patch('requests.Session', return_value=_session()):
                    import main  # noqa: F401
            import main
            main.router(paramstring)
        return list(ITEMS)

    def playable(self, items):
        return [label for label, is_folder, _ in items if not is_folder]

    def titles(self, items):
        return [label.split('  [COLOR')[0] for label, is_folder, _ in items
                if not is_folder]

    def folders(self, items):
        return [label for label, is_folder, _ in items if is_folder]

    # -- the reported regression ---------------------------------------
    def test_listing_url_without_mode_still_shows_the_listing(self):
        items = self.run_plugin('?url=' + self.encoded)
        self.assertEqual(self.titles(items), ['Silo.S03E10.1080p'])
        self.assertNotIn('Latest', self.folders(items))

    def test_category_with_mode_shows_the_listing(self):
        items = self.run_plugin('?url=%s&mode=1&name=Movies%%20HD&iconimage=/x.png/'
                                % self.encoded)
        self.assertEqual(self.titles(items), ['Silo.S03E10.1080p'])
        self.assertEqual(self.folders(items), [])

    def test_listing_labels_show_activity(self):
        items = self.run_plugin('?url=' + self.encoded)
        self.assertIn('S:15', self.playable(items)[0])
        self.assertIn('L:0', self.playable(items)[0])

    def test_menu_entries_are_folders_only(self):
        items = self.run_plugin('?url=&mode=9&name=Menu&iconimage=/x.png')
        self.assertEqual(self.playable(items), [])
        self.assertEqual(self.folders(items), MENU)

    def test_open_without_query_always_shows_the_menu(self):
        # even with a visited listing on record, the root is the menu:
        # auto-reopening stranded users on the last list with no way back
        self.run_plugin('?url=%s&mode=1&name=x&iconimage=/x.png' % self.encoded)
        self.assertTrue(SETTINGS['last_listing'])
        items = self.run_plugin('')
        self.assertEqual(self.playable(items), [])
        self.assertIn('Movies HD', self.folders(items))

    def test_open_without_query_without_history_shows_menu(self):
        items = self.run_plugin('')
        self.assertEqual(self.folders(items), MENU)

    def test_back_from_listing_returns_to_menu(self):
        items = self.run_plugin('')
        self.assertEqual(self.folders(items), MENU)

    # -- search --------------------------------------------------------
    def _history_content(self, payload):
        vfs = sys.modules['xbmcvfs']
        vfs.exists = lambda path: True
        handle = MagicMock()
        handle.read.return_value = payload
        vfs.File = MagicMock(return_value=handle)

    def test_search_screen_survives_corrupt_history(self):
        self._history_content('not json{{{')
        items = self.run_plugin('?m=5')
        self.assertEqual(self.folders(items), ['New search'])

    def test_search_screen_survives_non_list_history(self):
        self._history_content('{"text": "silo"}')
        items = self.run_plugin('?m=5')
        self.assertEqual(self.folders(items), ['New search'])

    def test_menu_search_opens_history_first(self):
        self._history_content('[{"text": "dark matter"}]')
        items = self.run_plugin('?m=5')
        self.assertEqual(self.folders(items),
                         ['New search', 'dark matter', 'Clear history'])

    def test_search_input_runs_the_search(self):
        DIALOG.answer = 'dark matter'
        items = self.run_plugin('?m=10')
        self.assertEqual(self.titles(items), ['Silo.S03E10.1080p'])
        self.assertIn('search=dark+matter', SETTINGS['last_listing'])
        self.assertIn('category=0', SETTINGS['last_listing'])

    def test_history_entry_reruns_its_search(self):
        self._history_content('[{"text": "dark matter"}]')
        items = self.run_plugin('?m=4&q=dark+matter')
        self.assertEqual(self.titles(items), ['Silo.S03E10.1080p'])
        self.assertIn('search=dark+matter', SETTINGS['last_listing'])

    def test_search_screen_offers_search(self):
        items = self.run_plugin('?url=%s&mode=5&name=x&iconimage=/x.png'
                                % self.encoded)
        self.assertEqual(self.folders(items), ['New search'])

    def test_search_runs_over_all_categories(self):
        items = self.run_plugin('?m=4&q=silo')
        self.assertEqual(self.titles(items), ['Silo.S03E10.1080p'])
        self.assertIn('category=0', SETTINGS['last_listing'])
        self.assertIn('search=silo', SETTINGS['last_listing'])
        self.assertIn('hidexxx=1', SETTINGS['last_listing'])

    def test_search_with_spaces_is_plus_encoded(self):
        items = self.run_plugin('?m=4&q=dark+matter')
        self.assertEqual(self.titles(items), ['Silo.S03E10.1080p'])
        self.assertIn('search=dark+matter', SETTINGS['last_listing'])
        self.assertIn('category=0', SETTINGS['last_listing'])

    def test_compact_category_urls(self):
        for cats, bare in (('68', ''), ('67;7;11;14;15;68;24;35;59;69', '&bare=1')):
            query = '?m=1&c=%s%s' % (cats, bare)
            items = self.run_plugin(query)
            self.assertEqual(self.titles(items), ['Silo.S03E10.1080p'], query)
            if bare:
                continue
            self.assertIn('category=' + cats, SETTINGS['last_listing'], query)

    # -- the menu must never come back as a nested directory ----------
    def test_unresolvable_click_never_renders_the_menu(self):
        for query in ('?url=&mode=1&name=x&iconimage=/x.png',
                      '?mode=1&name=x',
                      '?url=&mode=42&name=x',
                      '?url=not-a-url&mode=1',
                      '?mode=1'):
            items = self.run_plugin(query)
            self.assertEqual(self.folders(items), [],
                             'menu rendered for ' + query)
            self.assertEqual(self.playable(items), [])

    def test_root_without_history_is_the_only_implicit_menu(self):
        items = self.run_plugin('')
        self.assertIn('All movies and shows', self.folders(items))
        self.assertIn('Diagnostics', self.folders(items))

    def test_listing_url_is_recovered_from_a_mangled_query(self):
        # mode dropped and the url parameter re-encoded by the skin
        query = ('?url=' + self.encoded.replace('%3D', '%253D').replace('%3F', '%253F')
                 + '&iconimage=/x.png')
        self.assertIn('category%253D68', query)
        items = self.run_plugin(query)
        self.assertEqual(self.titles(items), ['Silo.S03E10.1080p'])
        self.assertIn('category=68', SETTINGS['last_listing'])

    def test_play_still_resolves_with_a_long_url(self):
        query = ('?url=https%3A%2F%2Fwww.p2pbg.com%2Fdownload.php%3Fid%3D'
                 + 'b' * 40 + '%26f%3DSilo.torrent&mode=2&name=Silo.S03E10.1080p')
        with patch('resources.lib.vpngate.VPNGate.check',
                   return_value=(True, 'BG')):
            self.run_plugin(query)
        self.assertTrue(SETTINGS.get('last_play'))
        self.assertIn('plugin.video.elementum', SETTINGS['last_play'])

    # -- label-based recovery (the TV drops the long parameters) --------
    def test_bare_category_label_resolves_by_name(self):
        items = self.run_plugin('?name=Movies+HD')
        self.assertEqual(self.titles(items), ['Silo.S03E10.1080p'])
        self.assertIn('category=68', SETTINGS['last_listing'])
        self.assertNotIn('category=14', SETTINGS['last_listing'])

    def test_category_mode_with_lost_url_resolves_by_name(self):
        items = self.run_plugin('?url=&mode=1&name=TV+Shows')
        self.assertEqual(self.titles(items), ['Silo.S03E10.1080p'])
        self.assertIn('category=14', SETTINGS['last_listing'])

    def test_menu_labels_resolve(self):
        items = self.run_plugin('?name=Menu')
        self.assertIn('All movies and shows', self.folders(items))
        items = self.run_plugin('?name=Search')
        self.assertEqual(self.folders(items), ['New search'])
        self.run_plugin('?name=Diagnostics')

    def test_stale_search_is_never_substituted(self):
        # search first, so a last_listing exists
        self.run_plugin('?url=%s&mode=4&name=x&iconimage=/x.png' % self.encoded)
        self.assertEqual(SETTINGS['last_items'], '1')
        # an unresolvable click reports instead of showing the old search
        items = self.run_plugin('?garbage')
        self.assertEqual(items, [])
        self.assertIn('last_error', SETTINGS)

    def test_truncated_label_still_resolves(self):
        items = self.run_plugin('?name=Movies+H')
        self.assertEqual(self.titles(items), ['Silo.S03E10.1080p'])
        self.assertIn('category=68', SETTINGS['last_listing'])

    def test_ambiguous_label_does_not_guess(self):
        items = self.run_plugin('?name=TV')
        self.assertEqual(items, [])
        self.assertIn('last_error', SETTINGS)

    def test_nothing_recoverable_reports_instead_of_menu(self):
        items = self.run_plugin('?garbage')
        self.assertEqual(items, [])
        self.assertIn('last_error', SETTINGS)

    # -- bookkeeping ---------------------------------------------------
    def test_listing_is_recorded_for_diagnostics(self):
        self.run_plugin('?url=%s&mode=1&name=Movies%%20HD&iconimage=/x.png'
                        % self.encoded)
        self.assertEqual(SETTINGS['last_listing'], self.listing)
        self.assertEqual(SETTINGS['last_table'], 'found')
        self.assertEqual(SETTINGS['last_items'], '1')
        self.assertIn('mode=1', SETTINGS['last_call'])


if __name__ == '__main__':
    unittest.main()
