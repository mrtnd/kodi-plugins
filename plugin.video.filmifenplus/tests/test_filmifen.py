# -*- coding: utf-8 -*-
"""Tests for plugin.video.filmifenplus pure logic.

Fork of plugin.video.filmifen 2026.05.05.01. The streaming path is
exercised on the real device; here the parsers, URLs and the
fork-fidelity invariants are tested offline against pages saved from
the live site (tests/fixtures/).
"""
import os
import sys
import unittest

ADDON = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ADDON)

from resources.lib import filmifen

LIB = os.path.join(ADDON, 'resources', 'lib')
FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding='utf-8') as handle:
        return handle.read()


def _lib_source(name):
    with open(os.path.join(LIB, name), encoding='utf-8') as handle:
        return handle.read()


class TestUrls(unittest.TestCase):
    def test_section_urls_are_the_working_ones(self):
        # Verified live: /hd_filmi_onlain/ 301-redirects to the homepage,
        # /hd-filmi-onlain/ serves the HD listing.
        self.assertEqual(filmifen.URL_MOVIES, 'https://filmifen.com/filmi/')
        self.assertEqual(filmifen.URL_MOVIES_HD,
                         'https://filmifen.com/hd-filmi-onlain/')
        self.assertEqual(filmifen.URL_TV_SHOWS,
                         'https://filmifen.com/seriali/')
        self.assertEqual(filmifen.URL_HOME, 'https://filmifen.com/')

    def test_no_dead_urls_in_the_url_constants(self):
        # The reference menu linked /hd_filmi_onlain/ and /filmi_bg_audio/;
        # both now 301-redirect to the homepage. (The strings only survive
        # in docstrings, which document the removal.)
        found = False
        for attr in dir(filmifen):
            if not attr.startswith('URL_'):
                continue
            value = getattr(filmifen, attr)
            if not isinstance(value, str):
                continue
            found = True
            self.assertNotIn('hd_filmi_onlain', value, attr)
            self.assertNotIn('filmi_bg_audio', value, attr)
        self.assertTrue(found)

    def test_search_page_url_uses_verified_search_start_semantics(self):
        url = filmifen.search_page_url('кари', 2)
        self.assertTrue(url.startswith(
            'https://filmifen.com/index.php?do=search'))
        self.assertIn('search_start=2', url)
        self.assertIn('full_search=0', url)
        self.assertIn('story=%D0%BA%D0%B0%D1%80%D0%B8', url)

    def test_story_recovered_from_search_url(self):
        url = filmifen.search_page_url('slow horses', 3)
        self.assertEqual(filmifen.story_from_url(url), 'slow horses')
        self.assertIsNone(filmifen.story_from_url(
            'https://filmifen.com/filmi/'))
        self.assertIsNone(filmifen.story_from_url(''))


class TestParseCards(unittest.TestCase):
    def test_movies_listing(self):
        cards = filmifen.parse_cards(fixture('listing_movies.html'))
        self.assertEqual(len(cards), 3)
        first = cards[0]
        self.assertEqual(first.title, 'Тензинг')
        self.assertEqual(first.url,
                         'https://filmifen.com/filmi/filmi-drama/14137-tenzing.html')
        self.assertEqual(first.thumb,
                         'https://filmifen.com/uploads/posts/2026-10/tenzing-2026.webp')
        self.assertEqual(first.category, 'Драматични')
        self.assertEqual(first.year, '2026')
        self.assertEqual(first.quality, 'Full HD 1080p (1920×1080)')
        self.assertEqual(first.season, '')
        self.assertEqual(first.episode, '')

    def test_lazy_loaded_poster_uses_data_src(self):
        # Regression: below-the-fold cards have a data: placeholder in
        # src and the real image in data-src; the reference add-on built
        # a garbage thumbnail URL out of the placeholder.
        cards = filmifen.parse_cards(fixture('listing_movies.html'))
        lazy = [card for card in cards
                if card.title == 'Хайде да имаме деца!']
        self.assertEqual(len(lazy), 1)
        self.assertEqual(
            lazy[0].thumb,
            'https://filmifen.com/uploads/posts/2026-10/kids-2026.webp')

    def test_hd_listing_parses(self):
        cards = filmifen.parse_cards(fixture('listing_hd.html'))
        self.assertEqual(len(cards), 2)

    def test_series_listing_parses_without_category_element(self):
        # Regression: series cards have no div.item__poster-category, which
        # made the reference regex skip every card (empty TV Shows folder).
        cards = filmifen.parse_cards(fixture('listing_series.html'))
        self.assertEqual(len(cards), 2)
        first = cards[0]
        self.assertEqual(first.title, 'Кари')
        self.assertEqual(first.category, '')
        self.assertEqual(first.season, 'Се 1')
        self.assertEqual(first.episode, 'Еп 8')
        self.assertTrue(first.thumb.startswith('https://filmifen.com/'))
        self.assertEqual(first.quality, 'Full HD 1080p (1920×1080)')

    def test_search_page_parses_both_movie_and_series_cards(self):
        # Regression: the reference parser dropped every series item in
        # search results for shows like "кари".
        cards = filmifen.parse_cards(fixture('search_page1.html'))
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0].title, 'Тензинг')
        self.assertEqual(cards[1].title, 'Кари')
        self.assertEqual(cards[1].episode, 'Еп 8')

    def test_display_title_adds_series_badge(self):
        cards = filmifen.parse_cards(fixture('listing_series.html'))
        self.assertEqual(cards[0].display_title,
                         'Кари (Се 1 • Еп 8)')
        movies = filmifen.parse_cards(fixture('listing_movies.html'))
        self.assertEqual(movies[0].display_title, 'Тензинг')

    def test_home_listing_parses_like_any_catalog_page(self):
        # The filmifen.com front page is the movies catalog itself
        # (canonical https://filmifen.com/); the root mirrors it.
        cards = filmifen.parse_cards(fixture('home.html'))
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[0].title, 'Неподозиран възход: Възмездие')
        self.assertEqual(cards[0].category, 'Екшън')
        self.assertEqual(cards[1].title, 'Големия план')
        self.assertEqual(cards[2].title, 'Тензинг')

    def test_empty_html_is_handled(self):
        self.assertEqual(filmifen.parse_cards(''), [])
        self.assertEqual(filmifen.parse_cards(None), [])


class TestPagination(unittest.TestCase):
    def test_absolute_next_page(self):
        self.assertEqual(
            filmifen.parse_next_page(fixture('listing_movies.html')),
            'https://filmifen.com/filmi/page/2/')

    def test_relative_next_page_gets_absolutized(self):
        # Regression: series pagination uses relative hrefs and no space
        # after the page span; the reference regex never matched it.
        self.assertEqual(
            filmifen.parse_next_page(fixture('listing_series.html')),
            'https://filmifen.com/seriali/page/2/')

    def test_hd_next_page(self):
        self.assertEqual(
            filmifen.parse_next_page(fixture('listing_hd.html')),
            'https://filmifen.com/hd-filmi-onlain/page/2/')

    def test_home_next_page(self):
        # The homepage pages as /page/N/ (no section prefix).
        self.assertEqual(
            filmifen.parse_next_page(fixture('home.html')),
            'https://filmifen.com/page/2/')

    def test_last_page_has_no_next_entry(self):
        self.assertIsNone(
            filmifen.parse_next_page(fixture('listing_last_page.html')))

    def test_search_list_submit_needs_the_story(self):
        # Search pagination is javascript:list_submit(2); the reference
        # regex turned that into a garbage href ("#" onclick=...).
        html = fixture('search_page1.html')
        self.assertEqual(filmifen.parse_next_page(html, story='кари'),
                         filmifen.search_page_url('кари', 2))
        self.assertIsNone(filmifen.parse_next_page(html))

    def test_search_page_two_ignores_the_previous_page_link(self):
        # On page 2 the list_submit(1) link comes before the <span>2</span>.
        html = fixture('search_page2.html')
        self.assertEqual(filmifen.parse_next_page(html, story='кари'),
                         filmifen.search_page_url('кари', 3))

    def test_no_pagination_block_is_handled(self):
        self.assertIsNone(filmifen.parse_next_page('<html></html>'))


class TestStreams(unittest.TestCase):
    def test_movie_streams(self):
        streams = filmifen.parse_streams(fixture('title_movie.html'))
        self.assertEqual(streams, [
            'https://vidon.to/e/M495IPFR1R6R',
            'https://ok.ru/videoembed/16388013099703',
            'https://voe.sx/e/avhiilis8qbk',
        ])

    def test_serial_streams(self):
        streams = filmifen.parse_streams(fixture('title_serial.html'))
        self.assertEqual(streams, [
            'https://vidon.to/e/678WBPOQ58PZ',
            'https://ok.ru/videoembed/17128259783422',
            'https://bysesukior.com/e/hq0e75pehaem',
            'https://voe.sx/e/cvhqczvkphhe',
        ])

    def test_trailer_and_noise_are_filtered(self):
        for name in ('title_movie.html', 'title_serial.html'):
            for stream in filmifen.parse_streams(fixture(name)):
                self.assertNotIn('youtube', stream)
                self.assertNotIn('schema', stream)
                self.assertNotIn('filmifen', stream)

    def test_empty_page(self):
        self.assertEqual(filmifen.parse_streams(''), [])
        self.assertEqual(filmifen.parse_streams(None), [])


class TestPlot(unittest.TestCase):
    def test_meta_description_parsed(self):
        plot = filmifen.parse_plot(fixture('title_movie.html'))
        self.assertTrue(plot.startswith('Биографичната драма'))

    def test_meta_description_missing(self):
        self.assertEqual(filmifen.parse_plot('<html></html>'), '')

    def test_card_plot_lines(self):
        cards = filmifen.parse_cards(fixture('listing_movies.html'))
        plot = cards[0].plot('Описание')
        self.assertIn('[COLOR CC00FF00]Category: [/COLOR]Драматични', plot)
        self.assertIn('[COLOR CC00FF00]Year: [/COLOR]2026', plot)
        self.assertIn('[COLOR CC00FF00]Quality: [/COLOR]Full HD 1080p', plot)
        self.assertTrue(plot.endswith('Описание'))

    def test_card_plot_without_description(self):
        cards = filmifen.parse_cards(fixture('listing_series.html'))
        plot = cards[0].plot('')
        self.assertNotIn('Category:', plot)
        self.assertIn('Year: ', plot)

    def test_card_defaults_and_badge(self):
        card = filmifen.Card()
        self.assertEqual(card.title, '')
        self.assertEqual(card.display_title, '')
        self.assertEqual(card.plot(''), '')


class TestForkFidelity(unittest.TestCase):
    """Pin the reference behaviour this fork must not diverge from."""

    REQUIRED_PLAY_LINES = (
        'link_sub = resolveurl.resolve(newurl)',
        'link = link_sub[0]',
        'suburl = link_sub[1]',
        "li.setSubtitles([subfile])",
        "opener.addheaders = [('User-Agent', 'UA')]",
        'urllib.request.urlretrieve(suburl, subfile)',
        'xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, li)',
        'xbmc.executebuiltin("Notification(\'Error\',\'Missing video!\')")',
    )

    REQUIRED_PARSER_LINES = (
        'data = (html or \'\').replace(\' \', \'\')',
        'links = re.findall(r":\'http(.+?)\'", data)',
        'links = re.findall(r\':"http(.+?)"\', data)',
    )

    def test_playback_handoff_matches_reference(self):
        source = _lib_source('playback.py')
        for line in self.REQUIRED_PLAY_LINES:
            self.assertIn(line, source, 'play path diverged: ' + line)

    def test_stream_regexes_match_reference(self):
        source = _lib_source('filmifen.py')
        for line in self.REQUIRED_PARSER_LINES:
            self.assertIn(line, source, 'stream parsing diverged: ' + line)
        # the reference filters, in order
        for needle in ("re.search('youtube', link)",
                       "re.search('color', link)",
                       "re.search('schema', link)",
                       "re.search('filmifen', link)"):
            self.assertIn(needle, source, 'stream filter diverged: ' + needle)

    def test_subtitle_file_matches_reference(self):
        source = _lib_source('kodi_utils.py')
        self.assertIn(
            "xbmcvfs.translatePath('special://temp/filmifen.Bulgarian.srt')",
            source)


class TestAgainstFullLivePages(unittest.TestCase):
    """Optional deep check: run against full pages if they are present.

    The committed fixtures are trimmed fragments; when the full captures
    exist next to them (development checkouts only) every card and page
    is verified to parse.
    """

    FULL_PAGES = {
        # name: (next-page URL, expected card count, URL marker)
        'full_filmi.html': ('https://filmifen.com/filmi/page/2/', 24,
                            '/filmi/'),
        'full_hdfilmi.html': ('https://filmifen.com/hd-filmi-onlain/page/2/',
                              24, '/filmi/'),
        'full_seriali.html': ('https://filmifen.com/seriali/page/2/', 24,
                              '/seriali/'),
        'full_home.html': ('https://filmifen.com/page/2/', 24, '/filmi/'),
    }

    def _full(self, name):
        path = os.path.join(FIXTURES, name)
        if not os.path.exists(path):
            self.skipTest('full capture %s not present' % name)
        with open(path, encoding='utf-8') as handle:
            return handle.read()

    def test_full_listing_pages(self):
        for name, (next_url, expected, mark) in self.FULL_PAGES.items():
            html = self._full(name)
            cards = filmifen.parse_cards(html)
            self.assertEqual(len(cards), expected, name)
            self.assertEqual(filmifen.parse_next_page(html), next_url, name)
            for card in cards:
                self.assertTrue(card.title, name)
                self.assertIn(mark, card.url, name)
                self.assertTrue(card.thumb.startswith('https://'), name)


if __name__ == '__main__':
    unittest.main()
