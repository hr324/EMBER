"""Single source of truth for study region, grid, horizons and chronological splits."""
from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = Path(__file__).resolve().parent
RAW_DIR = ROOT / 'data' / 'raw' / 'forecasting'        # gitignored: full source extracts
CACHE_DIR = ROOT / 'data' / 'cache' / 'forecasting'    # gitignored: API response cache
PROCESSED_DIR = ROOT / 'data' / 'processed' / 'forecasting'
SAMPLES_DIR = PKG / 'samples'                          # small verbatim extracts used by tests
OUTPUT_DIR = PKG / 'outputs'

# Study region (WGS84 / NAD83 degrees). Includes Butte County.
BBOX = dict(lat_min=39.0, lat_max=41.0, lon_min=-122.8, lon_max=-120.8)

# Square cells in EPSG:3310 (NAD83 / California Albers), metres.
CELL_SIZE_M = 25_000

# Forecast design.
HORIZON_DAYS = 7          # label window: [issue_date, issue_date + 6]
WEATHER_LAG_DAYS = 7      # latest usable weather date = issue_date - 7
ISSUE_WEEKDAY = 0         # Monday-issued forecasts (date.weekday() == 0)

# Years with fire records pulled. 2014 is history only (lookback for early-2015 features).
FIRE_YEARS = (2014, 2024)
FIRST_ISSUE = date(2015, 1, 5)    # first Monday of 2015
LAST_ISSUE = date(2024, 12, 23)   # last Monday whose 7-day window ends inside 2024

# Chronological splits by issue-date year.
SPLITS = {
    'train': (2015, 2020),
    'validation': (2021, 2022),
    'holdout': (2023, 2024),
}

FPA_FOD_LAYER = ('https://apps.fs.usda.gov/arcx/rest/services/EDW/'
                 'EDW_FireOccurrenceCurrentEdition_01/MapServer/0')
FPA_FOD_DOI = 'https://doi.org/10.2737/RDS-2013-0009.7'
OPEN_METEO_ARCHIVE = 'https://archive-api.open-meteo.com/v1/archive'


def split_of(issue: date) -> str:
    """Return the chronological split an issue date belongs to."""
    for name, (lo, hi) in SPLITS.items():
        if lo <= issue.year <= hi:
            return name
    raise ValueError(f'issue date {issue} outside all splits')
