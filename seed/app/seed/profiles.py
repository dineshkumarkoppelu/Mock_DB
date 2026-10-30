"""Stand-in rep profiles (the original profiles module was not available).

Each profile: per-domain (won, closed) counts inside the lookback window, optional extra
older history, and a number of open deals. Sized so the generator's hard-coded minimums
(>= 8 + 15 WON, >= 15 LOST, >= 55 open deals, >= 6 stall candidates) are comfortably met.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.domains import DOMAINS


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    email: str
    region: str
    window: dict[str, tuple[int, int]]  # domain -> (won, closed)
    open_deals: int
    extra_older: dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def window_domains(self) -> tuple[str, ...]:
        return tuple(d for d in DOMAINS if d in self.window)


def older_counts(won: int, closed: int) -> tuple[int, int]:
    """Older-history (won, closed) for a cell, ~70% of the window volume."""
    closed_old = max(2, round(closed * 0.7))
    won_old = min(closed_old, max(1, round(won * 0.7)))
    return won_old, closed_old


def _p(n: int, name: str, region: str, window: dict[str, tuple[int, int]], open_deals: int,
       extra_older: dict[str, tuple[int, int]] | None = None) -> Profile:
    email = name.lower().replace(" ", ".") + "@example.com"
    return Profile(f"SP-{n:03d}", name, email, region, window, open_deals, extra_older or {})


PROFILES: tuple[Profile, ...] = (
    _p(1, "Aarav Mehta", "North", {"AI": (7, 12), "Cloud Migration": (6, 10), "DevOps": (5, 9)}, 9),
    _p(2, "Priya Nair", "South", {"Cybersecurity": (8, 12), "AI": (5, 9), "IoT": (4, 8)}, 9),
    _p(3, "Rohan Kapoor", "West", {"IoT": (5, 11), "DevOps": (6, 10), "Cloud Migration": (4, 8)}, 10,
       {"AI": (4, 6)}),
    _p(4, "Sneha Iyer", "South", {"Cloud Migration": (7, 11), "Cybersecurity": (5, 9), "AI": (4, 8)}, 9),
    _p(5, "Vikram Rao", "East", {"DevOps": (8, 12), "IoT": (5, 9), "Cybersecurity": (4, 8)}, 8),
    _p(6, "Ananya Das", "International", {"AI": (6, 10), "Cybersecurity": (6, 10), "DevOps": (4, 8)}, 8),
    _p(7, "Karan Malhotra", "North", {"Cloud Migration": (4, 10), "IoT": (3, 9), "AI": (3, 8)}, 10,
       {"Cybersecurity": (5, 7)}),
    _p(8, "Meera Joshi", "West", {"Cybersecurity": (5, 9), "DevOps": (5, 9), "IoT": (4, 8)}, 9),
)
