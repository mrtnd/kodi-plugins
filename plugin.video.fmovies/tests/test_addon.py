import sys
import os

# Ensure mocks are in sys.modules first
class MockXbmcAddon:
    def __init__(self, id='plugin.video.fmovies'):
        pass
    def getSetting(self, id):
        if id == 'use_inputstream':
            return 'true'
        if id == 'preferred_server':
            return 'Server 1'
        return 'https://fmoviess.org'
    def setSetting(self, id, value):
        pass
    def getAddonInfo(self, id):
        return 'mock_value'

class MockXbmcGui:
    NOTIFICATION_INFO = 0
    def notification(self, *args, **kwargs): pass
    def ok(self, *args, **kwargs): pass
    def ListItem(self, *args, **kwargs): return type('obj', (object,), {'setProperty': lambda s,k,v:None, 'setArt': lambda s,a:None, 'setInfo': lambda s,t,i:None})
    def Dialog(self): return self

sys.modules['xbmc'] = type('obj', (object,), {})
sys.modules['xbmcgui'] = MockXbmcGui()
sys.modules['xbmcaddon'] = type('obj', (object,), {'Addon': MockXbmcAddon})
sys.modules['xbmcplugin'] = type('obj', (object,), {})

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import patch, MagicMock
from resources.lib.scraper import FMoviesScraper
from resources.lib.resolver import StreamResolver

class TestFMoviesScraper(unittest.TestCase):
    @patch('resources.lib.scraper.requests.Session.get')
    def test_get_catalog(self, mock_get):
        html = '''
        <html>
            <body>
                <div class="card bg-transparent">
                    <a href="/movie/test-movie-123"><h3 class="card-title">Test Movie</h3></a>
                    <img src="/images/test.jpg" alt="Test Movie"/>
                    <span class="mlbq">HD</span>
                </div>
                <div class="pagination">
                    <a class="page-link" rel="next" href="/movies?page=2">Next</a>
                </div>
            </body>
        </html>
        '''
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = lambda: None
        mock_get.return_value = mock_response

        scraper = FMoviesScraper()
        items, next_page = scraper.get_catalog('/movies')

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'Test Movie [HD]')
        self.assertEqual(items[0]['mediatype'], 'movie')
        self.assertEqual(next_page, 'https://fmoviess.org/movies?page=2')

    @patch('resources.lib.scraper.requests.Session.get')
    def test_series_slug_classified_as_tvshow(self, mock_get):
        html = '''
        <html><body>
            <div class="card bg-transparent border-0 h-100">
                <a href="/film/the-grand-tour-season-1-1421/"><h3 class="card-title">The Grand Tour</h3></a>
                <img class="lazy" data-src="https://img.cdno.my.id/thumb/w_200/h_300/x.jpg" alt="The Grand Tour"/>
            </div>
            <div class="card bg-transparent border-0 h-100">
                <a href="/film/burt-1423/"><h3 class="card-title">Burt</h3></a>
            </div>
        </body></html>
        '''
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = lambda: None
        mock_get.return_value = mock_response

        scraper = FMoviesScraper()
        items, _ = scraper.get_catalog('/tv-series')
        self.assertEqual(items[0]['mediatype'], 'tvshow')
        self.assertEqual(items[1]['mediatype'], 'movie')

    @patch('resources.lib.scraper.requests.Session.get')
    def test_search_uses_searching_api(self, mock_get):
        import json

        def route(url, *args, **kwargs):
            resp = MagicMock()
            if 'offset=0' in url:
                resp.json = lambda: {
                    'data': [
                        {'t': 'Gilmore Girls - Season 7', 's': 'gilmore-girls-season-7-7254',
                         'd': 's', 'e': 22, 'n': 7, 'q': 'HD', 'y': 2006},
                        {'t': 'Burt', 's': 'burt-1423',
                         'd': 'm', 'e': 1, 'n': 1, 'q': 'HD', 'y': 2025},
                    ],
                    'meta': {'offset': 0, 'total_items': 2, 'total_pages': 1, 'page_number': 1},
                }
            else:
                resp.json = lambda: {'data': [], 'meta': {}}
            return resp

        mock_get.side_effect = route
        scraper = FMoviesScraper()
        items, _ = scraper.search('gilmore')
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['mediatype'], 'tvshow')
        self.assertEqual(items[0]['url'], 'https://fmoviess.org/film/gilmore-girls-season-7-7254/')
        self.assertIn('(2006)', items[0]['title'])
        self.assertEqual(items[1]['mediatype'], 'movie')

    @patch('resources.lib.scraper.requests.Session.get')
    def test_get_dropdown_items(self, mock_get):
        html = '''
        <html>
            <body>
                <a href="/genre/action">Action</a>
                <a href="/genre/action">Action</a>
                <a href="/genre/comedy">Comedy</a>
            </body>
        </html>
        '''
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = lambda: None
        mock_get.return_value = mock_response

        scraper = FMoviesScraper()
        genres = scraper.get_dropdown_items('genre')

        self.assertEqual(len(genres), 2)
        self.assertEqual(genres[0]['title'], 'Action')
        self.assertEqual(genres[1]['title'], 'Comedy')


class TestStreamResolver(unittest.TestCase):
    @patch('resources.lib.resolver.requests.Session.get')
    def test_get_servers(self, mock_get):
        html = '''
        <html>
            <body>
                <button class="server" id="server-1">Server 1</button>
                <button class="server" id="server-2">Server 2</button>
            </body>
        </html>
        '''
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = lambda: None
        mock_get.return_value = mock_response

        resolver = StreamResolver()
        servers = resolver.get_servers('https://fmoviess.org/movie/test')

        self.assertEqual(len(servers), 2)
        self.assertEqual(servers[0]['name'], 'Server 1')
        self.assertEqual(servers[1]['name'], 'Server 2')

    @patch('resources.lib.resolver.requests.Session.get')
    def test_resolve_stream(self, mock_get):
        try:
            from test_chain import _fixture_router
        except ImportError:
            from tests.test_chain import _fixture_router
        mock_get.side_effect = _fixture_router

        resolver = StreamResolver()
        resolved = resolver.resolve_stream({
            'page_url': 'https://fmoviess.org/film/burt-1423/',
            'id': 'srv-1', 'num': '1',
        })

        self.assertIsNotNone(resolved)
        self.assertIn('akcloud.animanga.fun', resolved)
        self.assertIn('Referer=', resolved)

if __name__ == '__main__':
    unittest.main()
