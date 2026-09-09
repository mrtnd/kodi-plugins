"""Playback handoff: resolve stream, configure InputStream Adaptive."""
from __future__ import annotations

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib.kodi_utils import (
    HANDLE, get_setting, get_subs_dir, notify, show_error,
)
from resources.lib.resolver import ResolveError, StreamResolver

MANIFEST_MARKERS = ('.m3u8', 'master.txt', '.mpd', '/hls', '/pl/',
                    'streamsvr', 'urlset')


def order_servers(servers, preferred: str | None = None):
    preferred = (preferred or '').lower()
    return sorted(
        servers,
        key=lambda s: (0 if preferred and preferred in s['name'].lower() else 1),
    )


def is_manifest_url(base_url: str) -> bool:
    if '.mp4' in base_url.split('?')[0]:
        return False
    return any(marker in base_url for marker in MANIFEST_MARKERS)


def configure_listitem(play_item, stream_url: str) -> None:
    base_url, _, header_suffix = stream_url.partition('|')
    play_item.setPath(stream_url)
    if get_setting('use_inputstream') != 'true' or not is_manifest_url(base_url):
        return
    play_item.setProperty('inputstream', 'inputstream.adaptive')
    play_item.setProperty('inputstream.adaptive.manifest_type', 'hls')
    if header_suffix:
        # The '|Referer=..&User-Agent=..' suffix only covers the manifest
        # request made by Kodi core; inputstream.adaptive fetches media
        # segments itself, so headers must also be mirrored here or
        # playback stalls silently.
        play_item.setProperty('inputstream.adaptive.manifest_headers', header_suffix)
        play_item.setProperty('inputstream.adaptive.stream_headers', header_suffix)
    try:
        play_item.setMimeType('application/vnd.apple.mpegurl')
        play_item.setContentLookup(False)
    except AttributeError:
        pass


def play_stream(page_url, title, eps=None):
    resolver = StreamResolver()
    try:
        servers = resolver.get_servers(page_url)
        if not servers:
            notify("No stream servers found.")
            return

        # Preferred server first, then the rest as fallback (like a browser
        # trying each player until one yields a playable stream).
        ordered = order_servers(servers, get_setting('preferred_server'))

        try:
            stream_url = resolver.resolve_stream_any(ordered, eps,
                                                     sub_dir=get_subs_dir())
        except ResolveError as e:
            notify(f"Resolve failed: {e}")
            return
        if not stream_url:
            notify("Unable to resolve stream link.")
            return

        base_url = stream_url.partition('|')[0]
        play_item = xbmcgui.ListItem(path=base_url)
        configure_listitem(play_item, stream_url)

        subtitles = list(getattr(stream_url, 'subtitles', None) or ())
        if subtitles:
            try:
                play_item.setSubtitles(subtitles)
            except AttributeError:
                pass
        try:
            xbmc.log('plugin.video.fmovies: playing {} (subs={})'.format(
                base_url[:120], len(subtitles)), xbmc.LOGINFO)
        except Exception:
            pass

        xbmcplugin.setResolvedUrl(HANDLE, True, play_item)

    except Exception as e:
        show_error(f"Playback error: {e}")
