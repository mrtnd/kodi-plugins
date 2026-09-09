"""Pure display/text helpers (no Kodi, no network)."""
from __future__ import annotations

import re


def format_duration(total_seconds) -> str:
    """7500 -> '2h 5m' for the plot header."""
    try:
        total = int(total_seconds)
    except (TypeError, ValueError):
        return ''
    hours, rest = divmod(total, 3600)
    minutes = rest // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return ''


def _join(value) -> str:
    if isinstance(value, list):
        return ', '.join(value)
    return str(value)


def build_display_plot(item: dict) -> str:
    """Plot text prefixed with a compact info header.

    Most skins only render title + plot in the browse panel, so the key
    facts (genre, cast, director, ...) are folded into the plot head while
    the structured fields stay set for info dialogs.
    """
    lines = []
    for label, key in (('Genre', 'genre'), ('Cast', 'cast'),
                       ('Director', 'director'), ('Country', 'country')):
        if item.get(key):
            lines.append(f"{label}: {_join(item[key])}")
    facts = []
    duration = format_duration(item.get('duration'))
    if duration:
        facts.append(duration)
    if item.get('year'):
        facts.append(str(item['year']))
    if item.get('rating') is not None:
        try:
            facts.append('Rating: {}/10'.format(float(item['rating'])))
        except (TypeError, ValueError):
            pass
    if item.get('quality'):
        facts.append(str(item['quality']))
    if facts:
        lines.append(' | '.join(facts))
    plot = item.get('plot', '') or ''
    if lines and plot:
        return '\n'.join(lines) + '\n\n' + plot
    if lines:
        return '\n'.join(lines)
    return plot


def clean_film_title(title: str) -> str:
    """Reduce a film page title ('Watch X - Season 1 Full Movie on ...')
    to the plain work title ('X - Season 1') for subtitle search."""
    title = re.sub(r'^(watch\s+)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+on\s+fmovies.*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+full\s+(movie|serie|series|episode).*?$', '', title,
                   flags=re.IGNORECASE)
    title = re.sub(r'\s*[|]\s*Fmovies.*$', '', title)
    title = re.sub(r'\s+online\s*$', '', title, flags=re.IGNORECASE)
    return title.strip()
