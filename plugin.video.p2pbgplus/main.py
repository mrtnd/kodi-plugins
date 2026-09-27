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
            data = json.loads(f.read())
        except:
            return []
        finally:
            f.close()
        if isinstance(data, list):
            return [h for h in data if isinstance(h, dict)]
    return []


def save_history(history):
    if not xbmcvfs.exists(__profile__):
        xbmcvfs.mkdirs(__profile__)
    f = xbmcvfs.File(HISTORY_FILE, 'w')
    f.write(json.dumps(history))
    f.close()


def add_to_history(text, url=None):
    history = load_history()
    history = [h for h in history if h.get('text') != text]
    history.insert(0, {'text': text})
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

# Menu rebuilt from scratch: the entries below are the whole menu.
# Item URLs are compact (m/c/q/u/n keys) on purpose: the previous long
# listing-in-URL items did not always survive Kodi, and a lost query meant
# a dead click. Short values have nothing to lose.
SEARCH_CATEGORIES = '0'
ALL_CATEGORIES = '67;7;11;14;15;68;24;35;59;60;69'


def all_url():
    """All movies, TV shows and boxsets: the bare category URL."""
    return baseurl + '/torrents?category=' + ALL_CATEGORIES


def search_url(text):
    """Search over all categories, spaces plus-encoded as confirmed."""
    return listing_url(SEARCH_CATEGORIES,
                       search=urllib.parse.quote_plus(text or ''),
                       bgaudio=(bs != ''), show_xxx=xxx)


MENU_ITEMS = [
    (u'Търсене', {'m': '5'}),
    (u'Филми HD', {'m': '1', 'c': '68'}),
    (u'Филми 4K', {'m': '1', 'c': '60'}),
    (u'Сериали', {'m': '1', 'c': '14'}),
    (u'Сериали Boxset', {'m': '1', 'c': '15'}),
    (u'Всички филми и сериали', {'m': '1', 'c': ALL_CATEGORIES,
                                 'bare': '1'}),
]

# Labels from older menus, still resolvable so stale nodes keep working.
STALE_LABELS = {
    'Последно добавени': ('all', ''),
    'Филми SD': ('cat', '67'),
    'Филми VHS': ('cat', '59'),
    'Филми DVD': ('cat', '11'),
    'Филми DVD-R': ('cat', '11'),
    'Филми Pack': ('cat', '69'),
    'Български Филми': ('cat', '34'),
    'Български Сериали': ('cat', '24'),
    'Анимации': ('cat', '38'),
    'Документални': ('cat', '7'),
    'Филми GSM': ('cat', '35'),
    'Футбол': ('cat', '64'),
    'Формула 1': ('cat', '5'),
    'Формула 2': ('cat', '57'),
    'XXX': ('cat', '13;48;53;54'),
}


def build_item_url(params):
    """Compact plugin URL; ';' in categories stays literal."""
    parts = []
    for key in ('m', 'c', 'q', 'u', 'n', 'bare'):
        value = params.get(key)
        if value in (None, ''):
            continue
        if key in ('q', 'u', 'n'):
            value = urllib.parse.quote_plus(value)
        parts.append(key + '=' + value)
    return sys.argv[0] + '?' + '&'.join(parts)


def add_menu_item(label, params, iconimage):
    params = dict(params)
    params.setdefault('n', label)
    u = build_item_url(params)
    liz = xbmcgui.ListItem(label)
    liz.setArt({'thumb': iconimage, 'poster': iconimage,
                'banner': iconimage, 'fanart': iconimage})
    liz.setInfo(type="Video", infoLabels={"Title": label})
    xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=u, listitem=liz,
                                isFolder=True)
    return True

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

    add_menu_item(u'Търсене', {'m': '5'}, __icon_search__)
    for label, params in MENU_ITEMS[1:]:
        add_menu_item(label, params, __icon_folders__)

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
            add_menu_item('[COLOR CC00FF00][B]Следваща страница>>[/B][/COLOR]',
                          {'m': '1', 'u': next_page, 'n': name}, __icon_folders__)
    else:
        Record('last_items', '0')
        Log('results table not found for %s' % url)


# Екран за търсене с история
def SEARCHSCREEN():
    add_menu_item(u'Търсене', {'m': '10'}, __icon_search__)

    history = load_history()
    for item in history:
        text = item.get('text', '')
        if text:
            add_menu_item(text, {'m': '4', 'q': text}, __icon_sresult__)

    if history:
        add_menu_item(u'Изчисти историята', {'m': '6'}, __icon_clear__)


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

    The label survives even when the request query did not, and together
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
        SEARCHSCREEN()
        return True
    for menu_label, params in MENU_ITEMS[1:]:
        if menu_label == label:
            run_compact(params, label)
            return True
    if label in STALE_LABELS:
        kind, ids = STALE_LABELS[label]
        run_compact({'m': '1', 'c': ids} if kind == 'cat'
                    else {'m': '1', 'c': ALL_CATEGORIES, 'bare': '1'}, label)
        return True
    year = re.fullmatch(r'Филми от (\d{4}) година', label)
    if year:
        run_compact({'m': '4', 'q': year.group(1)}, label)
        return True
    # The label may be cut off mid-word, so accept a unique prefix match
    # ('Сериали' must not also match 'Сериали Boxset' - hence the exact
    # pass above).
    if len(label) >= 4:
        known = [menu_label for menu_label, _ in MENU_ITEMS[1:]]
        candidates = [menu_label for menu_label in known
                      if menu_label.startswith(label)
                      or label.startswith(menu_label)]
        if len(candidates) == 1:
            return resolve_label(candidates[0])
    return False


def run_compact(params, label=''):
    """Execute a compact menu request (m/c/q/u keys)."""
    mode = params.get('m')
    if mode == '1':
        cats = params.get('c', '')
        if params.get('bare') == '1' or cats == ALL_CATEGORIES:
            url = all_url()
        else:
            url = listing_url(cats, bgaudio=(bs != ''), show_xxx=xxx)
        INDEXPAGES(label or 'Категория', url)
    elif mode == '4':
        SEARCH(params.get('q', ''))
    elif mode == '5':
        SEARCHSCREEN()
    elif mode == '10':
        SEARCH()
    elif mode == '6':
        CLEARHISTORY()
    elif mode == '7':
        DIAGNOSTICS()
    elif mode == '9':
        CATEGORIES()
    else:
        Blocked('Cannot open "%s". Try it again from the menu.'
                % (label or 'this item'))


def SEARCH(query=None):
    """Run a search over all categories (category=0).

    With a query the search runs at once (history entry); without one the
    keyboard is shown first. Spaces stay plus-encoded, exactly like the
    confirmed search URL.
    """
    if query and '/torrents' in query:
        # Legacy full-URL history entry from an older release.
        INDEXPAGES(u'Търсене', query)
        return
    if query:
        add_to_history(query)
        INDEXPAGES(u'Търсене: ' + query, search_url(query))
        return
    # Dialog().input, not the Keyboard object: simpler, and immune to the
    # builds where the Keyboard attribute misbehaves.
    try:
        text = xbmcgui.Dialog().input(u'Търсене')
    except Exception as exc:
        Log('search input failed: %r' % (exc,))
        Record('last_error', 'search input failed: %r' % (exc,))
        Blocked('Search input is not available. Open Диагностика for details.')
        return
    if text and text.strip():
        SEARCH(text.strip())
    else:
        SEARCHSCREEN()


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
if not name:
    # compact items carry the label as 'n'; parse_qsl already decoded it
    name = params.get('n', '') or None


paramstring = sys.argv[2] if len(sys.argv) > 2 else ''
is_root = not paramstring or len(paramstring) < 2

# Compact menu parameters (m/c/q/u/n): short on purpose, so the query
# survives Kodi. Legacy mode/url/name below is only the fallback for nodes
# cached by older releases.
compact = {key: params.get(key) for key in ('m', 'c', 'q', 'u', 'n', 'bare')
           if params.get(key) not in (None, '')}

# What did Kodi actually hand us? Shown by Diagnostics, because a mangled
# query is the difference between a listing and the root menu reappearing.
Record('last_call', 'mode=%s url=%s raw=%s'
       % (compact.get('m', mode), (compact.get('u') or url or '')[:200],
          paramstring[:400]))
try:
    if compact.get('m') == '1' and compact.get('u'):
        # Next-page link: the only compact request carrying a full URL.
        INDEXPAGES(name or compact.get('n', '') or 'Категория', compact['u'])

    elif compact.get('m') in ('1', '4', '5', '6', '7', '9', '10'):
        run_compact(compact, name or compact.get('n', ''))

    elif compact:
        Log('unknown compact request: raw=%s' % paramstring)
        Record('last_error', 'unknown request')
        Blocked('Cannot open this item. Try it again from the menu.\n\nRequest: %s'
                % paramstring[:300])

    elif mode == None and is_root:
        # The real add-on root always shows the menu. Reopening the last
        # listing here stranded users on it: with no menu inside listings,
        # Back exits the add-on and reopening lands on the same list again,
        # so browsing became unreachable.
        print("")
        CATEGORIES()

    elif mode == None:
        if name and resolve_label(name):
            pass
        elif (url or recover_listing_url(paramstring)) and \
                '/torrents' in (url or recover_listing_url(paramstring)):
            address = url or recover_listing_url(paramstring)
            INDEXPAGES(name or GetSetting('last_category', 'Последно добавени'),
                       address)
        elif is_root:
            CATEGORIES()
        else:
            # Report with the request attached, do not substitute: showing other
            # content here is what made every category display previous results.
            Log('unresolvable call: raw=%s' % paramstring)
            Record('last_error', 'unresolvable call name=%s' % name)
            Blocked('Cannot open "%s". Try it again from the menu.\n\nRequest: %s'
                    % (name or compact.get('n', '') or 'this item',
                       paramstring[:300]))

    elif mode == 9:
        # Stale "Меню" entry: the menu is only ever rendered on request.
        CATEGORIES()

    elif mode == 7:
        DIAGNOSTICS()

    elif mode == 6:
        CLEARHISTORY()

    elif mode == 2:
        print("" + url)
        PLAY(url, name or '')

    elif mode == 5:
        SEARCHSCREEN()

    elif mode in (1, 4):
        address = url or recover_listing_url(paramstring)
        if not address and name and resolve_label(name):
            pass
        elif not address:
            Log('unresolvable call: mode=%s name=%s raw=%s'
                % (mode, name, paramstring))
            Record('last_error', 'unresolvable call: mode=%s' % mode)
            Blocked('Cannot open "%s". Try it again from the menu.\n\nRequest: %s'
                    % (name or 'this item', paramstring[:300]))
        elif mode == 4:
            print("" + address)
            SEARCH(address)
        else:
            print("" + address)
            INDEXPAGES(name, address)

    else:
        Log('unresolvable call: mode=%s url=%s raw=%s' % (mode, url, paramstring))
        Record('last_error', 'unresolvable call: mode=%s' % mode)
        Blocked('Cannot open "%s". Try it again from the menu.\n\nRequest: %s'
                % (name or 'this item', paramstring[:300]))

except Exception as exc:
    import traceback
    Log('dispatch failed: %r\n%s' % (exc, traceback.format_exc()))
    Record('last_error', 'dispatch failed: %r' % (exc,))
    Blocked('Error: %s\n\nRequest: %s'
            % (exc, paramstring[:300]))


# cacheToDisc=False: Kodi must never serve a saved copy of a live tracker
# listing, otherwise a revisited category shows the previous content.
xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=False)