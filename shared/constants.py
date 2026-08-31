# Exchange list classification per ibindex ticker (Nasdaq Stockholm unless noted).
# Updated: 2026-07-03. Change rarely — update manually if a company moves list.
NASDAQ_LIST: dict[str, str] = {
    "INVE B": "Large Cap",
    "INDU C": "Large Cap",
    "LUND B": "Large Cap",
    "LATO B": "Large Cap",
    "BURE": "Mid Cap",
    "KINV B": "Mid Cap",
    "CRED A": "Mid Cap",
    "ORES": "Mid Cap",
    "SPLTN": "Mid Cap",
    "SVOL B": "Mid Cap",
    "FLAT B": "Mid Cap",
    "LINC": "Mid Cap",
    "TRAC B": "Mid Cap",
    "FLERIE": "Mid Cap",
    "AJA B": "Mid Cap",
    "NAXS": "Small Cap",
    "VNV": "First North",
    "VEFAB": "First North",
    "FIRST B": "First North",
    "COLLAX": "First North",
    "SON": "Euronext Lisbon",
}

# Fallback for tickers ibindex adds before this map is updated — without
# it new companies would silently vanish from the app.
UNKNOWN_LIST = "Okänd lista"

LISTS = ["Large Cap", "Mid Cap", "Small Cap", "First North", "Euronext Lisbon", UNKNOWN_LIST]

# Investment companies quoted in more than one share class. Economic rights
# are identical across classes (same dividend, same claim on NAV) — only
# voting power differs — so for a passive owner the cheaper class is simply
# more NAV per krona. Keyed by ibindex ticker; the ibindex ticker itself is
# always part of its own list. Update manually when a class is added or
# delisted — verified against Yahoo Finance 2026-08-31.
SHARE_CLASSES: dict[str, list[str]] = {
    "INVE B": ["INVE A", "INVE B"],
    "INDU C": ["INDU A", "INDU C"],
    "KINV B": ["KINV A", "KINV B"],
    "SVOL B": ["SVOL A", "SVOL B"],
}

# A shares are often barely traded (SVOL A: 5 trading days out of 22, 41
# shares/day), which makes their last price stale and the apparent spread
# meaningless. Below this average daily volume a class is shown but flagged,
# and never auto-selected as "cheapest".
MIN_SHARE_CLASS_VOLUME = 1_000.0
