# -*- coding: utf-8 -*-
"""Navigation tests for plugin.video.filmifenplus.

Kodi is stubbed and the HTTP layer is faked, so main.router and the views
can be executed offline. The regressions these guard against (all
confirmed on the reference add-on):

* TV Shows (``/seriali/``) rendered an empty folder because series cards
  do not carry the ``item__poster-category`` element the old regex needed;
* search results dropped every series item and pagination built a garbage
  URL out of ``javascript:list_submit(N)``;
* the root menu re-appeared as a nested folder when a click could not be
  resolved (removed here: failures are reported, the menu is rendered only
  at the add-on root).

The fork also changed the root: the four selections come first, then the
same content the site homepage shows (the movies catalog, paged as
``/page/N/``), and every directory gets the InfoWall view by default.
"""
import json
import os
import sys
import types
import unittest
import urllib.parse
from unittest.mock import MagicMock, patch

ADDON = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ADDON)

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
# Derives from the Addon stub below ('/tmp/fake_' + 'profile').
HISTORY_PATH = '/tmp/fake_profile/search_history.json'


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding='utf-8') as handle:
        return handle.read()


ITEMS = []
NOTIFICATIONS = []
KEYBOARD_RESULT = [None]
EXECUTED = []
SETTINGS = {}
FILES = {}

MENU = ['Search', 'Movies', 'Movies HD', 'TV Shows']


class ListItem:
    def __init__(self, label=None, path=None):
        self.label = label
        self.path = path
        self.subtitles = []

    def setProperty(self, *args, **kwargs):
        pass

    def setArt(self, *args, **kwargs):
        pass

    def setInfo(self, *args, **kwargs):
        pass

    def setSubtitles(self, subtitles):
        self.subtitles = subtitles


class _Dialog:
    def notification(self, *args, **kwargs):
        NOTIFICATIONS.append(args)

    def ok(self, *args, **kwargs):
        pass

    def input(self, *args, **kwargs):
        return ''


DIALOG = _Dialog()


class _Keyboard:
    def __init__(self, *args, **kwargs):
        pass

    def doModal(self):
        pass

    def isConfirmed(self):
        return KEYBOARD_RESULT[0] is not None

    def getText(self):
        return KEYBOARD_RESULT[0] or ''


def _install_kodi_stubs():
    if sys.modules.get('xbmc') is not None and \
            getattr(sys.modules['xbmc'], '_filmifenplus_stub', False):
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
    xbmc._filmifenplus_stub = True
    xbmc.LOGINFO = 0
    xbmc.log = lambda *a, **k: None
    xbmc.executebuiltin = lambda command, *a, **k: EXECUTED.append(command)
    xbmc.Keyboard = _Keyboard

    class Addon:
        def __init__(self, id='plugin.video.filmifenplus'):
            pass

        def getSetting(self, key):
            return SETTINGS.get(key, '')

        def setSetting(self, key, value):
            pass

        def getAddonInfo(self, key):
            return '/tmp/fake_' + key

        def openSettings(self):
            pass

    xbmcaddon = types.ModuleType('xbmcaddon')
    xbmcaddon.Addon = Addon

    class _File:
        def __init__(self, path, mode='r'):
            self.path = path

        def read(self):
            return FILES.get(self.path, '')

        def write(self, data):
            FILES[self.path] = data

        def close(self):
            pass

    xbmcvfs = types.ModuleType('xbmcvfs')
    xbmcvfs.translatePath = lambda path: path
    xbmcvfs.exists = lambda path: path in FILES
    xbmcvfs.mkdirs = lambda path: None
    xbmcvfs.File = _File

    sys.modules.update({'xbmc': xbmc, 'xbmcgui': xbmcgui,
                        'xbmcplugin': xbmcplugin, 'xbmcaddon': xbmcaddon,
                        'xbmcvfs': xbmcvfs})


_install_kodi_stubs()

from resources.lib import filmifen  # noqa: E402
from resources.lib import kodi_utils  # noqa: E402


def unquote_url(item_url):
    """Decode the plugin query of one directory item."""
    query = item_url.split('?', 1)[1]
    return {key: value[0] for key, value in
            urllib.parse.parse_qs(query, keep_blank_values=True).items()}


class TestNavigation(unittest.TestCase):
    def setUp(self):
        del ITEMS[:]
        del NOTIFICATIONS[:]
        del EXECUTED[:]
        SETTINGS.clear()
        FILES.clear()
        KEYBOARD_RESULT[0] = None

    def run_plugin(self, paramstring):
        del ITEMS[:]
        with patch('sys.argv', ['plugin://plugin.video.filmifenplus/', '1',
                                paramstring]):
            import main
            main.router(paramstring)
        return list(ITEMS)

    def labels(self, items):
        return [label for label, is_folder, _ in items]

    def playables(self, items):
        return [label for label, is_folder, _ in items if not is_folder]

    # -- root menu / homepage mirror ------------------------------------
    def test_root_shows_the_four_selections_first(self):
        with patch('resources.lib.http.get',
                   return_value=fixture('home.html')):
            items = self.run_plugin('')
        self.assertEqual(self.labels(items)[:4], MENU)
        self.assertEqual(self.playables(items), [])

    def test_root_mirrors_the_homepage_content_under_the_menu(self):
        with patch('resources.lib.http.get',
                   return_value=fixture('home.html')):
            items = self.run_plugin('')
        titles = self.labels(items)
        self.assertIn('Големия план', titles)
        self.assertIn('Тензинг', titles)
        # a homepage card opens the stream selection of its title page
        tenzing = unquote_url([url for label, _, url in items
                               if label == 'Тензинг'][0])
        self.assertEqual(tenzing['mode'], '3')
        self.assertIn('/filmi/', tenzing['url'])

    def test_root_homepage_next_page_continues_the_catalog(self):
        with patch('resources.lib.http.get',
                   return_value=fixture('home.html')):
            items = self.run_plugin('')
        self.assertEqual(self.labels(items)[-1], 'Next page >>')
        next_page = unquote_url([url for label, _, url in items
                                 if label == 'Next page >>'][0])
        self.assertEqual(next_page['mode'], '1')
        self.assertEqual(next_page['url'], 'https://filmifen.com/page/2/')

    def test_root_survives_homepage_failure(self):
        with patch('resources.lib.http.get',
                   side_effect=Exception('offline')):
            items = self.run_plugin('')
        self.assertEqual(self.labels(items), MENU)
        self.assertTrue(any('homepage' in str(args).lower()
                            for args in NOTIFICATIONS))

    def test_root_menu_uses_the_working_section_urls(self):
        with patch('resources.lib.http.get',
                   return_value=fixture('home.html')):
            items = self.run_plugin('')
        by_label = {label: unquote_url(url) for label, _, url in items}
        self.assertEqual(by_label['Movies']['url'], filmifen.URL_MOVIES)
        self.assertEqual(by_label['Movies HD']['url'],
                         filmifen.URL_MOVIES_HD)
        self.assertEqual(by_label['TV Shows']['url'], filmifen.URL_TV_SHOWS)
        self.assertEqual(by_label['TV Shows']['mode'], '1')
        self.assertEqual(by_label['Search']['mode'], '2')

    # -- default InfoWall view -------------------------------------------
    def test_infowall_view_is_applied_after_a_listing(self):
        with patch('resources.lib.http.get',
                   return_value=fixture('listing_series.html')):
            query = '?url=%s&mode=1&name=TV%%20Shows' % urllib.parse.quote_plus(
                filmifen.URL_TV_SHOWS)
            self.run_plugin(query)
        self.assertIn('Container.SetViewMode(54)', EXECUTED)

    def test_infowall_view_can_be_disabled(self):
        SETTINGS['view_infowall'] = 'false'
        with patch('resources.lib.http.get',
                   return_value=fixture('home.html')):
            self.run_plugin('')
        self.assertFalse([cmd for cmd in EXECUTED
                          if cmd.startswith('Container.SetViewMode')])

    def test_infowall_view_id_is_configurable(self):
        SETTINGS['view_infowall_id'] = '57'
        with patch('resources.lib.http.get',
                   return_value=fixture('home.html')):
            self.run_plugin('')
        self.assertIn('Container.SetViewMode(57)', EXECUTED)

    # -- TV Shows (the reported empty folder) ---------------------------
    def test_tv_shows_listing_renders_series_cards(self):
        with patch('resources.lib.http.get',
                   return_value=fixture('listing_series.html')):
            query = '?url=%s&mode=1&name=TV%%20Shows' % urllib.parse.quote_plus(
                filmifen.URL_TV_SHOWS)
            items = self.run_plugin(query)
        self.assertIn('Кари (Се 1 • Еп 8)', self.labels(items))
        self.assertIn('Next page >>', self.labels(items))

    def test_movies_listing_renders_cards_with_plot_and_next_page(self):
        with patch('resources.lib.http.get',
                   return_value=fixture('listing_movies.html')):
            query = '?url=%s&mode=1&name=Movies' % urllib.parse.quote_plus(
                filmifen.URL_MOVIES)
            items = self.run_plugin(query)
        titles = self.labels(items)
        self.assertIn('Тензинг', titles)
        self.assertIn('Next page >>', titles)

        first = unquote_url([url for label, _, url in items
                             if label == 'Тензинг'][0])
        self.assertEqual(first['mode'], '3')
        self.assertIn('Category:', first['plot'])
        self.assertTrue(first['url'].startswith('https://filmifen.com/'))

        next_page = unquote_url([url for label, _, url in items
                                 if label == 'Next page >>'][0])
        self.assertEqual(next_page['url'],
                         'https://filmifen.com/filmi/page/2/')

    def test_empty_listing_reports_instead_of_showing_nothing(self):
        with patch('resources.lib.http.get', return_value='<html></html>'):
            query = '?url=%s&mode=1&name=Movies' % urllib.parse.quote_plus(
                filmifen.URL_MOVIES)
            items = self.run_plugin(query)
        self.assertEqual(items, [])
        self.assertTrue(NOTIFICATIONS)

    # -- search screen and history ---------------------------------------
    def test_search_screen_lists_only_new_search_without_history(self):
        items = self.run_plugin('?url=%s&mode=2&name=Search'
                                % urllib.parse.quote_plus(
                                    filmifen.URL_SEARCH))
        self.assertEqual(self.labels(items), ['New search'])

    def test_search_screen_lists_the_remembered_queries(self):
        FILES[HISTORY_PATH] = json.dumps([{'text': 'кари'},
                                          {'text': 'tenzing'}])
        items = self.run_plugin('?url=%s&mode=2&name=Search'
                                % urllib.parse.quote_plus(
                                    filmifen.URL_SEARCH))
        self.assertEqual(self.labels(items),
                         ['New search', 'кари', 'tenzing', 'Clear history'])

    def test_history_entry_replays_the_search(self):
        FILES[HISTORY_PATH] = json.dumps([{'text': 'кари'}])
        items = self.run_plugin('?url=%s&mode=2&name=Search'
                                % urllib.parse.quote_plus(
                                    filmifen.URL_SEARCH))
        entry_query = [url.split('?', 1)[1] for label, _, url in items
                       if label == 'кари'][0]
        with patch('resources.lib.http.post',
                   return_value=fixture('search_page1.html')) as post:
            results = self.run_plugin(entry_query)
        self.assertEqual(post.call_args[0][1]['story'], 'кари')
        self.assertIn('Тензинг', self.labels(results))
        self.assertIn('Кари (Се 1 • Еп 8)', self.labels(results))

    def test_new_search_is_remembered(self):
        KEYBOARD_RESULT[0] = 'кари'
        with patch('resources.lib.http.post',
                   return_value=fixture('search_page1.html')):
            self.run_plugin('?mode=5')
        self.assertEqual(json.loads(FILES[HISTORY_PATH]),
                         [{'text': 'кари'}])

    def test_cancelled_new_search_remembers_nothing(self):
        KEYBOARD_RESULT[0] = None
        items = self.run_plugin('?mode=5')
        self.assertEqual(items, [])
        self.assertNotIn(HISTORY_PATH, FILES)

    def test_clear_history_empties_the_screen(self):
        FILES[HISTORY_PATH] = json.dumps([{'text': 'кари'}])
        self.run_plugin('?mode=6')
        self.assertEqual(json.loads(FILES[HISTORY_PATH]), [])
        self.assertIn('Container.Refresh', EXECUTED)
        items = self.run_plugin('?url=%s&mode=2&name=Search'
                                % urllib.parse.quote_plus(
                                    filmifen.URL_SEARCH))
        self.assertEqual(self.labels(items), ['New search'])

    def test_history_keeps_newest_first_and_deduplicates(self):
        kodi_utils.add_to_history('а')
        kodi_utils.add_to_history('б')
        kodi_utils.add_to_history('а')
        self.assertEqual([item['text'] for item in kodi_utils.load_history()],
                         ['а', 'б'])

    def test_history_is_capped(self):
        for index in range(kodi_utils.MAX_HISTORY + 5):
            kodi_utils.add_to_history('q%d' % index)
        history = kodi_utils.load_history()
        self.assertEqual(len(history), kodi_utils.MAX_HISTORY)
        self.assertEqual(history[0]['text'], 'q%d' % (kodi_utils.MAX_HISTORY + 4))

    # -- search ---------------------------------------------------------
    def test_search_posts_the_story_and_renders_both_card_types(self):
        posted = {}

        def fake_post(url, data):
            posted['url'] = url
            posted['data'] = data
            return fixture('search_page1.html')

        KEYBOARD_RESULT[0] = 'кари'
        with patch('resources.lib.http.post', side_effect=fake_post):
            items = self.run_plugin('?mode=5')
        self.assertEqual(posted['url'], filmifen.URL_SEARCH)
        self.assertEqual(posted['data'], {'do': 'search',
                                          'subaction': 'search',
                                          'story': 'кари'})
        labels = self.labels(items)
        self.assertIn('Тензинг', labels)
        self.assertIn('Кари (Се 1 • Еп 8)', labels)
        self.assertEqual(json.loads(FILES[HISTORY_PATH]),
                         [{'text': 'кари'}])

        next_page = unquote_url([url for label, _, url in items
                                 if label == 'Next page >>'][0])
        self.assertEqual(next_page['url'], filmifen.search_page_url('кари', 2))

    def test_search_next_page_recovers_the_story_from_the_url(self):
        # Page 2 arrives as a plain GET URL; its list_submit(3) link must
        # still become a working page-3 URL (the list_submit(1) link that
        # points back to page 1 comes before the current-page span).
        page2 = filmifen.search_page_url('кари', 2)
        with patch('resources.lib.http.get',
                   return_value=fixture('search_page2.html')):
            query = '?url=%s&mode=1&name=кари' % urllib.parse.quote_plus(page2)
            items = self.run_plugin(query)
        next_page = unquote_url([url for label, _, url in items
                                 if label == 'Next page >>'][0])
        self.assertEqual(next_page['url'], filmifen.search_page_url('кари', 3))

    def test_empty_search_reports_no_results(self):
        KEYBOARD_RESULT[0] = 'нищо'
        with patch('resources.lib.http.post',
                   return_value='<html></html>'):
            self.run_plugin('?mode=5')
        self.assertTrue(any('No results' in str(args)
                            for args in NOTIFICATIONS))

    def test_cancelled_search_never_renders_the_menu(self):
        KEYBOARD_RESULT[0] = None
        items = self.run_plugin('?mode=5')
        self.assertEqual(items, [])

    # -- stream selection and play --------------------------------------
    def test_stream_screen_lists_the_resolvable_players(self):
        with patch('resources.lib.http.get',
                   return_value=fixture('title_movie.html')):
            query = ('?url=%s&mode=3&name=%s&plot=%s&iconimage='
                     % (urllib.parse.quote_plus(
                            'https://filmifen.com/filmi/x/14137-tenzing.html'),
                        urllib.parse.quote_plus('Тензинг'),
                        urllib.parse.quote_plus('plot')))
            items = self.run_plugin(query)
        self.assertEqual(self.playables(items), [
            'Stream 1: Тензинг', 'Stream 2: Тензинг', 'Stream 3: Тензинг'])
        streams = [unquote_url(url)['url'] for _, _, url in items]
        self.assertIn('https://vidon.to/e/M495IPFR1R6R', streams)
        self.assertIn('https://ok.ru/videoembed/16388013099703', streams)

    def test_play_hands_the_resolved_url_to_kodi(self):
        set_resolved = sys.modules['xbmcplugin'].setResolvedUrl
        set_resolved.reset_mock()
        fake_resolveurl = MagicMock()
        fake_resolveurl.resolve.return_value = (
            'https://cdn.example/stream.mp4', '')
        with patch('resources.lib.playback.resolveurl', fake_resolveurl):
            self.run_plugin('?url=%s&mode=4&name=Тензинг'
                            % urllib.parse.quote_plus(
                                'https://vidon.to/e/M495IPFR1R6R'))
        fake_resolveurl.resolve.assert_called_once_with(
            'https://vidon.to/e/M495IPFR1R6R')
        self.assertEqual(set_resolved.call_count, 1)
        handle, ok, listitem = set_resolved.call_args[0]
        self.assertTrue(ok)
        self.assertEqual(listitem.path, 'https://cdn.example/stream.mp4')

    # -- failure handling ------------------------------------------------
    def test_unresolvable_call_reports_instead_of_rendering_the_menu(self):
        items = self.run_plugin('?mode=99&name=Ghost')
        self.assertEqual(items, [])
        self.assertTrue(any('Cannot open' in str(args)
                            for args in NOTIFICATIONS))

    def test_listing_without_url_reports_instead_of_rendering_the_menu(self):
        items = self.run_plugin('?mode=1&name=Movies')
        self.assertEqual(items, [])
        self.assertTrue(any('no URL' in str(args) for args in NOTIFICATIONS))


if __name__ == '__main__':
    unittest.main()
