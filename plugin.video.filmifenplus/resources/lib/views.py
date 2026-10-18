# -*- coding: utf-8 -*-
"""Screens: root menu, listings, search and stream selection.

The root menu shows exactly the four entries this fork keeps:

    Search      -> the site search form (POST)
    Movies      -> https://filmifen.com/filmi/
    Movies HD   -> https://filmifen.com/hd-filmi-onlain/
    TV Shows    -> https://filmifen.com/seriali/

Every other reference entry was removed because it no longer works:
``/hd_filmi_onlain/`` and ``/filmi_bg_audio/`` 301-redirect to the
homepage, the year pages are redundant with Movies, and the scraped
genre entries were built by regexes that no longer match the markup.
"""
from __future__ import annotations

from resources.lib import filmifen
from resources.lib import http
from resources.lib import kodi_utils as ku

NEXT_PAGE_LABEL = 'Next page >>'
STREAM_LABEL = 'Stream %d: %s'


def menu():
    """Root menu. Only ever rendered at the add-on root (or on request)."""
    ku.set_content('files')
    ku.add_dir('Search', filmifen.URL_SEARCH, ku.MODE_SEARCH, ku.SEARCH_ICON)
    ku.add_dir('Movies', filmifen.URL_MOVIES, ku.MODE_LISTING, ku.MOVIE_ICON)
    ku.add_dir('Movies HD', filmifen.URL_MOVIES_HD, ku.MODE_LISTING,
               ku.MOVIE_ICON)
    ku.add_dir('TV Shows', filmifen.URL_TV_SHOWS, ku.MODE_LISTING,
               ku.MOVIE_ICON)


def listing(url):
    """Movies / Movies HD / TV Shows listing (and search result pages)."""
    ku.set_content('tvshows' if '/seriali/' in (url or '') else 'movies')
    html = http.get(url)
    count = _render_cards(html, current_url=url)
    ku.log('listing %s -> %d items' % (url, count))
    if count == 0:
        ku.show_error('No items found. The site may have changed;\n'
                      'please report at the add-on repository.')


def search():
    """Search screen: keyboard, POST to the site's search form, results."""
    text = ku.keyboard('Search')
    if text is None:
        # Cancelled: close the (empty) directory; never re-render the
        # root menu as a side effect of a cancelled action.
        ku.log('search cancelled')
        return
    story = text.strip()
    if not story:
        ku.notify('Empty search')
        return

    ku.set_content('movies')
    html = http.post(filmifen.URL_SEARCH, {
        'do': 'search',
        'subaction': 'search',
        'story': story,
    })
    count = _render_cards(html, story=story)
    ku.log('search %r -> %d items' % (story, count))
    if count == 0:
        ku.notify('No results for "%s"' % story)


def streams(name, url, plot='', iconimage=''):
    """Stream list for one title page (reference logic, reference labels)."""
    ku.set_content('movies')
    urls = filmifen.parse_streams(http.get(url))
    ku.log('title %s -> %d streams' % (url, len(urls)))
    if not urls:
        ku.show_error('No streams found for "%s".' % (name or 'this title'))
        return
    for index, stream in enumerate(urls, 1):
        ku.add_play(STREAM_LABEL % (index, name), stream, ku.MODE_PLAY,
                    iconimage, plot)


def _render_cards(html, current_url='', story=None):
    """Render parsed cards plus the next-page entry; return the count."""
    cards = filmifen.parse_cards(html)
    for card in cards:
        ku.add_link(card.display_title, card.url, ku.MODE_STREAMS,
                    card.thumb, card.plot(_description(card.url)))

    # Search pages encode paging as list_submit(N); the query comes from
    # the POST (first page) or from the current page's URL (page N+1).
    if story is None:
        story = filmifen.story_from_url(current_url)
    next_url = filmifen.parse_next_page(html, story=story)
    if next_url:
        ku.add_dir(NEXT_PAGE_LABEL, next_url, ku.MODE_LISTING, ku.MOVIE_ICON)

    return len(cards)


def _description(url):
    """Title-page description; a failed fetch never breaks the listing."""
    try:
        return filmifen.parse_plot(http.get(url))
    except Exception as exc:
        ku.log('description fetch failed for %s: %r' % (url, exc))
        return ''
