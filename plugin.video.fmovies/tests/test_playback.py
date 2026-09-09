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
            return 'Server'
        return 'https://fmoviess.org'
    def setSetting(self, id, value):
        pass
    def getAddonInfo(self, id):
        return 'mock_value'

class MockListItem:
    def __init__(self, path=None):
        self.properties = {}
        if path:
            self.properties['path'] = path
        self.art = {}
        self.info = {}
    def setPath(self, path):
        self.properties['path'] = path
    def setProperty(self, k, v):
        self.properties[k] = v
        # Also store with lower case or exact key
    def getProperty(self, k):
        return self.properties.get(k)
    def setMimeType(self, mime):
        self.properties['mimetype'] = mime
    def setContentLookup(self, flag):
        self.properties['contentlookup'] = flag
    def setSubtitles(self, subs):
        self.properties['subtitles'] = list(subs)
    def setArt(self, art):
        self.art.update(art)
    def setInfo(self, type, info):
        self.info.update(info)
    def getVideoInfoTag(self):
        return self

class MockXbmcGui:
    NOTIFICATION_INFO = 0
    def notification(self, *args, **kwargs): pass
    def ok(self, *args, **kwargs): pass
    def ListItem(self, path=None, **kwargs): return MockListItem(path)
    def Dialog(self): return self

sys.modules['xbmc'] = type('obj', (object,), {})
sys.modules['xbmcgui'] = MockXbmcGui()
sys.modules['xbmcaddon'] = type('obj', (object,), {'Addon': MockXbmcAddon})
sys.modules['xbmcplugin'] = type('obj', (object,), {
    'setResolvedUrl': lambda handle, succeeded, listitem: setattr(MockXbmcPlugin, 'resolved', (succeeded, listitem))
})
sys.modules['inputstreamhelper'] = type('obj', (object,), {
    'Helper': lambda *args, **kwargs: type('obj', (object,), {
        'check_inputstream': lambda self: False,
        'inputstream_addon': 'inputstream.adaptive'
    })()
})

sys.modules['xbmcplugin'] = type('obj', (object,), {
    'setResolvedUrl': lambda handle, succeeded, listitem: setattr(MockXbmcPlugin, 'resolved', (succeeded, listitem))
})

class MockXbmcPlugin:
    resolved = None

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import patch, MagicMock
from resources.lib.scraper import FMoviesScraper
from resources.lib.resolver import StreamResolver
import main

class TestPlaybackHandOff(unittest.TestCase):
    @patch('resources.lib.resolver.requests.Session.get')
    def test_play_stream_success(self, mock_get):
        try:
            from test_chain import _fixture_router
        except ImportError:
            from tests.test_chain import _fixture_router

        # Browser-like replay: real film page fixture, live-shaped netoda
        # responses, recorded vidnest payload, verified m3u8 playlist.
        mock_get.side_effect = _fixture_router

        main.play_stream('https://fmoviess.org/film/burt-1423/', 'Burt')

        succeeded, listitem = MockXbmcPlugin.resolved
        self.assertTrue(succeeded)
        self.assertIn('animanga.fun', listitem.properties.get('path', ''))
        self.assertEqual(listitem.properties.get('inputstream'), 'inputstream.adaptive')
        self.assertEqual(listitem.properties.get('inputstream.adaptive.manifest_type'), 'hls')
        # Segment requests need the headers too, or playback stalls silently.
        manifest_headers = listitem.properties.get('inputstream.adaptive.manifest_headers', '')
        stream_headers = listitem.properties.get('inputstream.adaptive.stream_headers', '')
        self.assertIn('Referer=', manifest_headers)
        self.assertIn('Referer=', stream_headers)
        self.assertEqual(listitem.properties.get('mimetype'), 'application/vnd.apple.mpegurl')
        self.assertEqual(listitem.properties.get('contentlookup'), False)

if __name__ == '__main__':
    unittest.main()
