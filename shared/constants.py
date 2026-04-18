# Nasdaq Stockholm list classification per ibindex ticker.
# Updated: 2026-04-03. Change rarely — update manually if a company moves list.
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
    "SON": "First North",
}

LISTS = ["Large Cap", "Mid Cap", "Small Cap", "First North"]
