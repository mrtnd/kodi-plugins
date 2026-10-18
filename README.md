# kodi-plugins

Monorepo for Kodi video add-ons. Each top-level `plugin.*` folder is one
installable Kodi add-on, versioned via its own `addon.xml`.

Current plugins:

| Add-on | Kodi ID | Version | Description |
|---|---|---|---|
| FMovies | `plugin.video.fmovies` | `1.2.6` | **DEPRECATED — unmaintained, no further releases.** Kept for reference/history only |
| P2PBG+ | `plugin.video.p2pbgplus` | `0.9.0` | p2pbg.com torrent search + streaming via Elementum, VPN country gate, seeders-sorted HD-only listings |
| FilmiFen+ | `plugin.video.filmifenplus` | `0.3.0` | Fork of `plugin.video.filmifen` 2026.05.05.01: filmifen.com homepage mirrored at the root plus Movies, Movies HD and TV Shows with fixed listings, search (with history) and pagination |

> Works on Kodi 19 (Matrix), 20 (Nexus), 21 (Omega) — Android TV / Google TV / Fire OS / desktop.

**Maintenance status:** `plugin.video.p2pbgplus` and
`plugin.video.filmifenplus` are the actively maintained add-ons.
`plugin.video.fmovies` is **deprecated**: its upstream
site is gone/broken, it receives no fixes, no version bumps and no releases,
and changes to it are out of scope. Do not work on it, and ignore it in
reviews, test runs and release prep.

---

## 1. Install (end users)

1. Go to the [**Releases page**](https://github.com/mrtnd/kodi-plugins/releases),
    download the zip you need, e.g. `plugin.video.p2pbgplus-0.6.1.zip`
    (the FMovies zips are kept for existing installs only).
2. Copy the zip to your TV (USB, `Send Files to TV` app, or cloud drive).
3. In Kodi: **Settings → System → Add-ons → Unknown sources → ON**.
4. **Add-ons → 📦 (top-left) → Install from zip file** → select the zip.
5. Open **Add-ons → Video add-ons** → your add-on.

### FMovies only (deprecated add-on)

6. Enable HLS playback: **Settings → Add-ons → My add-ons →
   VideoPlayer InputStream → InputStream Adaptive → Enable**.

### P2PBG+ only

6. Install the **Elementum** add-on (Android `arm64` build for Google TV /
   Fire OS) and open it once so its torrent engine starts.
7. You need a **p2pbg.com account** — enter the username and password in
   the add-on's Configure dialog (stored only in local Kodi settings,
   never leaves your device).
8. Connect your **VPN** before playing. The add-on checks the exit country
   on every playback and blocks with a dialog when the check fails.
9. Keep a couple GB free for the stream buffer; temp files are cleaned up
   after watching. Long-term seeding is governed by Elementum's own
   settings (mind your tracker ratio).

### FilmiFen+ only

6. Install **`script.module.findstreamurl`** first (it is the resolver
   module the original add-on used; it is served by the same repos as
   `plugin.video.filmifen`, e.g. `martinstz.com/_repo`). The add-on has no
   settings of its own — browse **Search / Movies / Movies HD / TV Shows**
   and play a stream; subtitles are fetched automatically when the source
   provides them.

No build, no Python, no adb needed — the Release zip is the artifact.

### Update

Download the newer `plugin.video.<name>-x.y.z.zip` from Releases and
**Install from zip** again. Kodi upgrades in place, settings/history kept.

---

## 2. Repository layout

```text
kodi-plugins/
├── plugin.video.fmovies/      # DEPRECATED, unmaintained (HLS streaming add-on)
│   ├── addon.xml              # <-- version source of truth
│   ├── main.py
│   ├── icon.png / fanart.jpg
│   └── resources/
│       ├── settings.xml
│       ├── language/.../strings.po
│       └── lib/               # scraper.py, resolver.py, kodi_utils.py, ...
├── plugin.video.p2pbgplus/    # torrent search add-on (needs Elementum)
│   ├── addon.xml              # <-- version source of truth
│   ├── main.py                # thin router (query parsing + dispatch)
│   └── resources/
│       ├── settings.xml       # tracker creds, base URL, VPN country, filters
│       ├── language/.../strings.po
│       └── lib/               # p2pbg.py (URLs + HTML parsing, pure),
│                              # tracker.py (session/client), views.py
│                              # (menu/listings/search), playback.py
│                              # (Elementum hand-off), kodi_utils.py
│                              # (Kodi adapters), vpngate.py (country gate)
│   └── tests/                 # pytest suite (sanitized fixtures only)
├── plugin.video.filmifenplus/ # filmifen.com streaming add-on (FilmiFen+)
│   ├── addon.xml              # <-- version source of truth
│   ├── main.py                # thin router (query parsing + dispatch)
│   └── resources/
│       ├── settings.xml       # InfoWall view default + about box
│       ├── language/resource.language.en_gb/strings.po
│       └── lib/               # filmifen.py (URLs + HTML parsing, pure),
│                              # http.py (session), views.py
│                              # (menu/listings/search/streams),
│                              # playback.py (resolveurl hand-off),
│                              # kodi_utils.py (Kodi adapters)
│   └── tests/                 # pytest suite (fixtures trimmed from live pages)
├── scripts/
│   └── build_zip.py           # local build, same logic as CI
├── .github/workflows/
│   └── release.yml            # test → build → GitHub Release
├── .gitignore
└── README.md
```

To add another add-on later, just drop in another `plugin.video.xxx/`
folder with its own `addon.xml`. CI discovers all `plugin.*/` folders
automatically — no workflow changes needed.

---

## 3. Versioning & automated releases (how it works)

**Source of truth:** the add-on's own `addon.xml` (e.g.
`plugin.video.p2pbgplus/addon.xml`):

```xml
<addon id="plugin.video.p2pbgplus" version="0.6.1" ...>
```

**Tag format:** `<addon-id>-v<version>`, e.g. `plugin.video.p2pbgplus-v0.6.1`.
**Asset format:** `<addon-id>-<version>.zip`, e.g.
`plugin.video.p2pbgplus-0.6.1.zip` (+ `.sha256` checksum).

Pipeline (`.github/workflows/release.yml`, runs on every `push` to
`main`/`master`, on PRs, and manually via **Actions → Run workflow**):

1. **`test`** — validates every `plugin.*/addon.xml` (id + version present),
   installs `pytest requests beautifulsoup4`, runs each add-on's
   `tests/` suite.
2. **`build`** — runs `scripts/build_zip.py --out dist`, producing one
   versioned zip per add-on (excluding `venv/`, `__pycache__/`, `*.pyc`,
   `.pytest_cache/`, `tests/`, `.git/`, etc.). Uploads to Actions artifacts.
3. **`release`** (only on push to `main`/`master`) — for each add-on, if tag
   `<id>-v<version>` does **not** exist yet, creates the tag + GitHub
   Release (auto release notes) and uploads the zip + `.sha256`.

Consequences:

- **To ship a release:** bump `version="…"` in `addon.xml`, commit, push to
  `main`. CI does the rest. No manual zipping, no committing zips.
- **Commits without a version bump:** CI still tests + builds (artifacts
  visible under the Actions run), but **no new Release** is created —
  so ordinary fixes/docs don't spam the Releases page.
- Built zips are **never committed** (`*.zip` is in `.gitignore`). The
  Releases page is the distribution channel.

### Release checklist

```bash
# 1. bump version, e.g. 1.2.1 -> 1.2.2
#    edit plugin.video.p2pbgplus/addon.xml

# 2. sanity check locally
python3 scripts/build_zip.py --out dist
ls -lh dist/

# 3. commit + push
git add plugin.video.p2pbgplus/addon.xml
git commit -m "plugin.video.p2pbgplus: bump to 0.6.2"
git push origin main

# 4. watch Actions → new Release plugin.video.p2pbgplus-v0.6.2 appears
```

---

## 4. Local development

```bash
# build (output in dist/, ignored by git)
python3 scripts/build_zip.py --addon plugin.video.p2pbgplus --out dist

# run tests (needs pytest)
pip install pytest requests beautifulsoup4
python3 -m pytest plugin.video.p2pbgplus/tests -v
python3 -m pytest plugin.video.filmifenplus/tests -v
```

`plugin.video.fmovies` is deprecated: no builds, no test runs, no releases.

Manual Kodi install from a local build: use the `dist/*.zip` with
**Install from zip** as in section 1.

### FMovies add-on notes (DEPRECATED)

> **Deprecated / unmaintained.** Upstream playback no longer works, the add-on
> gets no further releases, and it is excluded from active development. Kept in
> the repo so existing installations keep working and for historical reference.
> Known-good state at the time of deprecation:

- Root menu: Search (with history), Home Suggestions, Movies, TV-Series,
  Top IMDb, Genres, Countries.
- Settings (`resources/settings.xml`): `base_url` (default
  `https://fmoviess.org`, change if ISP-blocked), `default_quality`,
  `preferred_server`, `use_inputstream`.
- Playback: resolves Server 1/2/3 embeds to direct `.m3u8`/`.mp4`, passes
  `Referer`/`User-Agent`, configures `inputstream.adaptive` for HLS
  (manifest + segment headers mirrored, otherwise playback stalls).

### P2PBG+ add-on notes

**This add-on is a fork of
[`plugin.video.p2pbg` 2026.09.24.01](http://martinstz.com/_repo/plugin.video.p2pbg/)
by MartinStZ (GPL-3.0).** The Elementum hand-off and the tracker session
set-up (now in `resources/lib/playback.py` and `resources/lib/tracker.py`)
are kept byte-for-byte identical to the original, because that hand-off is
the only version confirmed to play on the target TV. Do not "improve" the
play path: a regression test (`test_p2pbg.py::TestForkFidelity`) pins the
hand-off lines, and every earlier divergence in this repo cost playback in
the field. The rest of the add-on was refactored into small modules:

| Module | Role |
|---|---|
| `main.py` | Thin router: parse the query, dispatch to a view |
| `resources/lib/p2pbg.py` | Pure tracker logic: URL shapes, HTML parsing, filtering, ordering |
| `resources/lib/tracker.py` | requests session, login, listing/enrichment, torrent fetch |
| `resources/lib/views.py` | Menu, listings, search and diagnostics screens |
| `resources/lib/playback.py` | Fail-closed VPN gate + Elementum hand-off |
| `resources/lib/kodi_utils.py` | Settings, logging, dialogs, history, list items |

Added on top of the fork:

- **Fail-closed VPN country gate** (`resources/lib/vpngate.py`) checked before
  every download; wrong country *or* a failed check blocks with a dialog.
- **Most-active-first listings**: every category and every search result is
  sorted by seeders (then leechers), and each row carries a `S:x L:y` badge,
  so it is obvious at a glance what is hot right now. The tracker form has no
  server-side sort, so ordering is applied to the parsed rows.
- **HD only**: 4K/UHD (2160p/3840p) releases are dropped from listings and
  search, and the dedicated Movies 4K category is gone.
- **English-only interface**: every menu label, plot field, dialog and
  notification is English. Bulgarian survives only inside the parser regexes
  that read the tracker's own Bulgarian HTML.
- **Diagnostics**: a `Diagnostics` entry in the root menu shows Elementum
  presence, the VPN country/state, the profile path, the last plugin call
  (raw query + parsed mode/url), the last listing URL with the results-table
  state and item count, the last URI handed to Elementum and the last error —
  so failures can be read on the TV instead of guessed at.
- **Routing**: plugin queries are parsed with `parse_qsl` (blank values and
  the trailing slash Kodi appends included). The main menu is rendered **only**
  at the add-on root — never as a side effect of a click that could not be
  resolved, which is what made every selection re-render the menu as a
  nested folder. A listing address embedded in a mangled query
  (mode lost, URL re-encoded, double-encoded) is recovered and shown; if
  nothing can be resolved, the add-on reports the error instead of guessing.
  A failed listing request is reported too, so Kodi never keeps the previous
  directory on screen.
- Setting ids differ from the reference so existing installations keep their
  credentials: `p2pbg_user`, `p2pbg_password`, `prefer_bgaudio`, `show_xxx`,
  `vpn_country`, plus hidden `search_history`, `last_error`, `last_play`.

Behaviour inherited from the reference:

- Root menu (rebuilt): Search with history (over all categories,
  `category=0`, spaces plus-encoded), Movies HD (`category=68`), TV shows
  (`category=14`), TV boxsets (`category=15`), all movies/shows/boxsets via
  the bare `?category=...` URL, diagnostics. Listings have no menu entry; the
  remote Back button is enough.
- Menu items use compact requests (`m`/`c`/`q` keys) instead of embedding the
  whole listing URL, so a click cannot lose its address inside Kodi; any
  failure shows the recorded request on screen.
- A category click can never render a previous search: when a request cannot
  be resolved, the add-on reports the error instead of substituting content
  (truncated labels resolve by unique prefix). The root menu is rendered
  with content type `files`, so it always shows folder icons.
- Opening the add-on always shows the root menu (an earlier auto-reopen of
  the last listing stranded users on it with no way back to browse).
- Listing and search URLs mirror the tracker's own search form, because it
  only honours the filters when the whole query is present:
  `/torrents?fakeusernameremembered=&fakepasswordremembered=&search=<q>&category=<ids>&active=1[&bgaudio=1]&hidexxx=1`
  (category ids keep literal `;`, `hidexxx` is `1`/`0`). Verified against the
  confirmed `Movies HD` URL.
- Every listing row is enriched from its own details page: release, video
  stream, year, genre, IMDb id, BG-subs/BG-audio badges, poster, size,
  seeders/leechers, synopsis, plus "next page". Cells are read at the real
  column offsets and a malformed row is skipped instead of aborting the
  listing.
- Playback: tracker session (UA + `referer` + `host`), CSRF token from the
  homepage, login with `_token`/`returnto`/`uid`/`pwd`, details page per
  torrent for the `download.php` link, staged as
  `elementum_temp.torrent` in the profile dir, handed to Elementum as
  `plugin://plugin.video.elementum/play?uri=<percent-encoded absolute path>`.
- Credentials never leave the device; nothing session-related is committed
  (development snapshots live under git-ignored `p2pbg.com/`).

### FilmiFen+ add-on notes

**This add-on is a fork of
[`plugin.video.filmifen` 2026.05.05.01](http://martinstz.com/_repo/plugin.video.filmifen/)
by MartinStZ (GPL-3.0).** The whole play path — the stream regexes in
`resources/lib/filmifen.py` and the resolveurl/subtitle/`setResolvedUrl`
hand-off in `resources/lib/playback.py` — is kept byte-for-byte identical
to the reference, because that is the only version confirmed to play with
`script.module.findstreamurl`. Do not "improve" it: a regression test
(`tests/test_filmifen.py::TestForkFidelity`) pins the exact lines.

#### What was broken (analysis of the reference against the live site)

| Symptom in the reference add-on | Root cause | Fix in FilmiFen+ |
|---|---|---|
| TV Shows (Сериали) opens an **empty folder** | `INDEXPAGES` parsed cards with one regex that required a `div.item__poster-category` element. Series cards on `/seriali/` do not have that element, so **every** card was skipped | Cards are parsed with BeautifulSoup attribute-wise; series cards parse without the category div |
| Series are missing from search results | Same regex requirement: only movie cards in mixed results matched (e.g. `кари` parsed 9 of 24 rows) | Same fix; a mixed-results regression test covers it |
| "Most selections don't work" | The menu linked `/hd_filmi_onlain/` and `/filmi_bg_audio/` (the site now 301-redirects both to the homepage) and built the genre entries by scraping `ul.menu__block` with regexes that no longer match the markup | Menu reduced to the three working sections plus Search; dead URLs and scraping are gone |
| TV Shows has no "next page" | The pagination regex required a literal space after `<span>N</span>`, and series pagination uses relative hrefs without it | Pagination is read from the DOM; relative hrefs are absolutized |
| Search "next page" never works | Search paginates with `javascript:list_submit(N)`, which the old regex turned into a garbage URL (`#" onclick=...`) | `list_submit(N)` maps to `index.php?do=search&…&search_start=N` — semantics verified live (`search_start=2` → results 25-48); the query is carried across pages |
| Below-the-fold posters broken | Lazy cards carry a 1×1 `data:` placeholder in `src` and the real image in `data-src`; the old regex used the placeholder | `data-src`/`srcset` fallbacks, never a `data:` URI |
| Clicking a dead entry re-rendered the menu as a nested folder | The reference rendered the root menu whenever a request could not be resolved | The menu is rendered only at the add-on root; failures are reported on screen |

#### Behaviour of the fork

- Root menu: **Search**, **Movies** (`/filmi/`), **Movies HD**
  (`/hd-filmi-onlain/`), **TV Shows** (`/seriali/`) — nothing else.
- The root then mirrors the filmifen.com homepage below the four entries:
  the same cards and the same "Next page" (`/page/2/`, `/page/3/`…). The
  site front page currently serves the movies catalog itself, so no TV
  Shows appear there; a homepage fetch failure leaves the menu usable.
- The **InfoWall** view is applied by default on every screen (Kodi view
  ids are skin-specific; 54 is Estuary's InfoWall, configurable in the
  add-on settings, or switchable off).
- Search opens the **search screen** first: **New search**, the last 20
  remembered queries (most recent first), **Clear history**. Replaying a
  query runs it at once; the history lives in the add-on profile
  (`search_history.json`) on the device and is never uploaded anywhere.
- New searches post the site's own form (`do=search`/`subaction=search`/
  `story=<query>`); results include movies and series, and paging works.
- Series rows show the season/episode badge (`Кари (Се 1 • Еп 8)`) because
  the site titles every episode with the same name.
- Stream selection preserves the reference labels (`Stream N: <title>`) and
  the reference filters (trailer/ads/schema/self-links excluded); resolver
  playback and subtitle download are unchanged.
- Listings are never served from Kodi's directory cache
  (`cacheToDisc=False`).
- The interface (menu labels, dialogs) is English; site values (titles,
  categories) stay as the site returns them.

#### Layout

| Module | Role |
|---|---|
| `main.py` | Thin router: parse the query, dispatch to a view |
| `resources/lib/filmifen.py` | Pure site logic: URLs, card/pagination parsing, streams |
| `resources/lib/http.py` | requests session for filmifen.com (timeout added) |
| `resources/lib/views.py` | Menu, listings, search, stream selection |
| `resources/lib/playback.py` | resolveurl + subtitles + `setResolvedUrl` (reference logic) |
| `resources/lib/kodi_utils.py` | Dialogs, keyboard, list items, directory plumbing, search history |

Run its tests with:

```bash
pip install pytest requests beautifulsoup4
python3 -m pytest plugin.video.filmifenplus/tests -v
```

The committed fixtures are fragments trimmed from live captures. For a
deep check, drop full captures into `tests/fixtures/` as
`full_filmi.html`, `full_hdfilmi.html`, `full_seriali.html` and
`full_home.html` — `TestAgainstFullLivePages` then verifies every card
(24 per page) and parses the pagination of each.

---

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| `Error loading catalog` (FMovies, deprecated) | Upstream no longer works; the add-on is unmaintained |
| `No stream / resolve failed` (FMovies, deprecated) | Upstream no longer works; the add-on is unmaintained |
| Choppy HLS (FMovies, deprecated) | Enable **InputStream Adaptive** (see §1 step 6) |
| P2PBG+ `Tracker login failed` | Re-enter username/password in Configure; check tracker reachability/VPN |
| P2PBG+ playback blocked, wrong country | Connect VPN to the configured country and retry (gate is fail-closed) |
| P2PBG+ `Install the Elementum add-on first` | Install Elementum (Android build) and open it once |
| P2PBG+ empty results | Lower minimum seeders, or try another category/title |
| P2PBG+ item does nothing | Open **Diagnostics** in the add-on menu: VPN state, Elementum presence, profile path, last Elementum URI and last error |
| P2PBG+ `One or more items failed to play` | Open **Diagnostics** and check `Last play:`; Elementum must get a bare absolute path (no `file://`) |
| FilmiFen+ `Resolver missing` | Install `script.module.findstreamurl` (same repos as the original add-on) |
| FilmiFen+ `No streams found` | The title page listed no players for this title; try another title or stream |
| FilmiFen+ empty listing / `No items found` | The site layout likely changed — re-capture a page and compare with `resources/lib/filmifen.py` |
| FilmiFen+ view/art looks wrong on a non-Estuary skin | The InfoWall id is skin-specific — change or disable "Force the InfoWall view" in the add-on settings |
| FilmiFen+ root has no homepage content | The homepage fetch failed (site down); a notification is shown — the four menu entries still work |
| FilmiFen+ remove remembered search queries | Open Search → **Clear history** (bottom of the screen) |
| FilmiFen+ `No results for "…"` | The site search found nothing; check the spelling (the site's Bulgarian titles differ from English ones) |
| No new Release after push | You didn't bump `addon.xml` version, or tag already exists — bump version and push again |
| CI `addon.xml` validation fails | `id` or `version` attribute missing/malformed |
| CI `settings.xml` validation fails | Unknown setting `type`, or numeric label missing from `strings.po` |

---

## 6. Disclaimer

These add-ons do not host or store any content. Listings resolve against
publicly available third-party web sources, and torrent playback runs
through the third-party Elementum engine against torrents you choose.
Tracker credentials live only in your local Kodi settings and are never
committed, logged, or transmitted anywhere except the tracker's own login.
Use at your own discretion and in compliance with local law. Torrenting
uploads while downloading — a VPN is strongly recommended.
