# -*- coding: utf-8 -*-
"""HTTP session for filmifen.com.

One module-level :class:`requests.Session` (same as the reference add-on),
with a timeout added so a hanging connection cannot freeze Kodi. Errors
are raised (``raise_for_status``) so callers can tell a failed request
from an empty page; the site needs no cookies or login for any of the
sections this fork keeps. TLS is verified normally (the site's
certificate is valid).
"""
from __future__ import annotations

import requests

from resources.lib import filmifen

SESSION = requests.Session()
HEADERS = {'user-agent': filmifen.UA}
TIMEOUT = 30


def get(url):
    """GET a page, return its text."""
    response = SESSION.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def post(url, data):
    """POST a form (used by the search form), return the page text."""
    response = SESSION.post(url, data=data, headers=HEADERS,
                            timeout=TIMEOUT)
    response.raise_for_status()
    return response.text
