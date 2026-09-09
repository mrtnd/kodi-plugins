import re
from urllib.parse import urljoin, quote
import requests
from bs4 import BeautifulSoup
from resources.lib.kodi_utils import get_setting

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def decode_html(response):
    """Decode response bytes as UTF-8.

    requests falls back to ISO-8859-1 for text/html without an explicit
    charset, which mangles names like 'Chloé' into 'ChloÃ©'.
    """
    content = getattr(response, 'content', None)
    if isinstance(content, (bytes, bytearray)):
        try:
            content_type = response.headers.get('content-type', '') or ''
        except Exception:
            content_type = ''
        if not isinstance(content_type, str):
            content_type = ''
        if 'charset' not in content_type.lower():
            try:
                return bytes(content).decode('utf-8')
            except UnicodeDecodeError:
                pass
    text = getattr(response, 'text', '')
    return text if isinstance(text, str) else ''


class FMoviesScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.base_url = get_setting('base_url').rstrip('/') or 'https://fmoviess.org'

    def _get_soup(self, url):
        response = self.session.get(url, timeout=12)
        response.raise_for_status()
        return BeautifulSoup(decode_html(response), 'html.parser')

    def get_catalog(self, path_or_url):
        url = path_or_url if path_or_url.startswith('http') else urljoin(self.base_url, path_or_url)
        soup = self._get_soup(url)
        items = []

        # Correct selectors for fmoviess.org cards
        cards = soup.select('.card.bg-transparent.border-0.h-100, div.col .card')
        if not cards:
            cards = soup.select('div.col, .card')

        for card in cards:
            title_el = card.select_one('.card-title, h2, h3, .film-name')
            link_el = card.select_one('a[href*="/film/"], a[href*="/tv/"], a.rounded')
            
            if not link_el:
                # Try finding any anchor inside card
                link_el = card.select_one('a')
            
            if not link_el or not link_el.get('href'):
                continue

            link = link_el.get('href')
            full_link = urljoin(self.base_url, link)

            # Title fallback to img alt or title attribute
            title = ''
            if title_el:
                title = title_el.get_text(strip=True)
            if not title:
                img_check = card.select_one('img')
                if img_check:
                    title = img_check.get('alt', '')
            if not title:
                title = link_el.get('title', 'Unknown Title')

            # Extract thumbnail image
            img_el = card.select_one('img.lazy, img')
            thumb = ''
            if img_el:
                thumb = img_el.get('data-src') or img_el.get('src') or ''
                if thumb and not thumb.startswith('http') and not thumb.startswith('data:'):
                    thumb = urljoin(self.base_url, thumb)

            # Quality badge (HD, CAM, TS, mlbq)
            quality_el = card.select_one('.mlbq, .badge, .quality')
            quality = quality_el.get_text(strip=True) if quality_el else ''

            # Media type (movie vs tvshow). NOTE: film URLs are /film/...
            # for both movies and series, so series slugs carrying
            # '-season-<n>-<id>' must also count as tv shows.
            is_tv = ('/tv/' in link or 'tv-series' in link or '/tv-show/' in link
                     or re.search(r'-season-\d+-\d+/?$', link) is not None)
            media_type = 'tvshow' if is_tv else 'movie'

            display_title = f"{title} [{quality}]" if quality else title

            items.append({
                'title': display_title,
                'raw_title': title,
                'url': full_link,
                'thumb': thumb,
                'quality': quality,
                'mediatype': media_type
            })

        # Pagination
        next_page_url = None
        pagination = soup.select_one('.pagination, .page-item')
        if pagination:
            next_el = pagination.select_one('a[rel="next"], a.page-link[aria-label="Next"], .page-item.active + .page-item a')
            if next_el and next_el.get('href'):
                next_page_url = urljoin(self.base_url, next_el['href'])

        return items, next_page_url

    def search(self, query, limit=40):
        """Search via the site's own /searching JSON API (what the site's
        autocomplete uses). Returns (items, next_offset or None)."""
        from urllib.parse import urlencode
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
            for entry in data:
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
                items.append({
                    'title': display,
                    'raw_title': title,
                    'url': urljoin(self.base_url, '/film/{}/'.format(slug)),
                    'thumb': 'https://img.cdno.my.id/thumb/w_200/h_300/{}.jpg'.format(slug),
                    'quality': quality,
                    'year': year,
                    'mediatype': media_type,
                })
            offset += len(data)
            if not data or (total is not None and offset >= total):
                break
            if offset >= limit * 2:  # keep search snappy: max ~2 pages
                break
        next_offset = offset if (total is not None and offset < total) else None
        return items, next_offset

    def get_dropdown_items(self, category_type):
        """Scrapes Genres or Countries list from the site menu"""
        soup = self._get_soup(self.base_url)
        items = []
        
        selector = f"a[href*='/{category_type}/']"
        for link in soup.select(selector):
            title = link.get_text(strip=True)
            href = link.get('href', '')
            if title and href:
                items.append({
                    'title': title,
                    'url': urljoin(self.base_url, href)
                })
        
        seen = set()
        unique_items = []
        for item in items:
            if item['title'].lower() not in seen:
                seen.add(item['title'].lower())
                unique_items.append(item)
                
        return unique_items

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
        seasons = []

        details = {
            'seasons': seasons,
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
