import re
from urllib.parse import urlencode, urljoin

import requests  # kept: tests patch resources.lib.scraper.requests.Session.get
from resources.lib.http import (
    HTML_HEADERS, decode_html, fetch_soup, make_session, normalize_base_url,
)
from resources.lib.kodi_utils import get_setting

# Re-exported for back-compat (tests import decode_html from scraper).
__all__ = ['FMoviesScraper', 'decode_html']

CARD_SELECTORS = '.card.bg-transparent.border-0.h-100, div.col .card'
CARD_FALLBACK = 'div.col, .card'

SEARCH_THUMB = 'https://img.cdno.my.id/thumb/w_200/h_300/{}.jpg'


class FMoviesScraper:
    def __init__(self):
        self.session = make_session(HTML_HEADERS)
        self.base_url = normalize_base_url(get_setting('base_url'))

    def _get_soup(self, url):
        return fetch_soup(self.session, url)

    # -- catalog ------------------------------------------------------
    def get_catalog(self, path_or_url):
        url = (path_or_url if path_or_url.startswith('http')
               else urljoin(self.base_url, path_or_url))
        soup = self._get_soup(url)
        cards = soup.select(CARD_SELECTORS) or soup.select(CARD_FALLBACK)
        items = [item for card in cards
                 if (item := self._parse_card(card)) is not None]
        return items, self._parse_next_page(soup)

    def _parse_card(self, card):
        title_el = card.select_one('.card-title, h2, h3, .film-name')
        link_el = card.select_one('a[href*="/film/"], a[href*="/tv/"], a.rounded')
        if not link_el:
            link_el = card.select_one('a')
        if not link_el or not link_el.get('href'):
            return None
        link = link_el.get('href')
        title = self._card_title(card, title_el, link_el)
        thumb = self._card_thumb(card)
        quality_el = card.select_one('.mlbq, .badge, .quality')
        quality = quality_el.get_text(strip=True) if quality_el else ''
        media_type = 'tvshow' if self._is_tv_link(link) else 'movie'
        display_title = f"{title} [{quality}]" if quality else title
        return {
            'title': display_title,
            'raw_title': title,
            'url': urljoin(self.base_url, link),
            'thumb': thumb,
            'quality': quality,
            'mediatype': media_type,
        }

    @staticmethod
    def _card_title(card, title_el, link_el):
        if title_el and title_el.get_text(strip=True):
            return title_el.get_text(strip=True)
        img = card.select_one('img')
        if img and img.get('alt'):
            return img.get('alt')
        return link_el.get('title', 'Unknown Title')

    def _card_thumb(self, card):
        img_el = card.select_one('img.lazy, img')
        if not img_el:
            return ''
        thumb = img_el.get('data-src') or img_el.get('src') or ''
        if thumb and not thumb.startswith(('http', 'data:')):
            thumb = urljoin(self.base_url, thumb)
        return thumb

    @staticmethod
    def _is_tv_link(link):
        # NOTE: film URLs are /film/... for both movies and series, so
        # series slugs carrying '-season-<n>-<id>' must also count as tv.
        return ('/tv/' in link or 'tv-series' in link or '/tv-show/' in link
                or re.search(r'-season-\d+-\d+/?$', link) is not None)

    def _parse_next_page(self, soup):
        pagination = soup.select_one('.pagination, .page-item')
        if not pagination:
            return None
        next_el = pagination.select_one(
            'a[rel="next"], a.page-link[aria-label="Next"], '
            '.page-item.active + .page-item a')
        if next_el and next_el.get('href'):
            return urljoin(self.base_url, next_el['href'])
        return None

    # -- search -------------------------------------------------------
    def search(self, query, limit=40):
        """Search via the site's own /searching JSON API (what the site's
        autocomplete uses). Returns (items, next_offset or None)."""
        items = []
        offset = 0
        total = None
        while True:
            params = urlencode({'q': query, 'limit': limit, 'offset': offset})
            res = self.session.get('{}/searching?{}'.format(self.base_url, params),
                                   headers={'Accept': 'application/json'}, timeout=12)
            res.raise_for_status()
            payload = res.json()
            data = payload.get('data') or []
            meta = payload.get('meta') or {}
            if total is None:
                total = meta.get('total_items', len(data))
            items.extend(self._parse_search_entry(e) for e in data)
            offset += len(data)
            if not data or (total is not None and offset >= total):
                break
            if offset >= limit * 2:  # keep search snappy: max ~2 pages
                break
        next_offset = offset if (total is not None and offset < total) else None
        return items, next_offset

    def _parse_search_entry(self, entry):
        title = entry.get('t', 'Unknown Title')
        slug = entry.get('s', '')
        quality = entry.get('q', '')
        year = entry.get('y', '')
        media_type = 'tvshow' if entry.get('d') == 's' else 'movie'
        display = title
        if quality:
            display = '{} [{}]'.format(display, quality)
        if year:
            display = '{} ({})'.format(display, year)
        return {
            'title': display,
            'raw_title': title,
            'url': urljoin(self.base_url, '/film/{}/'.format(slug)),
            'thumb': SEARCH_THUMB.format(slug),
            'quality': quality,
            'year': year,
            'mediatype': media_type,
        }

    # -- genres / countries -------------------------------------------
    def get_dropdown_items(self, category_type):
        """Scrapes Genres or Countries list from the site menu"""
        soup = self._get_soup(self.base_url)
        seen = set()
        unique_items = []
        for link in soup.select(f"a[href*='/{category_type}/']"):
            title = link.get_text(strip=True)
            href = link.get('href', '')
            if not (title and href):
                continue
            if title.lower() in seen:
                continue
            seen.add(title.lower())
            unique_items.append({
                'title': title,
                'url': urljoin(self.base_url, href),
            })
        return unique_items

    # -- film page meta -------------------------------------------------
    @staticmethod
    def _info_row(soup, label):
        """Value cell of a '<p><strong>Label:</strong> ...</p>' info row.

        Scoped to the film info card so footer nav menus (which reuse
        labels like 'Country') can never match first.
        """
        scope = soup.select_one('.mov-info, #mid') or soup
        el = scope.find(string=re.compile(r'^\s*' + re.escape(label) + r':?\s*$'))
        if el is None or el.parent is None or el.parent.parent is None:
            return None
        return el.parent.parent

    @classmethod
    def _row_values(cls, soup, label):
        row = cls._info_row(soup, label)
        if row is None:
            return []
        links = [a.get_text(strip=True) for a in row.select('a') if a.get_text(strip=True)]
        if links:
            return links
        text = row.get_text(separator=' ', strip=True)
        text = re.sub(r'^\s*' + re.escape(label) + r':?\s*', '', text).strip()
        return [p.strip() for p in re.split(r'\s*,\s*', text) if p.strip()] if text else []

    @staticmethod
    def _parse_duration(text):
        m = re.match(r'(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?', text or '')
        if not m or not (m.group(1) or m.group(2)):
            return None
        return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60

    @classmethod
    def parse_film_meta(cls, soup, page_url=''):
        """Full metadata dict from an already-fetched film page soup."""
        og_desc = soup.select_one('meta[property="og:description"]')
        synopsis = og_desc.get('content', '').strip() if og_desc else ''
        if not synopsis:
            el = soup.select_one('.m_i-d-desc, .description, .film-description')
            synopsis = el.get_text(strip=True) if el else ''

        og_img = soup.select_one('meta[property="og:image"]')
        backdrop = og_img.get('content', '').strip() if og_img else ''
        if not backdrop:
            img = soup.select_one('#cover-img, .cover_follow, img')
            backdrop = img.get('data-src') or img.get('src') or '' if img else ''
            if backdrop and not backdrop.startswith(('http', 'data:')):
                backdrop = urljoin(page_url or '/', backdrop)

        genres = cls._row_values(soup, 'Genre')
        actors = cls._row_values(soup, 'Actor')
        directors = cls._row_values(soup, 'Director')
        countries = cls._row_values(soup, 'Country')
        durations = cls._row_values(soup, 'Duration')
        releases = cls._row_values(soup, 'Release')
        imdbs = cls._row_values(soup, 'IMDb')

        year = None
        for value in releases:
            m = re.search(r'(19|20)\d{2}', value)
            if m:
                year = int(m.group(0))
                break

        rating = None
        for value in imdbs:
            try:
                num = float(value)
            except (TypeError, ValueError):
                continue
            # Site shows a 0-100 score (e.g. 81, 100); Kodi wants 0-10.
            rating = round(num / 10.0, 1) if num > 10 else round(num, 1)
            break

        return {
            'synopsis': synopsis,
            'backdrop': backdrop,
            'genres': genres,
            'actors': actors,
            'directors': directors,
            'countries': countries,
            'duration': cls._parse_duration(durations[0] if durations else ''),
            'year': year,
            'rating': rating,
        }

    def get_details_and_seasons(self, page_url):
        """Extracts synopsis, meta information, seasons or direct servers"""
        soup = self._get_soup(page_url)
        mid_el = soup.select_one('#mid[data-mid]')
        mode = mid_el.get('data-mode', '') if mid_el else ''
        mid = mid_el.get('data-mid', '') if mid_el else ''

        meta = self.parse_film_meta(soup, page_url)

        # The site lists episodes inline on the film page (.episode buttons);
        # there are no separate season pages, so seasons stay empty.
        details = {
            'seasons': [],
            'episodes': self._parse_episodes(soup),
            'mode': mode,
            'mid': mid,
        }
        details.update(meta)
        # Back-compat alias used by older views.
        details['backdrop'] = meta['backdrop']
        return details

    @staticmethod
    def _parse_episodes(soup):
        episodes = []
        for el in soup.select('.episode'):
            el_id = el.get('id', '')
            num = el_id.split('-').pop() if '-' in el_id else ''
            title = el.get('title', '') or el.get_text(strip=True)
            if num:
                episodes.append({'num': num, 'title': title or 'Episode {}'.format(num)})
        return episodes

    def get_episodes(self, page_url):
        """Fetches episodes inline from a film/series page."""
        return self._parse_episodes(self._get_soup(page_url))
