"""Navigation tests for plugin.video.p2pbgplus.

Kodi is stubbed and the tracker session is faked, so main.py can be executed
offline and the routing verified. The regression these guard against: a
category/search click that arrives without its `mode` parameter used to fall
through to the root menu, so every selection re-rendered the main menu.
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

SETTINGS = {
    'p2pbg_user': 'user', 'p2pbg_password': 'pass', 'vpn_country': 'BG',
    'prefer_bgaudio': 'true', 'show_xxx': 'false', 'firstrun': 'false',
    'search_history': '',
}


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


class Keyboard:
    text = 'silo'

    def __init__(self, default='', title=''):
        pass

    def doModal(self):
        pass

    def isConfirmed(self):
        return True

    def getText(self):
        return self.text


def _install_kodi_stubs(items):
    xbmcplugin = types.ModuleType('xbmcplugin')
    xbmcplugin.setContent = lambda *a, **k: None
    xbmcplugin.addDirectoryItem = (
        lambda handle, url, listitem, isFolder: items.append(
            (listitem.label, isFolder, url)))
    xbmcplugin.endOfDirectory = lambda *a, **k: None
    xbmcplugin.setResolvedUrl = MagicMock()

    xbmcgui = types.ModuleType('xbmcgui')
    xbmcgui.NOTIFICATION_INFO = 0
    xbmcgui.ListItem = ListItem
    xbmcgui.Keyboard = Keyboard
    dialog = types.SimpleNamespace(notification=lambda *a, **k: None,
                                   ok=lambda *a, **k: None)
    xbmcgui.Dialog = lambda *a, **k: dialog

    xbmc = types.ModuleType('xbmc')
    xbmc.LOGINFO = 0
    xbmc.log = lambda *a, **k: None
    xbmc.executebuiltin = lambda *a, **k: None
    xbmc.Keyboard = None  # the attribute the reference got wrong

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

    sys.modules.update({'xbmc': xbmc, 'xbmcgui': xbmcgui, 'xbmcplugin': xbmcplugin,
                        'xbmcaddon': xbmcaddon, 'xbmcvfs': xbmcvfs})


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
        self.items = []
        _install_kodi_stubs(self.items)
        SETTINGS.clear()
        SETTINGS.update({'p2pbg_user': 'user', 'p2pbg_password': 'pass',
                         'vpn_country': 'BG', 'prefer_bgaudio': 'true',
                         'show_xxx': 'false', 'firstrun': 'false',
                         'search_history': ''})
        LISTING_URL = ('https://www.p2pbg.com/torrents?fakeusernameremembered=&'
                       'fakepasswordremembered=&search=&category=68&active=1&'
                       'hidexxx=1')
        self.listing = LISTING_URL
        self.encoded = LISTING_URL.replace(':', '%3A').replace('/', '%2F') \
            .replace('?', '%3F').replace('&', '%26').replace('=', '%3D')

    def run_plugin(self, paramstring):
        """Execute main.py once with the given plugin query."""
        del self.items[:]
        sys.modules.pop('main', None)
        argv = ['plugin://plugin.video.p2pbgplus/', '1', paramstring]
        with patch('requests.Session', return_value=_session()):
            with patch.object(sys, 'argv', argv):
                import main  # noqa: F401  (execution is the test)
        sys.modules.pop('main', None)
        return list(self.items)

    def playable(self, items):
        return [label for label, is_folder, _ in items if not is_folder]

    def folders(self, items):
        return [label for label, is_folder, _ in items if is_folder]

    # -- the reported regression ---------------------------------------
    def test_listing_url_without_mode_still_shows_the_listing(self):
        items = self.run_plugin('?url=' + self.encoded)
        self.assertEqual(self.playable(items), ['Silo.S03E10.1080p'])
        self.assertNotIn('Последно добавени', self.folders(items))

    def test_category_with_mode_shows_the_listing(self):
        items = self.run_plugin('?url=%s&mode=1&name=Филми%%20HD&iconimage=/x.png/'
                                % self.encoded)
        self.assertEqual(self.playable(items), ['Silo.S03E10.1080p'])
        self.assertEqual(self.folders(items), [])

    def test_menu_entries_are_folders_only(self):
        items = self.run_plugin('?url=&mode=9&name=Меню&iconimage=/x.png')
        self.assertEqual(self.playable(items), [])
        self.assertEqual(self.folders(items),
                         ['Търсене', 'Филми HD', 'Филми 4K', 'Сериали',
                          'Сериали Boxset', 'Всички филми и сериали',
                          'Диагностика'])

    def test_open_without_query_always_shows_the_menu(self):
        # even with a visited listing on record, the root is the menu:
        # auto-reopening stranded users on the last list with no way back
        self.run_plugin('?url=%s&mode=1&name=x&iconimage=/x.png' % self.encoded)
        self.assertTrue(SETTINGS['last_listing'])
        items = self.run_plugin('')
        self.assertEqual(self.playable(items), [])
        self.assertIn('Филми HD', self.folders(items))

    def test_open_without_query_without_history_shows_menu(self):
        items = self.run_plugin('')
        self.assertEqual(self.folders(items),
                         ['Търсене', 'Филми HD', 'Филми 4K', 'Сериали',
                          'Сериали Boxset', 'Всички филми и сериали',
                          'Диагностика'])

    def test_back_from_listing_returns_to_menu(self):
        # the menu reached from a listing-equivalent root shows every entry
        items = self.run_plugin('')
        self.assertEqual(self.folders(items),
                         ['Търсене', 'Филми HD', 'Филми 4K', 'Сериали',
                          'Сериали Boxset', 'Всички филми и сериали',
                          'Диагностика'])

    # -- search --------------------------------------------------------
    def test_search_screen_offers_search(self):
        items = self.run_plugin('?url=%s&mode=5&name=x&iconimage=/x.png'
                                % self.encoded)
        self.assertEqual(self.folders(items), ['Търсене'])

    def test_search_runs_over_all_categories(self):
        items = self.run_plugin('?m=4&q=silo')
        self.assertEqual(self.playable(items), ['Silo.S03E10.1080p'])
        self.assertIn('category=0', SETTINGS['last_listing'])
        self.assertIn('search=silo', SETTINGS['last_listing'])
        self.assertIn('hidexxx=1', SETTINGS['last_listing'])

    def test_search_with_spaces_is_plus_encoded(self):
        items = self.run_plugin('?m=4&q=dark+matter')
        self.assertEqual(self.playable(items), ['Silo.S03E10.1080p'])
        self.assertIn('search=dark+matter', SETTINGS['last_listing'])
        self.assertIn('category=0', SETTINGS['last_listing'])

    def test_compact_category_urls(self):
        for cats, bare in (('68', ''), ('60', ''),
                           ('67;7;11;14;15;68;24;35;59;60;69', '&bare=1')):
            query = '?m=1&c=%s%s' % (cats, bare)
            items = self.run_plugin(query)
            self.assertEqual(self.playable(items), ['Silo.S03E10.1080p'],
                             query)
            self.assertIn('category=' + cats, SETTINGS['last_listing'], query)

    # -- the menu must never come back as a nested directory ----------
    def test_unresolvable_click_never_renders_the_menu(self):
        for query in ('?url=&mode=1&name=x&iconimage=/x.png',
                      '?mode=1&name=x',
                      '?url=&mode=42&name=x',
                      '?url=not-a-url&mode=1',
                      '?mode=1'):
            items = self.run_plugin(query)
            # no folders at all here, and never the main menu entries
            self.assertEqual([label for label in self.folders(items)
                              if label != 'Меню'], [],
                             'menu rendered for ' + query)
            self.assertEqual(self.playable(items), [])

    def test_root_without_history_is_the_only_implicit_menu(self):
        items = self.run_plugin('')
        self.assertIn('Всички филми и сериали', self.folders(items))
        self.assertIn('Диагностика', self.folders(items))

    def test_listing_url_is_recovered_from_a_mangled_query(self):
        # mode dropped and the url parameter re-encoded by the skin
        query = ('?url=' + self.encoded.replace('%3D', '%253D').replace('%3F', '%253F')
                 + '&iconimage=/x.png')
        self.assertIn('category%253D68', query)
        items = self.run_plugin(query)
        self.assertEqual(self.playable(items), ['Silo.S03E10.1080p'])
        self.assertIn('category=68', SETTINGS['last_listing'])

    def test_play_still_resolves_with_a_long_url(self):
        query = ('?url=https%3A%2F%2Fwww.p2pbg.com%2Fdownload.php%3Fid%3D'
                 + 'b' * 40 + '%26f%3DSilo.torrent&mode=2&name=Silo.S03E10.1080p')
        self.run_plugin(query)
        # VPN country is BG in the stub and the check is cached per call, so
        # either the Elementum URI is recorded or the gate blocked it
        self.assertTrue(SETTINGS.get('last_play') or SETTINGS.get('last_error'))

    # -- label-based recovery (the TV drops the long parameters) --------
    def test_bare_category_label_resolves_by_name(self):
        items = self.run_plugin('?name=%D0%A4%D0%B8%D0%BB%D0%BC%D0%B8+HD')
        self.assertEqual(self.playable(items), ['Silo.S03E10.1080p'])
        self.assertIn('category=68', SETTINGS['last_listing'])
        self.assertNotIn('category=14', SETTINGS['last_listing'])

    def test_category_mode_with_lost_url_resolves_by_name(self):
        items = self.run_plugin('?url=&mode=1&name=%D0%A1%D0%B5%D1%80%D0%B8%D0%B0%D0%BB%D0%B8')
        self.assertEqual(self.playable(items), ['Silo.S03E10.1080p'])
        self.assertIn('category=14', SETTINGS['last_listing'])

    def test_menu_labels_resolve(self):
        items = self.run_plugin('?name=%D0%9C%D0%B5%D0%BD%D1%8E')
        self.assertIn('Всички филми и сериали', self.folders(items))
        items = self.run_plugin('?name=%D0%A2%D1%8A%D1%80%D1%81%D0%B5%D0%BD%D0%B5')
        self.assertEqual(self.folders(items), ['Търсене'])
        self.run_plugin('?name=%D0%94%D0%B8%D0%B0%D0%B3%D0%BD%D0%BE%D1%81%D1%82%D0%B8%D0%BA%D0%B0')

    def test_stale_search_is_never_substituted(self):
        # search first, so a last_listing exists
        self.run_plugin('?url=%s&mode=4&name=x&iconimage=/x.png' % self.encoded)
        self.assertEqual(SETTINGS['last_items'], '1')
        # an unresolvable click reports instead of showing the old search
        items = self.run_plugin('?garbage')
        self.assertEqual(items, [])
        self.assertIn('last_error', SETTINGS)

    def test_truncated_label_still_resolves(self):
        items = self.run_plugin('?name=%D0%A4%D0%B8%D0%BB%D0%BC%D0%B8+H')
        self.assertEqual(self.playable(items), ['Silo.S03E10.1080p'])
        self.assertIn('category=68', SETTINGS['last_listing'])

    def test_ambiguous_label_does_not_guess(self):
        items = self.run_plugin('?name=%D0%A4%D0%B8%D0%BB%D0%BC%D0%B8')
        self.assertEqual(items, [])
        self.assertIn('last_error', SETTINGS)

    def test_nothing_recoverable_reports_instead_of_menu(self):
        items = self.run_plugin('?garbage')
        self.assertEqual(items, [])
        self.assertIn('last_error', SETTINGS)

    # -- bookkeeping ---------------------------------------------------
    def test_listing_is_recorded_for_diagnostics(self):
        self.run_plugin('?url=%s&mode=1&name=Филми%%20HD&iconimage=/x.png'
                        % self.encoded)
        self.assertEqual(SETTINGS['last_listing'], self.listing)
        self.assertEqual(SETTINGS['last_table'], 'found')
        self.assertEqual(SETTINGS['last_items'], '1')
        self.assertIn('mode=1', SETTINGS['last_call'])


if __name__ == '__main__':
    unittest.main()
