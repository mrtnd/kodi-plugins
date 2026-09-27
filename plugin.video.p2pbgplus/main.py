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
        'Last call: ' + (__addon__.getSetting('last_call') or 'none'),
        'Last listing: ' + ((__addon__.getSetting('last_category') or '?') + ' -> '
                            + (GetSetting('last_listing') or 'none')),
        'Table: ' + (__addon__.getSetting('last_table') or '?')
        + ', items: ' + (__addon__.getSetting('last_items') or '?'),
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

# Browsing menu: exactly the "Movies" optgroup of the tracker's own
# Категория dropdown (p2pbg.com/1.html snapshot). IDs outside it are dead on
# the current site and make the tracker answer with an unrelated listing.
__categories__ = [
    {'cat_ids': '60', 'cat_name': u'Филми 4K'},
    {'cat_ids': '68', 'cat_name': u'Филми HD'},
    {'cat_ids': '67', 'cat_name': u'Филми SD'},
    {'cat_ids': '59', 'cat_name': u'Филми VHS'},
    {'cat_ids': '11', 'cat_name': u'Филми DVD'},
    {'cat_ids': '69', 'cat_name': u'Филми Pack'},
    {'cat_ids': '34', 'cat_name': u'Български Филми'},
    {'cat_ids': '24', 'cat_name': u'Български Сериали'},
    {'cat_ids': '14', 'cat_name': u'Сериали'},
    {'cat_ids': '15', 'cat_name': u'Сериали Boxset'},
    {'cat_ids': '38', 'cat_name': u'Анимации'},
    {'cat_ids': '7', 'cat_name': u'Документални'},
    {'cat_ids': '35', 'cat_name': u'Филми GSM'},
]

UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
headers_new = {'user-agent': UA,
               'referer': 'https://www.p2pbg.com/',
               'host': 'www.p2pbg.com'
               }

s = requests.Session()

baseurl = 'https://www.p2pbg.com'
loginurl = '/login'
subpage = baseurl + '/torrents/'

# Categories for "Последно добавени": same Movies set as the menu.
latest_categories = '7;11;14;15;24;34;35;38;59;60;67;68;69'


def listing_url(categories, search='', bgaudio=False, show_xxx=False):
    """Listing/search URL in the exact shape of the site's search form.

    The tracker only honours the filters when the whole form query is
    present (fake*remembered fields, search, category, active, bgaudio,
    hidexxx), and hidexxx is a boolean flag (1/0), not on/off.
    """
    url = (baseurl + '/torrents?fakeusernameremembered=&fakepasswordremembered=&search='
           + search + '&category=' + categories + '&active=1')
    if bgaudio:
        url += '&bgaudio=1'
    return url + '&hidexxx=' + ('0' if show_xxx else '1')


def to_int(text):
    """Never raise on '---' or empty cells; a dead row must not kill the
    whole listing (Kodi then keeps showing the previous menu)."""
    try:
        return int(str(text).replace('\u00a0', '').replace(' ', '')
                   .replace(',', '').strip())
    except (TypeError, ValueError):
        return 0

bgsubs_flags = ["subs.gif","torrent-flag-subs-in-torrent.png","torrent-flag-external-subs.png","torrent-flag-subs-in-video.png"]
bgaudio_flags = ["bgaudio.gif","torrent-flag-bg-audio.png"]

if xxx == True:
    latest_categories += ';13;48;53;54'

torrentsurl = listing_url(latest_categories, bgaudio=(bs != ''), show_xxx=xxx)

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
    # 'files' keeps the menu rendering as folders; without this Kodi can
    # inherit 'movies' from the previous directory and draw every menu entry
    # as a video file.
    xbmcplugin.setContent(int(sys.argv[1]), 'files')

    FilmiYear = int(datetime.now().date().strftime("%Y"))

    addDir(u'Търсене', torrentsurl, 5, '', __icon_search__)
    addDir(u'Последно добавени', torrentsurl, 1, '', __icon_folders__)
    addDir(u'Филми от ' + str(FilmiYear) + u' година',
           listing_url(latest_categories, search=str(FilmiYear),
                       bgaudio=(bs != ''), show_xxx=xxx), 1, '',
           __icon_folders__)
    addDir(u'Филми от ' + str(FilmiYear - 1) + u' година',
           listing_url(latest_categories, search=str(FilmiYear - 1),
                       bgaudio=(bs != ''), show_xxx=xxx), 1, '',
           __icon_folders__)
    addDir(u'Филми от ' + str(FilmiYear - 2) + u' година',
           listing_url(latest_categories, search=str(FilmiYear - 2),
                       bgaudio=(bs != ''), show_xxx=xxx), 1, '',
           __icon_folders__)

    for cat in __categories__:
        addDir(cat['cat_name'],
               listing_url(cat['cat_ids'], bgaudio=(bs != ''), show_xxx=xxx),
               1, '', __icon_folders__)

    addDir('Диагностика', 'diagnostics', 7, '', __icon_folders__)


def data_row_count(table):
    """Rows that look like real torrent rows (9 cells)."""
    return sum(1 for row in table.find_all('tr')
               if len(row.find_all('td')) >= 9)


def find_results_table(soup):
    """The results table, not the 'recommended' block above it.

    The proven exact match first; if the site changes attributes, fall back
    to the torrent-index table holding the most torrent rows.
    """
    exact = next(
        (
            t for t in soup.find_all("table")
            if t.get("width") == "100%"
               and t.get("class") == ["lista"]
               and len(t.attrs) == 2
        ),
        None
    )
    if exact:
        return exact
    exact = next(
        (
            t for t in soup.find_all("table")
            if t.get("class") == ["torrent-index__table"]
               and len(t.attrs) == 1
        ),
        None
    )
    if exact:
        return exact
    candidates = [t for t in soup.find_all("table")
                  if t.get("class") and 'torrent-index__table' in t.get("class")
                  and data_row_count(t)]
    if not candidates:
        return None
    return max(candidates, key=data_row_count)


def INDEXPAGES(name, url):
    xbmcplugin.setContent(int(sys.argv[1]), 'movies')

    # Remember where we were so the add-on can reopen it instead of the root
    # menu, and record it for Diagnostics.
    Record('last_listing', url)
    Record('last_category', name or 'Последно добавени')

    try:
        r = s.get(url, headers=headers_new)
        data = r.text
    except Exception as exc:
        # Kodi keeps the previous directory on screen when a plugin dies
        # before endOfDirectory, which looks like a stuck/duplicated menu.
        Record('last_items', '0')
        Log('listing request failed for %s: %r' % (url, exc))
        Blocked('Failed to load the listing.\n\n%s' % exc)
        return

    soup = BeautifulSoup(data, 'html.parser')

    target_table = find_results_table(soup)
    Record('last_table', 'found' if target_table else 'NOT FOUND')

    counted = [0]

    if target_table:
        rows = target_table.find_all("tr")

        for row in rows:
            # One malformed row must never abort the listing: Kodi
            # keeps the previous directory on screen otherwise.
            try:
                desk = ''
                imdb_id = ''

                cols = row.find_all("td")

                if len(cols) < 9:
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
                title_anchor = cols[1].find("a", onclick=True)
                if title_anchor is None:
                    continue
                title = title_anchor.get_text(' ', strip=True)

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

                # SIZE / SEEDS / LEECHES (0 cat, 1 name, 2 download,
                # 3 comments, 4 date, 5 size, 6 seeds, 7 leeches, 8 snatched)
                size = cols[5].get_text(' ', strip=True)

                # SEEDS / LEECHES - '---' must not raise
                seeds = to_int(cols[6].get_text(strip=True))

                leeches = to_int(cols[7].get_text(strip=True))

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
                counted[0] += 1

            except Exception as exc:
                Log('row skipped: %r' % (exc,))
                continue

        Record('last_items', str(counted[0]))

        # Следваща страница
        next_page = None

        for a in soup.find_all("a", href=True):
            if a.get_text(strip=True) == ">":
                next_page = a["href"]
                break
        if next_page:
            addDir('[COLOR CC00FF00][B]Следваща страница>>[/B][/COLOR]', next_page, 1, '', '')
    else:
        Record('last_items', '0')
        Log('results table not found for %s' % url)


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
def search_value(url):
    """Current value of the search= parameter ('' when absent)."""
    _head, sep, tail = url.partition('&search=')
    if not sep:
        return ''
    return tail.partition('&')[0]


def with_search(url, text=''):
    """Replace only the search= value.

    The tracker honours the filters only when the whole form query is
    present (category/active/hidexxx) with literal ';' separators, so the
    query must not be rebuilt with urlencode.
    """
    head, sep, tail = url.partition('&search=')
    if not sep:
        return url + ('&search=' + text if text else '')
    rest = tail.partition('&')
    return head + '&search=' + text + ('&' + rest[2] if rest[1] else '')


def resolve_label(label):
    """Best-effort action for a menu click that lost its parameters.

    The label survives even when the long listing URL did not, and together
    with the settings it is everything the request needs.
    Returns True when something was rendered.
    """
    if not label:
        return False
    label = label.strip().rstrip('/')
    if label == 'Меню':
        CATEGORIES()
        return True
    if label == 'Диагностика':
        DIAGNOSTICS()
        return True
    if label == 'Търсене':
        SEARCHSCREEN(torrentsurl)
        return True
    if label == 'Последно добавени':
        prefs = (bs != '', xxx)
        INDEXPAGES('Последно добавени',
                   listing_url(latest_categories, bgaudio=prefs[0],
                               show_xxx=prefs[1]))
        return True
    year = re.fullmatch(r'Филми от (\d{4}) година', label)
    if year:
        INDEXPAGES(label, listing_url(latest_categories, search=year.group(1),
                                      bgaudio=(bs != ''), show_xxx=xxx))
        return True
    for cat in __categories__:
        if cat['cat_name'] == label:
            INDEXPAGES(label, listing_url(cat['cat_ids'],
                                          bgaudio=(bs != ''), show_xxx=xxx))
            return True
    # The label may be cut off mid-word, so accept a unique prefix match
    # ('Сериали' must not also match 'Сериали Boxset' - hence the exact
    # pass above).
    if len(label) >= 4:
        candidates = [cat for cat in __categories__
                      if cat['cat_name'].startswith(label)
                      or label.startswith(cat['cat_name'])]
        if len(candidates) == 1:
            cat = candidates[0]
            INDEXPAGES(cat['cat_name'],
                       listing_url(cat['cat_ids'],
                                   bgaudio=(bs != ''), show_xxx=xxx))
            return True
    return False


def SEARCH(url):
    prefill = search_value(url)

    if prefill:
        INDEXPAGES('Търсачка', url)
    else:
        # xbmcgui.Keyboard, not xbmc.Keyboard (the latter does not exist and
        # used to raise before the search screen could be shown).
        keyb = xbmcgui.Keyboard('', 'Търсачка')
        keyb.doModal()
        if keyb.isConfirmed():
            searchText = urllib.parse.quote_plus(keyb.getText())
            searchText = searchText.replace('+', ' ')
            full_url = with_search(url, searchText)
            add_to_history(keyb.getText(), full_url)
            INDEXPAGES('Търсачка', full_url)
        else:
            SEARCHSCREEN(url)


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


def recover_listing_url(paramstring):
    """Dig a listing URL out of a (possibly mangled) plugin query.

    The listing address is part of the item URL, so it survives even when the
    mode/url parameters do not. Understands the plain and the (double)
    percent-encoded form and stops at the plugin's own parameters
    (mode/name/iconimage), so a listing query is never truncated.
    """
    if not paramstring:
        return ''
    flat = urllib.parse.unquote_plus(paramstring)
    # a query that was encoded twice keeps '?' and '=' percent-encoded
    flat = flat.replace('%3F', '?').replace('%3f', '?')
    head = flat.find('https://')
    if head < 0:
        return ''
    marker = '/torrents?'
    found = flat.find(marker, head)
    if found < 0:
        return ''
    tail = flat[found + len(marker):]
    stop = len(tail)
    for name in ('&mode=', '&name=', '&iconimage=', '&groupid=', '&count=',
                 '&ytpass='):
        pos = tail.lower().find(name)
        if pos >= 0:
            stop = min(stop, pos)
    url = urllib.parse.unquote_plus(
        flat[head:found + len(marker)] + tail[:stop])
    if 'category=' not in url and 'search=' not in url:
        return ''
    return url


def get_params():
    """Parse the plugin query.

    parse_qsl (not a hand-rolled split) so a trailing slash, a blank value
    such as search= or any stray character cannot drop mode/url and land
    the user back in the root menu.
    """
    paramstring = sys.argv[2] if len(sys.argv) > 2 else ''
    if not paramstring or len(paramstring) < 2:
        return {}
    return dict(urllib.parse.parse_qsl(paramstring.lstrip('?'),
                                       keep_blank_values=True))


def GetSetting(setting, default=''):
    try:
        value = __addon__.getSetting(setting)
    except Exception:
        return default
    return value if value != '' else default


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


paramstring = sys.argv[2] if len(sys.argv) > 2 else ''
is_root = not paramstring or len(paramstring) < 2
recovered = recover_listing_url(paramstring)

# What did Kodi actually hand us? Shown by Diagnostics, because a mangled
# query is the difference between a listing and the root menu reappearing.
Record('last_call', 'mode=%s url=%s raw=%s'
       % (mode, (url or '')[:200], paramstring[:400]))

if not url:
    url = recovered

if mode == None and is_root:
    # The real add-on root: reopen the last listing, or show the menu once.
    if GetSetting('start_at_last') == 'true' and GetSetting('last_listing'):
        INDEXPAGES(GetSetting('last_category', 'Последно добавени'),
                   GetSetting('last_listing'))
    else:
        print("")
        CATEGORIES()

elif mode == None:
    if name and resolve_label(name):
        pass
    elif url and '/torrents' in url:
        INDEXPAGES(name or GetSetting('last_category', 'Последно добавени'),
                   url)
    elif is_root:
        CATEGORIES()
    else:
        # Report, do not substitute: showing the last viewed listing here is
        # what made every category display the previous search results.
        Log('unresolvable call: mode=None name=%s url=%s raw=%s'
            % (name, url, paramstring))
        Record('last_error', 'unresolvable call: mode=None name=%s' % name)
        Blocked('Cannot open "%s". Try it again from the menu.'
                % (name or 'this item'))

elif mode == 9:
    # Explicit "Меню" entry: the menu is only ever rendered on request.
    CATEGORIES()

elif mode == 7:
    DIAGNOSTICS()

elif mode == 6:
    CLEARHISTORY()

elif mode == 2:
    print("" + url)
    PLAY(url, name or '')

elif mode == 5:
    SEARCHSCREEN(url or torrentsurl)

elif mode in (1, 4):
    if not url and name and resolve_label(name):
        pass
    elif not url:
        Log('unresolvable call: mode=%s name=%s raw=%s'
            % (mode, name, paramstring))
        Record('last_error', 'unresolvable call: mode=%s' % mode)
        Blocked('Cannot open this item: no listing address in the request. '
                'Open Диагностика for the recorded request.')
    elif mode == 4:
        print("" + url)
        SEARCH(url)
    else:
        print("" + url)
        INDEXPAGES(name, url)

else:
    Log('unresolvable call: mode=%s url=%s raw=%s' % (mode, url, paramstring))
    Record('last_error', 'unresolvable call: mode=%s' % mode)
    Blocked('Cannot open this item (mode=%s). Open Диагностика for the '
            'recorded request.' % mode)

xbmcplugin.endOfDirectory(int(sys.argv[1]))