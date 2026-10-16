# -*- coding: utf-8 -*-
"""p2pbg.com session and HTTP client.

The session set-up mirrors the working reference add-on on purpose: its
Elementum hand-off is the only version confirmed to play on the target TV.
"""
from __future__ import annotations

import re

import requests

from resources.lib import kodi_utils as ku
from resources.lib import p2pbg

UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like '
      'Gecko) Chrome/67.0.3396.99 Safari/537.36')

baseurl = p2pbg.BASE_URL
loginurl = p2pbg.LOGIN_URL

headers_new = {'user-agent': UA,
               'referer': 'https://www.p2pbg.com/',
               'host': 'www.p2pbg.com'
               }

s = requests.Session()
_logged_in = False


def login():
    """Log in once per process; safe to call on every request."""
    global _logged_in
    if _logged_in:
        return
    r = s.get(baseurl, headers=headers_new)
    data_token = r.text

    match_token = re.search('token".+?"(.+?)"', data_token)

    if match_token:
        token = match_token.group(1)
    else:
        token = ''

    values = {'_token': token,
              'returnto': '',
              'uid': ku.get_setting(ku.S_USER),
              'pwd': ku.get_setting(ku.S_PASSWORD)}

    s.post(baseurl + loginurl, data=values, headers=headers_new)
    _logged_in = True
    ku.log('logged in as %s' % (ku.get_setting(ku.S_USER) or '(no user)'))


def get(url):
    login()
    return s.get(url, headers=headers_new)


def fetch_torrent(url):
    """Raw .torrent bytes for a download.php address."""
    login()
    return s.get(url, headers=headers_new).content


def listing(url):
    """(rows, next_page_url) for a listing/search address.

    Every row is enriched from its own details page; rows are then filtered
    (no 4K) and ordered most-active-first so it is obvious what is hot now.
    """
    from bs4 import BeautifulSoup

    response = get(url)
    html = response.text
    soup = BeautifulSoup(html, 'html.parser')

    table = p2pbg.find_results_table(soup)
    ku.set_setting(ku.S_LAST_TABLE, 'found' if table else 'NOT FOUND')

    rows = []
    if table:
        for row in table.find_all('tr'):
            try:
                download_id = p2pbg.row_download_id(row)
                if not download_id:
                    continue
                details = p2pbg.parse_details(
                    get(p2pbg.SUBPAGE + download_id).text)
                parsed = p2pbg.parse_row(row, details)
                if parsed:
                    rows.append(parsed)
            except Exception as exc:
                ku.log('row skipped: %r' % (exc,))
                continue
    else:
        ku.log('results table not found for %s' % url)

    return p2pbg.sort_rows(rows), p2pbg.next_page_url(soup)
