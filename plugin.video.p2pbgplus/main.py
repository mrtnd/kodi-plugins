# -*- coding: utf-8 -*-
"""P2PBG+ - fork of plugin.video.p2pbg 2026.09.24.01 (GPL-3.0, MartinStZ).

Browsing, search and the Elementum playback hand-off are kept exactly as the
working reference add-on. Added on top: a fail-closed VPN country gate before
playback and a Diagnostics screen showing the last error and the last URI
handed to Elementum.
"""
import os
import re
import sys
import json
import xbmc, xbmcplugin, xbmcgui, xbmcaddon
import urllib
import requests
import xbmcvfs
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
import urllib.parse

__addon__ = xbmcaddon.Addon()
__icon__ = __addon__.getAddonInfo('icon')
__cwd__ = xbmcvfs.translatePath(__addon__.getAddonInfo('path'))
__profile__ = xbmcvfs.translatePath(__addon__.getAddonInfo('profile'))
__icon_search__ = xbmcvfs.translatePath(os.path.join(__cwd__, 'resources', 'search.png'))
__icon_clear__ = xbmcvfs.translatePath(os.path.join(__cwd__, 'resources', 'clear.png'))
__icon_folders__ = xbmcvfs.translatePath(os.path.join(__cwd__, 'resources', 'movies.png'))
__icon_sresult__ = xbmcvfs.translatePath(os.path.join(__cwd__, 'resources', 'search-result.png'))
__icon_emptyfolder__ = xbmcvfs.translatePath(os.path.join(__cwd__, 'resources', 'empty.png'))

searchlist = __addon__.getSetting('search_history')

HISTORY_FILE = os.path.join(__profile__, 'search_history.json')
MAX_HISTORY = 20


def load_history():
    if xbmcvfs.exists(HISTORY_FILE):
        f = xbmcvfs.File(HISTORY_FILE, 'r')
        try:
            return json.loads(f.read())
        except:
            return []
        finally:
            f.close()
    return []


def save_history(history):
    if not xbmcvfs.exists(__profile__):
        xbmcvfs.mkdirs(__profile__)
    f = xbmcvfs.File(HISTORY_FILE, 'w')
    f.write(json.dumps(history))
    f.close()


def add_to_history(text, url):
    history = load_history()
    history = [h for h in history if h['text'] != text]
    history.insert(0, {'text': text, 'url': url})
    history = history[:MAX_HISTORY]
    save_history(history)


def Log(msg):
    try:
        xbmc.log('[P2PBG+] ' + msg, xbmc.LOGINFO)
    except Exception:
        pass


def Record(setting, value):
    try:
        __addon__.setSetting(setting, value or '')
    except Exception:
        pass


def Blocked(msg):
    """Unmissable reason why playback did not start."""
    Log(msg)
    Record('last_error', msg)
    xbmcgui.Dialog().ok('P2PBG+', msg)


def VPN_CHECK():
    """Fail-closed country gate. Returns True when playback may continue."""
    try:
        from resources.lib.vpngate import VPNGate
        country = __addon__.getSetting('vpn_country') or 'BG'
        ok, label = VPNGate(country=country).check()
    except Exception as exc:
        Record('last_error', 'VPN check error: ' + str(exc))
        return False
    if not ok:
        Blocked('VPN check failed (country: %s). Connect the VPN to %s and try again.'
                % (label, country))
        return False
    return True


def DIAGNOSTICS():
    try:
        from resources.lib.vpngate import VPNGate
        country = __addon__.getSetting('vpn_country') or 'BG'
        ok, label = VPNGate(country=country).check()
    except Exception as exc:
        ok, label = False, 'check error: ' + str(exc)
    try:
        elementum = 'installed'
        xbmcaddon.Addon('plugin.video.elementum')
    except Exception:
        elementum = 'NOT INSTALLED'
    lines = [
        'Elementum: ' + elementum,
        'VPN country: %s (required %s, gate %s)' % (label, country,
                                                    'OK' if ok else 'BLOCKED'),
        'User: ' + (__addon__.getSetting('p2pbg_user') or '(not set)'),
        'Profile: ' + __profile__,
        'Last play: ' + (__addon__.getSetting('last_play') or 'none'),
        'Last error: ' + (__addon__.getSetting('last_error') or 'none'),
    ]
    xbmcgui.Dialog().ok('P2PBG+ diagnostics', '\n'.join(lines))


def Notify(msg1, msg2):
    xbmc.executebuiltin((u'Notification(%s,%s,%s,%s)' % (msg1, msg2, '5000', __icon_folders__)))


if __addon__.getSetting('firstrun') == 'true':
    Notify('Settings', 'empty')
    __addon__.openSettings()
    __addon__.setSetting('firstrun', 'false')

if __addon__.getSetting('prefer_bgaudio') == 'true':
    bs = '&bgaudio=1'
else:
    bs = ''

if __addon__.getSetting('show_xxx') == 'true':
    xxx = True
else:
    xxx = False

if not __addon__.getSetting('p2pbg_user'):
    Notify('User', 'empty')
if not __addon__.getSetting('p2pbg_password'):
    Notify('Password', 'empty')

usr = __addon__.getSetting('p2pbg_user')
passwd = __addon__.getSetting('p2pbg_password')

__categories__ = [
    {'cat_ids': '60', 'cat_name': u'Филми 4K'},
    {'cat_ids': '68', 'cat_name': u'Филми HD'},
    {'cat_ids': '67', 'cat_name': u'Филми SD'},
    {'cat_ids': '59', 'cat_name': u'Филми VHS'},
    {'cat_ids': '11', 'cat_name': u'Филми DVD-R'},
    {'cat_ids': '69', 'cat_name': u'Филми Pack'},
    {'cat_ids': '34', 'cat_name': u'Български Филми'},
    {'cat_ids': '24', 'cat_name': u'Български Сериали'},
    {'cat_ids': '14;15', 'cat_name': u'Сериали'},
    {'cat_ids': '38', 'cat_name': u'Анимации'},
    {'cat_ids': '7', 'cat_name': u'Документални'},
    {'cat_ids': '64', 'cat_name': u'Футбол'},
    {'cat_ids': '5', 'cat_name': u'Формула 1'},
    {'cat_ids': '57', 'cat_name': u'Формула 2'}
]

UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
headers_new = {'user-agent': UA,
               'referer': 'https://www.p2pbg.com/',
               'host': 'www.p2pbg.com'
               }

s = requests.Session()

baseurl = 'https://www.p2pbg.com'
loginurl = '/login'
categoryurl = baseurl + '/torrents?category='
subpage = baseurl + '/torrents/'

bgsubs_flags = ["subs.gif","torrent-flag-subs-in-torrent.png","torrent-flag-external-subs.png","torrent-flag-subs-in-video.png"]
bgaudio_flags = ["bgaudio.gif","torrent-flag-bg-audio.png"]

url_prefix = '/torrents?category=1;5;7;11;14;15;16;17;18;24;34;35;38;58;59;60;51;57'
url_suffix = '&active=1&hidexxx='

if xxx == True:
    __categories__ += [
        {'cat_ids': '13;48;53;54', 'cat_name': u'XXX'}
    ]

    torrentsurl = baseurl + url_prefix + ';13;48;53;54' + url_suffix + 'off' + bs
else:
    torrentsurl = baseurl + url_prefix + url_suffix + 'on' + bs

# взимаме token
r = s.get(baseurl, headers=headers_new)
data_token = r.text

match_token = re.search('token".+?"(.+?)"', data_token)

if match_token:
    token = match_token.group(1)
else:
    token = ''

values = {'_token': token,
          'returnto': '',
          'uid': usr,
          'pwd': passwd}

r = s.post(baseurl + loginurl, data=values, headers=headers_new)


def CATEGORIES():
    FilmiYear = int(datetime.now().date().strftime("%Y"))

    addDir(u'Търсене', torrentsurl + '&search=', 5, '', __icon_search__)
    addDir(u'Последно добавени', torrentsurl, 1, '', __icon_folders__)
    addDir(u'Филми от ' + str(FilmiYear) + u' година', torrentsurl + '&search=' + str(FilmiYear), 1, '',
           __icon_folders__)
    addDir(u'Филми от ' + str(FilmiYear - 1) + u' година', torrentsurl + '&search=' + str(FilmiYear - 1), 1, '',
           __icon_folders__)
    addDir(u'Филми от ' + str(FilmiYear - 2) + u' година', torrentsurl + '&search=' + str(FilmiYear - 2), 1, '',
           __icon_folders__)

    for cat in __categories__:
        addDir(cat['cat_name'], categoryurl + cat['cat_ids'] + bs, 1, '', __icon_folders__)

    addDir('Диагностика', 'diagnostics', 7, '', __icon_folders__)


def INDEXPAGES(name, url):
    xbmcplugin.setContent(int(sys.argv[1]), 'movies')

    r = s.get(url, headers=headers_new)

    data = r.text

    soup = BeautifulSoup(data, 'html.parser')

    target_table = next(
        (
            t for t in soup.find_all("table")
            if t.get("width") == "100%"
               and t.get("class") == ["lista"]
               and len(t.attrs) == 2
        ),
        None
    )

    if not target_table:
        target_table = next(
            (
                t for t in soup.find_all("table")
                if t.get("class") == ["torrent-index__table"]
                   and len(t.attrs) == 1
            ),
            None
        )

    if target_table:
        rows = target_table.find_all("tr")

        for row in rows:
            desk = ''
            imdb_id = ''

            cols = row.find_all("td")

            if len(cols) < 3:
                continue

            # Magnet
            #magnet_tag = cols[1].find("a", href=True)

            magnet = None
            #for a in cols[1].find_all("a", href=True):
            #    if "magnet:?" in a["href"]:
            #        magnet = a["href"]
            #        break

            #if not magnet:
            #    continue

            # Линк "Свали"
            #download = cols[2].find("a")["href"]

            #if not download:
            #    continue
            download_match = re.search(r"showPreview\('(.+?)'", str(row))
            if not download_match:
                continue

            download = subpage + download_match.group(1)

            # --- IMDB ID и описание на филма/сериала ---
            r_page = s.get(download, headers=headers_new)
            data_page = r_page.text

            match_imdb_id = re.search(u'imdb.+?(tt.+?)/', data_page)
            if match_imdb_id:
                imdb_id = match_imdb_id.group(1)

            magnet_match = re.search('https://www.p2pbg.com/download.php.+?.torrent', data_page)

            if not magnet_match:
                continue

            torrent_url = magnet_match.group(0)

            # Заглавие на английски
            # match_eng = re.search(u'Заглавие на Английски.+?fieldValue">(.+?)<', data_page)
            # if match_eng:
            #    title = match_eng.group(1)
            # else:
            title = cols[1].find("a", onclick=True).get_text(strip=True)

            # --- Година на филма ---
            match_year = re.search(r'Година.+?(\d{4})', data_page)
            if match_year:
                year = match_year.group(1)
            else:
                year = ''

            # Жанр
            match_genre = re.search(u'Жанр.+?fieldValue">(.+?)<', data_page)

            if not match_genre:
                match_genre = re.search(u'Жанр.+?class="torrent-preview-fact__value">(.+?)<', data_page)

            if match_genre:
                genre = match_genre.group(1)
            else:
                genre = ''

            # Релийз
            match_release = re.search(u'Релийз.+?fieldValue">(.+?)<', data_page)

            if not match_release:
                match_release = re.search(u'Релийз.+?class="torrent-preview-fact__value">(.+?)<', data_page)

            if match_release:
                release = match_release.group(1)
            else:
                release = ''

            # Видео поток
            match_potok = re.search(u'Видео поток.+?fieldValue">(.+?)<', data_page)
            if match_potok:
                potok = match_potok.group(1)
            else:
                potok = ''

            # Резюме
            match_resume = re.search(u'Резюме.+?fieldValue">(.+?)<', data_page)

            if not match_resume:
                match_resume = re.search(u'Резюме.+?class="torrent-preview-fact__value">(.+?)<', data_page)

            if match_resume:
                resume = match_resume.group(1)
            else:
                resume = ''

            # SIZE
            size = cols[6].get_text(strip=True)

            # SEEDS
            seeds = int(cols[7].get_text(strip=True))

            # LEECHES
            leeches = int(cols[8].get_text(strip=True))

            # --- BG Subs ---
            bg_subs = "Да" if row.find("img", src=lambda x: x and any(x.endswith(s) for s in bgsubs_flags)) else "Не"

            # --- BG Audio ---
            bg_audio = "Да" if row.find("img", src=lambda x: x and any(x.endswith(s) for s in bgaudio_flags)) else "Не"

            if release != '':
                desk = desk + '[COLOR CC00FF00]Релийз: [/COLOR]' + str(release) + '\n'

            if potok != '':
                desk = desk + '[COLOR CC00FF00]Видео поток: [/COLOR]' + str(potok) + '\n'

            desk = desk + '[COLOR CC00FF00]Seeders: [/COLOR]' + str(
                seeds) + ' [COLOR CC00FF00]Leechers: [/COLOR]' + str(leeches) + '\n'
            desk = desk + '[COLOR CC00FF00]Размер: [/COLOR]' + str(size) + '\n'

            if year != '':
                desk = desk + '[COLOR CC00FF00]Година: [/COLOR]' + str(year) + '\n'

            if genre != '':
                desk = desk + '[COLOR CC00FF00]Жанр: [/COLOR]' + str(genre) + '\n'

            desk = desk + '[COLOR CC00FF00]БГ субтитри: [/COLOR]' + str(bg_subs) + '\n'
            desk = desk + '[COLOR CC00FF00]БГ аудио: [/COLOR]' + str(bg_audio)

            if resume != '':
                desk = desk + '\n\n[COLOR CC00FF00]Резюме: [/COLOR]' + str(resume)

            image_url = None

            for a in row.find_all("a", onmouseover=True):
                if "img src=" in a["onmouseover"]:
                    match = re.search(r"img src=([^ >]+)", a["onmouseover"])
                    if match:
                        image_url = match.group(1)
                        break

            if not image_url:
                match = re.search('data-overlib=\'&lt;img src="(.+?)"', str(row))
                if match:
                    image_url = match.group(1)

            # if bg_subs == 'Да':
            #    title = title + '[COLOR CC00FF00] | БГ субтитри[/COLOR]'

            # if bg_audio == 'Да':
            #    title = title + '[COLOR CC00FF00] | БГ аудио[/COLOR]'

            #r_magnet = s.get(torrent_url, headers=headers_new)
            #torrent_data = r_magnet.content

            #magnet = torrent_url_to_magnet(torrent_data, name=title)

            addLink(title, torrent_url, 2, desk, image_url, imdb_id)

        # Следваща страница
        next_page = None

        for a in soup.find_all("a", href=True):
            if a.get_text(strip=True) == ">":
                next_page = a["href"]
                break
        if next_page:
            addDir('[COLOR CC00FF00][B]Следваща страница>>[/B][/COLOR]', next_page, 1, '', '')
    else:
        pass


# Екран за търсене с история
def SEARCHSCREEN(base_url):
    addDir(u'Търсене', base_url, 4, '', __icon_search__)

    history = load_history()
    for item in history:
        addDir(item['text'], item['url'], 4, '', __icon_sresult__)

    if history:
        addDir(u'Изчисти историята', 'clear', 6, '', __icon_clear__)


def CLEARHISTORY():
    save_history([])
    xbmc.executebuiltin('Container.Refresh')


# Търсачка
def SEARCH(url):
    search_pos = url.find('&search=')
    if search_pos != -1:
        base_url = url[:search_pos + 8]
        prefill = url[search_pos + 8:]
    else:
        base_url = url
        prefill = ''

    if prefill:
        INDEXPAGES('Търсачка', url)
    else:
        keyb = xbmc.Keyboard('', 'Търсачка')
        keyb.doModal()
        if keyb.isConfirmed():
            searchText = urllib.parse.quote_plus(keyb.getText())
            searchText = searchText.replace('+', ' ')
            full_url = base_url + searchText
            add_to_history(keyb.getText(), full_url)
            INDEXPAGES('Търсачка', full_url)
        else:
            SEARCHSCREEN(base_url)


def PLAY(torrent_url, title=''):
    # Fail-closed VPN country gate (the only addition on this path).
    if not VPN_CHECK():
        return

    r = s.get(torrent_url, headers=headers_new)
    torrent_data = r.content

    if not torrent_data.startswith(b'd'):
        Log('download did not return a torrent, first bytes: %r'
            % torrent_data[:40])
        Blocked('The tracker did not return a .torrent file.')
        return

    # уверяваме се, че папката съществува
    if not xbmcvfs.exists(__profile__):
        xbmcvfs.mkdirs(__profile__)

    torrent_path = os.path.join(__profile__, "elementum_temp.torrent")

    # запис през xbmcvfs (по-правилно за Android)
    f = xbmcvfs.File(torrent_path, 'wb')
    f.write(torrent_data)
    f.close()

    uri = urllib.parse.quote_plus(torrent_path)

    elementum_url = f'plugin://plugin.video.elementum/play?uri={uri}'

    Log('resolved %s (%d bytes) for %s' % (elementum_url, len(torrent_data),
                                          title))
    Record('last_play', elementum_url)
    Record('last_error', '')

    li = xbmcgui.ListItem(path=elementum_url)
    li.setProperty('IsPlayable', 'true')

    li.setInfo('video', {'title': title})
    try:
        xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, li)
    except:
        Log('setResolvedUrl raised')
        Record('last_error', 'setResolvedUrl raised for ' + elementum_url)
        xbmc.executebuiltin("Notification('Грешка','Видеото липсва на сървъра!')")


def get_params():
    param = []
    paramstring = sys.argv[2]
    if len(paramstring) >= 2:
        params = sys.argv[2]
        cleanedparams = params.replace('?', '')
        if (params[len(params) - 1] == '/'):
            params = params[0:len(params) - 2]
        pairsofparams = cleanedparams.split('&')
        param = {}
        for i in range(len(pairsofparams)):
            splitparams = {}
            splitparams = pairsofparams[i].split('=')
            if (len(splitparams)) == 2:
                param[splitparams[0]] = splitparams[1]

    return param


def addDir(name, url, mode, plot, iconimage):
    u = sys.argv[0] + "?url=" + urllib.parse.quote_plus(url) + "&mode=" + str(
        mode) + "&name=" + urllib.parse.quote_plus(name) + "&iconimage=" + urllib.parse.quote_plus(iconimage)
    liz = xbmcgui.ListItem(name)

    ok = True
    liz.setArt({'thumb': iconimage, 'poster': iconimage, 'banner': iconimage, 'fanart': iconimage})
    liz.setInfo(type="Video", infoLabels={"Title": name, "plot": plot})
    ok = xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=u, listitem=liz, isFolder=True)
    return ok


def addLink(name, url, mode, plot, iconimage, imdb_id):
    u = sys.argv[0] + "?url=" + urllib.parse.quote_plus(url) + "&mode=" + str(
        mode) + "&name=" + urllib.parse.quote_plus(name)
    liz = xbmcgui.ListItem(name)

    ok = True
    liz.setArt({'thumb': iconimage, 'poster': iconimage, 'banner': iconimage, 'fanart': iconimage})
    liz.setInfo(type="Video", infoLabels={"Title": name, "plot": plot, 'IMDBNumber': imdb_id})
    liz.setProperty('fanart_image', iconimage)
    liz.setProperty("IsPlayable", "true")
    ok = xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=u, listitem=liz, isFolder=False)
    return ok


params = get_params()
url = None
name = None
iconimage = None
mode = None
count = None
groupID = None
ytpass = None

try:
    url = urllib.parse.unquote_plus(params["url"])
except:
    pass
try:
    name = urllib.parse.unquote_plus(params["name"])
except:
    pass
try:
    iconimage = urllib.parse.unquote_plus(params["iconimage"])
except:
    pass
try:
    mode = int(params["mode"])
except:
    pass
try:
    count = int(params["count"])
except:
    pass
try:
    groupID = int(params["groupID"])
except:
    pass
try:
    ytpass = urllib.parse.unquote_plus(params["ytpass"])
except:
    pass

if mode == None or url == None or len(url) < 1:
    print("")
    CATEGORIES()

elif mode == 5:
    SEARCHSCREEN(url)

elif mode == 4:
    print("" + url)
    SEARCH(url)

elif mode == 6:
    CLEARHISTORY()

elif mode == 7:
    DIAGNOSTICS()

elif mode == 1:
    print("" + url)
    INDEXPAGES(name, url)

elif mode == 2:
    print("" + url)
    PLAY(url, name or '')

xbmcplugin.endOfDirectory(int(sys.argv[1]))