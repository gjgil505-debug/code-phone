"""Keep videos with blocklisted words from being posted."""
from __future__ import annotations

import re

from clipbot.render.captions import Word


def is_safe(words: list[Word], blocklist: list[str]) -> bool:
    blocked = {b.lower() for b in blocklist}
    for w in words:
        for token in re.findall(r"[\w']+", w.text.lower()):
            if token in blocked:
                return False
    return True
