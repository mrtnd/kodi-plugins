# kodi-plugins

Monorepo for Kodi video add-ons. Each top-level `plugin.*` folder is one
installable Kodi add-on, versioned via its own `addon.xml`.

Current plugins:

| Add-on | Kodi ID | Version | Description |
|---|---|---|---|
| FMovies | `plugin.video.fmovies` | `1.2.6` | **DEPRECATED — unmaintained, no further releases.** Kept for reference/history only |
| P2PBG+ | `plugin.video.p2pbgplus` | `0.7.1` | p2pbg.com torrent search + streaming via Elementum, fail-closed VPN country gate |

> Works on Kodi 19 (Matrix), 20 (Nexus), 21 (Omega) — Android TV / Google TV / Fire OS / desktop.

**Maintenance status:** `plugin.video.p2pbgplus` is the only actively
maintained add-on. `plugin.video.fmovies` is **deprecated**: its upstream
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
│   ├── main.py                # router: menu, search, catalog, files, play
│   └── resources/
│       ├── settings.xml       # tracker creds, base URL, VPN country, filters
│       ├── language/.../strings.po
│       └── lib/               # p2pbg.py (tracker client), torrentfile.py
│                              # (bencode), vpngate.py (country gate),
│                              # playback.py (Elementum handoff), ...
│   └── tests/                 # pytest suite (sanitized fixtures only)
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
by MartinStZ (GPL-3.0).** `main.py` is that code, kept as close to the original
as possible, because its Elementum hand-off is the only version confirmed to
play on the target TV. Do not "improve" the play path: a regression test
(`test_p2pbg.py::TestForkFidelity`) pins the hand-off lines, and every earlier
divergence in this repo cost playback in the field.

Added on top of the fork:

- **Fail-closed VPN country gate** (`resources/lib/vpngate.py`) checked before
  every download; wrong country *or* a failed check blocks with a dialog.
- **Diagnostics**: a `Диагностика` entry in the root menu shows Elementum
  presence, the VPN country/state, the profile path, the last plugin call
  (raw query + parsed mode/url), the last listing URL with the results-table
  state and item count, the last URI handed to Elementum and the last error —
  so failures can be read on the TV instead of guessed at.
- **Routing**: plugin queries are parsed with `parse_qsl` (blank values and
  the trailing slash Kodi appends included). The main menu is rendered **only**
  at the add-on root or via the `Меню` entry — never as a side effect of a click
  that could not be resolved, which is what made every selection re-render the
  menu as a nested folder. A listing address embedded in a mangled query
  (mode lost, URL re-encoded, double-encoded) is recovered and shown; if
  nothing can be resolved, the add-on reports the error instead of guessing.
  A failed listing request is reported too, so Kodi never keeps the previous
  directory on screen.
- Setting ids differ from the reference so existing installations keep their
  credentials: `p2pbg_user`, `p2pbg_password`, `prefer_bgaudio`, `show_xxx`,
  `vpn_country`, plus hidden `search_history`, `last_error`, `last_play`.

Behaviour inherited from the reference:

- Root menu: search (with history screen), latest additions, movies-by-year,
  per-category folders (4K/HD/SD, BG movies/series, TV series, animation,
  documentary, sports, optional XXX), diagnostics. The root menu is rendered
  with content type `files`, so it always shows folder icons.
- Opening the add-on reopens the **last used category** instead of the root
  menu (setting `start_at_last`, on by default); every listing has a `Меню`
  entry at the top to get back to it.
- Listing and search URLs mirror the tracker's own search form, because it
  only honours the filters when the whole query is present:
  `/torrents?fakeusernameremembered=&fakepasswordremembered=&search=<q>&category=<ids>&active=1[&bgaudio=1]&hidexxx=1`
  (category ids keep literal `;`, `hidexxx` is `1`/`0`). Verified against the
  confirmed `Филми HD` URL.
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
| P2PBG+ item does nothing | Open **Диагностика** in the add-on menu: VPN state, Elementum presence, profile path, last Elementum URI and last error |
| P2PBG+ `One or more items failed to play` | Open **Диагностика** and check `Last play:`; Elementum must get a bare absolute path (no `file://`) |
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
