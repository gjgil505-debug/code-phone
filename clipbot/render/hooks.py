"""Hook text shown over the cold open."""
from __future__ import annotations

import random

DEFAULT_HOOKS: dict[str, list[tuple[str, str]]] = {
    "funny": [
        ("funny-1", "I CAN'T STOP LAUGHING AT THIS"),
        ("funny-2", "{name} WAS NOT READY"),
        ("funny-3", "CHAT LOST IT AT THIS"),
        ("funny-4", "THE WAY THIS HAPPENED"),
        ("funny-5", "WORST LUCK IN GTA 6 HISTORY"),
        ("funny-6", "WAIT FOR IT..."),
        ("funny-7", "HOW DID THIS EVEN HAPPEN"),
        ("funny-8", "GTA 6 PHYSICS ARE UNREAL"),
        ("funny-9", "{name} WILL NEVER LIVE THIS DOWN"),
    ],
    "hype": [
        ("hype-1", "THIS IS ACTUALLY INSANE"),
        ("hype-2", "{name} JUST DID THE IMPOSSIBLE"),
        ("hype-3", "CHAT WENT CRAZY FOR THIS"),
        ("hype-4", "BEST GTA 6 MOMENT SO FAR"),
        ("hype-5", "NO WAY THIS WORKED"),
        ("hype-6", "THE CLUTCH OF THE YEAR"),
        ("hype-7", "WATCH TILL THE END"),
        ("hype-8", "{name} IS DIFFERENT"),
        ("hype-9", "THIS SHOULDN'T BE POSSIBLE"),
    ],
    "shock": [
        ("shock-1", "NOBODY EXPECTED THIS"),
        ("shock-2", "{name} DID NOT SEE THIS COMING"),
        ("shock-3", "WAIT... WHAT JUST HAPPENED"),
        ("shock-4", "GTA 6 IS WILD FOR THIS"),
        ("shock-5", "CHAT WAS SPEECHLESS"),
        ("shock-6", "THIS CAME OUT OF NOWHERE"),
        ("shock-7", "ROCKSTAR WHAT IS THIS"),
        ("shock-8", "THE TWIST AT THE END"),
        ("shock-9", "{name} WAS SHOOK"),
    ],
    "general": [
        ("general-1", "CHAT WENT CRAZY FOR THIS ONE"),
        ("general-2", "{name} IN GTA 6 IS SOMETHING ELSE"),
        ("general-3", "YOU HAVE TO SEE THIS"),
        ("general-4", "THIS GTA 6 MOMENT THOUGH"),
        ("general-5", "WAIT FOR THE END"),
        ("general-6", "ONLY IN GTA 6"),
        ("general-7", "THIS IS WHY WE WATCH {name}"),
        ("general-8", "THE MOMENT CHAT EXPLODED"),
        ("general-9", "GTA 6 NEVER DISAPPOINTS"),
    ],
}


class HookPicker:
    def __init__(self, templates: dict[str, list[tuple[str, str]]], recent_ids: list[str],
                 rng: random.Random | None = None):
        self.templates = templates
        self.recent = set(recent_ids)
        self.rng = rng or random.Random()

    def pick(self, trigger_type: str, display_name: str) -> tuple[str, str]:
        pool = self.templates.get(trigger_type) or self.templates["general"]
        fresh = [t for t in pool if t[0] not in self.recent] or pool
        hook_id, text = self.rng.choice(fresh)
        return hook_id, text.replace("{name}", display_name).upper()
