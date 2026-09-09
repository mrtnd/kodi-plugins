# kodi-plugins

Monorepo for Kodi video add-ons. Each top-level `plugin.*` folder is one
installable Kodi add-on, versioned via its own `addon.xml`.

Current plugins:

| Add-on | Kodi ID | Version | Description |
|---|---|---|---|
| FMovies | `plugin.video.fmovies` | `1.2.1` | Movies & TV-Series from fmoviess.org, HLS via InputStream Adaptive |

> Works on Kodi 19 (Matrix), 20 (Nexus), 21 (Omega) — Android TV / Google TV / Fire OS / desktop.

---

## 1. Install (end users)

1. Go to the [**Releases page**](https://github.com/mrtnd/kodi-plugins/releases),
   download the zip you need, e.g. `plugin.video.fmovies-1.2.1.zip`.
2. Copy the zip to your TV (USB, `Send Files to TV` app, or cloud drive).
3. In Kodi: **Settings → System → Add-ons → Unknown sources → ON**.
4. **Add-ons → 📦 (top-left) → Install from zip file** → select the zip.
5. Open **Add-ons → Video add-ons → FMovies**.
6. Enable HLS playback: **Settings → Add-ons → My add-ons →
   VideoPlayer InputStream → InputStream Adaptive → Enable**.

No build, no Python, no adb needed — the Release zip is the artifact.

### Update

Download the newer `plugin.video.<name>-x.y.z.zip` from Releases and
**Install from zip** again. Kodi upgrades in place, settings/history kept.

---

## 2. Repository layout

```text
kodi-plugins/
├── plugin.video.fmovies/      # one Kodi add-on
│   ├── addon.xml              # <-- version source of truth
│   ├── main.py
│   ├── icon.png / fanart.jpg
│   └── resources/
│       ├── settings.xml
│       └── lib/               # scraper.py, resolver.py, kodi_utils.py, ...
├── scripts/
│   └── build_zip.py           # local build, same logic as CI
├── .github/workflows/
│   └── release.yml            # test → build → GitHub Release
├── .gitignore
└── README.md
```

To add a second add-on later, just drop in another `plugin.video.xxx/`
folder with its own `addon.xml`. CI discovers all `plugin.*/` folders
automatically — no workflow changes needed.

---

## 3. Versioning & automated releases (how it works)

**Source of truth:** `plugin.video.fmovies/addon.xml`:

```xml
<addon id="plugin.video.fmovies" version="1.2.1" ...>
```

**Tag format:** `<addon-id>-v<version>`, e.g. `plugin.video.fmovies-v1.2.1`.
**Asset format:** `<addon-id>-<version>.zip`, e.g.
`plugin.video.fmovies-1.2.1.zip` (+ `.sha256` checksum).

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
#    edit plugin.video.fmovies/addon.xml

# 2. sanity check locally
python3 scripts/build_zip.py --out dist
ls -lh dist/

# 3. commit + push
git add plugin.video.fmovies/addon.xml
git commit -m "plugin.video.fmovies: bump to 1.2.2"
git push origin main

# 4. watch Actions → new Release plugin.video.fmovies-v1.2.2 appears
```

---

## 4. Local development

```bash
# build exactly like CI (output in dist/, ignored by git)
python3 scripts/build_zip.py
python3 scripts/build_zip.py --addon plugin.video.fmovies --out dist

# run tests (needs pytest)
pip install pytest requests beautifulsoup4
python3 -m pytest plugin.video.fmovies/tests -v
```

Manual Kodi install from a local build: use the `dist/*.zip` with
**Install from zip** as in section 1.

### FMovies add-on notes

- Root menu: Search (with history), Home Suggestions, Movies, TV-Series,
  Top IMDb, Genres, Countries.
- Settings (`resources/settings.xml`): `base_url` (default
  `https://fmoviess.org`, change if ISP-blocked), `default_quality`,
  `preferred_server`, `use_inputstream`.
- Playback: resolves Server 1/2/3 embeds to direct `.m3u8`/`.mp4`, passes
  `Referer`/`User-Agent`, configures `inputstream.adaptive` for HLS
  (manifest + segment headers mirrored, otherwise playback stalls).

---

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| `Error loading catalog` | Check internet; if `fmoviess.org` blocked, change domain in add-on settings |
| `No stream / resolve failed` | Try another server in settings, or another episode/link |
| Choppy HLS | Enable **InputStream Adaptive** (see §1 step 6) |
| No new Release after push | You didn't bump `addon.xml` version, or tag already exists — bump version and push again |
| CI `addon.xml` validation fails | `id` or `version` attribute missing/malformed |

---

## 6. Disclaimer

These add-ons do not host or store any content. All listings resolve
against publicly available third-party web sources. Use at your own
discretion and in compliance with local law.
