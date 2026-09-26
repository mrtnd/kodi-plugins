import sys
import os


class MockAddon:
    def __init__(self, id='plugin.video.p2pbg'):
        self._settings = {
            'base_url': 'https://www.p2pbg.com',
            'p2pbg_user': '', 'p2pbg_password': '',
            'vpn_country': 'BG', 'prefer_bgaudio': 'true',
            'min_seeders': '1', 'show_xxx': 'false', 'search_history': '',
        }

    def getSetting(self, key):
        return self._settings.get(key, '')

    def setSetting(self, key, value):
        self._settings[key] = value

    def getAddonInfo(self, key):
        return 'mock_' + key


class MockDialog:
    def notification(self, *a, **k):
        pass

    def ok(self, *a, **k):
        pass

    def input(self, *a, **k):
        return ''


class MockGui:
    NOTIFICATION_INFO = 0
    Dialog = MockDialog

    class ListItem:
        def __init__(self, label=None, path=None):
            self.label = label
            self.path = path

        def setProperty(self, k, v):
            pass

        def getVideoInfoTag(self):
            return self


class MockPlugin:
    @staticmethod
    def addDirectoryItem(**kwargs):
        pass

    @staticmethod
    def setPluginCategory(*a, **k):
        pass

    @staticmethod
    def setContent(*a, **k):
        pass

    @staticmethod
    def endOfDirectory(*a, **k):
        pass

    @staticmethod
    def setResolvedUrl(*a, **k):
        pass


sys.modules['xbmc'] = type('xbmc', (), {'log': staticmethod(lambda *a, **k: None)})()
sys.modules['xbmcgui'] = MockGui()
sys.modules['xbmcaddon'] = type('xbmcaddon', (), {'Addon': MockAddon})()
sys.modules['xbmcplugin'] = MockPlugin()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
