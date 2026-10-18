# -*- coding: utf-8 -*-
"""Pure filmifen.com logic: URLs, card/list parsing, pagination, streams.

Fork of plugin.video.filmifen 2026.05.05.01 by MartinStZ (GPL-3.0).
Everything in this module is free of Kodi imports so it can be tested
offline against saved pages (see tests/).

What was broken in the reference add-on (why the fix exists):

* ``INDEXPAGES`` parsed listing cards with one regex that required a
  ``div.item__poster-category`` element. Series cards do not have that
  element, so the TV Shows listing (``/seriali/``) rendered empty and
  any series in search results was silently dropped.
* Pagination was parsed with a regex that required ``<span>N</span> <a``
  (with a literal space) and did not absolutize relative hrefs, so the
  TV Shows "next page" link was never rendered. Search pages paginate
  through ``javascript:list_submit(N)`` instead of links, which the old
  regex turned into a garbage URL.
* The root menu linked ``/hd_filmi_onlain/`` and ``/filmi_bg_audio/``,
  both of which the site now 301-redirects to the homepage, and scraped
  genre blocks with regexes that no longer match the markup.
* Below-the-fold cards lazy-load: ``src`` holds a 1x1 ``data:``
  placeholder and the real poster is in ``data-src``.

The listing cards on the live site have the shape::

    <a class="item item-poster grid-item" href="...">
      <div class="item-poster__img ...">
        <div class="item__poster-category">Драматични</div>   # movies only
        <div class="series-season__badge">                    # series only
          <span class="series-season__label">Се 1</span>
          <span class="series-season__number">Еп 8</span>
        </div>
        <img src="/uploads/...">
        <div class="item-poster__year"><time datetime="2026">...</time></div>
        <div class="film-quality-label"><abbr title="Full HD 1080p ...">...
      </div>
      <div class="item-poster__title ws-nowrap"> Тензинг </div>
    </a>

Pagination::

    <div class="pagination__pages d-flex">
      <span>1</span> <a href="https://filmifen.com/filmi/page/2/">2</a> ...
    </div>

Search results use ``<a href="#" onclick="javascript:list_submit(2)">``
instead of hrefs; ``list_submit(N)`` submits the search form with
``search_start=N``, whose semantics were verified against the live site
(``search_start=2`` -> results 25-48).
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

from bs4 import BeautifulSoup

BASE_URL = 'https://filmifen.com'

# The three sections kept by this fork (the rest of the reference menu was
# removed: dead redirects, broken genre scraping, year pages).
URL_MOVIES = BASE_URL + '/filmi/'
URL_MOVIES_HD = BASE_URL + '/hd-filmi-onlain/'
URL_TV_SHOWS = BASE_URL + '/seriali/'
URL_SEARCH = BASE_URL + '/index.php?do=search'

# Same UA the reference add-on used; the site serves the same markup to it.
UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36')

CARD_CLASS = 'item item-poster grid-item'

PLOT_COLOR = 'CC00FF00'


@dataclass
class Card:
    """One poster card of a listing/search page (site values as-is)."""

    title: str = ''
    url: str = ''
    thumb: str = ''
    category: str = ''
    year: str = ''
    quality: str = ''
    season: str = ''
    episode: str = ''

    @property
    def display_title(self):
        """Listing label; series cards get their season/episode appended.

        The site titles every episode of a series with the same name
        (e.g. "Кари"), so without the badge the TV Shows folder would
        show the same label for every episode.
        """
        badge = ' • '.join(part for part in (self.season, self.episode)
                           if part)
        if badge:
            return f'{self.title} ({badge})'
        return self.title

    def plot(self, description=''):
        """Plot text (English UI labels, site values as-is)."""
        lines = []
        for label, value in (('Category', self.category),
                             ('Year', self.year),
                             ('Quality', self.quality)):
            if value:
                lines.append(f'[COLOR {PLOT_COLOR}]{label}: [/COLOR]{value}')
        body = (description or '').strip()
        if body:
            if lines:
                lines.append('')
            lines.append(body)
        return '\n'.join(lines)


def search_page_url(story, start):
    """GET URL for a search results page.

    ``start`` is the DLE ``search_start`` value, which the site treats as
    the page number (1-based; verified live: start=2 -> results 25-48).
    """
    return '%s&subaction=search&search_start=%d&full_search=0&story=%s' % (
        URL_SEARCH, int(start), urllib.parse.quote_plus(story or ''))


def story_from_url(url):
    """Recover the search query from a search page URL, if it is one."""
    try:
        query = urllib.parse.urlparse(url or '').query
    except ValueError:
        return None
    if not query:
        return None
    values = urllib.parse.parse_qs(query).get('story') or []
    return values[0] if values else None


def parse_cards(html):
    """Parse the poster cards of a listing/search page.

    Cards without a link are skipped; an item without the movie-only
    category div still parses (series).
    """
    soup = BeautifulSoup(html or '', 'html.parser')
    cards = []
    for node in soup.find_all('a', attrs={'class': CARD_CLASS}):
        card = _card_from_node(node)
        if card is not None:
            cards.append(card)
    return cards


def parse_plot(html):
    """Description from a title page's ``meta[name=description]``."""
    soup = BeautifulSoup(html or '', 'html.parser')
    tag = soup.find('meta', attrs={'name': 'description'})
    if not tag:
        return ''
    return (tag.get('content') or '').strip()


def parse_next_page(html, story=None):
    """Next-page URL from the pagination block, or None on the last page.

    Handles both real hrefs (absolute or relative) and the search page's
    ``list_submit(N)`` links, for which ``story`` must be the search query.
    """
    soup = BeautifulSoup(html or '', 'html.parser')
    box = soup.find('div', class_='pagination__pages')
    if box is None:
        return None

    current_seen = False
    for child in box.find_all(['span', 'a']):
        if child.name == 'span':
            if (not child.get('class')
                    and child.get_text(strip=True).isdigit()):
                current_seen = True
            continue
        if not current_seen:
            continue

        href = (child.get('href') or '').strip()
        if href and href != '#' and not href.lower().startswith('javascript:'):
            return urllib.parse.urljoin(BASE_URL + '/', href)

        match = re.search(r'list_submit\((\d+)\)',
                          child.get('onclick') or '')
        if match:
            if story:
                return search_page_url(story, int(match.group(1)))
            return None
    return None


def parse_streams(html):
    """Player URLs from a title page.

    The reference add-on read the page's player object with two regexes
    (``:'http...'`` then ``:"http..."``) and filtered trailer/ad/schema
    noise. The same steps are kept here verbatim because this is the
    hand-off the resolver (script.module.findstreamurl) was proven with.
    """
    data = (html or '').replace(' ', '')
    links = re.findall(r":'http(.+?)'", data)
    if not links:
        links = re.findall(r':"http(.+?)"', data)

    streams = []
    for link in links:
        if re.search('youtube', link):
            continue
        if re.search('color', link):
            continue
        if re.search('schema', link):
            continue
        if re.search('filmifen', link):
            continue
        newurl = link
        if not re.search('http', newurl):
            newurl = 'http' + newurl
        streams.append(newurl)
    return streams


def _absolute(url):
    """Resolve a site-relative URL (``/uploads/...``) to an absolute one."""
    if not url:
        return ''
    url = url.strip()
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('/'):
        return BASE_URL + url
    return url


def _image_url(img):
    """Poster URL of a card image, ``data-src`` preferred.

    Below-the-fold cards lazy-load: ``src`` is a 1x1 ``data:`` placeholder
    and the real image sits in ``data-src`` (``srcset``/``data-srcset`` as
    a last resort). The reference add-on fed the data URI straight into
    the thumbnail URL, so every lazy card had a broken poster.
    """
    if img is None:
        return ''
    src = (img.get('src') or '').strip()
    if src.startswith('data:'):
        src = (img.get('data-src') or '').strip()
    if not src:
        for attr in ('srcset', 'data-srcset'):
            value = (img.get(attr) or '').strip()
            if value:
                src = value.split(',')[0].strip().split(' ')[0]
                break
    return _absolute(src)


def _text(node):
    return node.get_text(' ', strip=True) if node else ''


def _card_from_node(node):
    """Build a Card from one ``a.item.item-poster.grid-item`` node."""
    url = _absolute(node.get('href'))
    if not url:
        return None

    title = _text(node.find('div', class_='item-poster__title'))
    if not title:
        title = (node.get('aria-label') or '').strip()

    time_node = node.find('time')
    year = ''
    if time_node:
        year = (time_node.get('datetime')
                or time_node.get_text(strip=True) or '').strip()

    abbr_node = node.find('abbr')

    season = episode = ''
    badge = node.find('div', class_='series-season__badge')
    if badge:
        season = _text(badge.find('span', class_='series-season__label'))
        episode = _text(badge.find('span', class_='series-season__number'))

    return Card(
        title=title,
        url=url,
        thumb=_image_url(node.find('img')),
        category=_text(node.find('div', class_='item__poster-category')),
        year=year,
        quality=(abbr_node.get('title') or '').strip() if abbr_node else '',
        season=season,
        episode=episode,
    )
