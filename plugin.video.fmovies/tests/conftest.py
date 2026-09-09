import sys
import os

# Mock xbmc modules BEFORE any imports from resources
class MockXbmcAddon:
    def __init__(self, id='plugin.video.fmovies'):
        pass
    def getSetting(self, id):
        settings = {
            'base_url': 'https://fmoviess.org',
            'preferred_server': 'Server 1',
            'use_inputstream': 'true'
        }
        return settings.get(id, '')
    def setSetting(self, id, value):
        pass
    def getAddonInfo(self, id):
        return 'mock_value'

class MockXbmcGui:
    NOTIFICATION_INFO = 0
    def notification(self, *args, **kwargs):
        pass
    def ok(self, *args, **kwargs):
        pass
    def ListItem(self, *args, **kwargs):
        return MockListItem()
    def Dialog(self):
        return self

class MockListItem:
    def __init__(self):
        self.properties = {}
        self.art = {}
        self.info = {}
    def setProperty(self, k, v):
        self.properties[k] = v
    def setArt(self, art):
        self.art.update(art)
    def setInfo(self, type, info):
        self.info.update(info)
    def getVideoInfoTag(self):
        return self

sys.modules['xbmc'] = object()
sys.modules['xbmcgui'] = MockXbmcGui()
sys.modules['xbmcaddon'] = type('obj', (object,), {'Addon': MockXbmcAddon})
sys.modules['xbmcplugin'] = object()

# Add plugin directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
