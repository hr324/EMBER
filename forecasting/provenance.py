"""Write forecasting/outputs/provenance.json from the saved source manifests."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from . import config


def sha(path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main() -> None:
    fpa = json.loads((config.RAW_DIR / 'fpa_fod' / 'manifest.json').read_text())
    wx = json.loads((config.PROCESSED_DIR / 'weather_manifest.json').read_text())
    P = config.PROCESSED_DIR
    prov = dict(
        generated_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        study_region=dict(bbox_deg=config.BBOX, grid='square cells in EPSG:3310 NAD83/California Albers',
                          cell_size_m=config.CELL_SIZE_M, cells=80),
        prediction=dict(target='>=1 FPA-FOD discovery in cell during [issue, issue+6]', issue_weekday='Monday',
                        first_issue=str(config.FIRST_ISSUE), last_issue=str(config.LAST_ISSUE),
                        splits=config.SPLITS, weather_lag_days=config.WEATHER_LAG_DAYS,
                        fire_history_cutoff='discoveries strictly before issue date'),
        sources=dict(
            fire_occurrence=dict(name='USFS Fire Program Analysis Fire-Occurrence Database (FPA-FOD), 7th edition',
                                 service=fpa['source'], archive_doi=fpa['doi'], query_where=fpa['where'],
                                 out_fields=fpa['out_fields'], page_size=fpa['page_size'],
                                 downloaded_utc=fpa['downloaded_utc'], raw_records=fpa['total_records'],
                                 raw_pages=fpa['pages'],
                                 date_convention=('discovery_date is an ArcGIS Date (epoch ms). Its UTC calendar date '
                                                  'matched discovery_doy for every record, so it is used as a local '
                                                  'calendar date with no timezone conversion.'),
                                 excluded_from_predictors=['fire_size', 'fire_size_class', 'nwcg_general_cause',
                                                           'cont_date']),
            weather=dict(name='Open-Meteo Historical Weather API (reanalysis, ERA5 / ERA5-Land family)',
                         endpoint=wx['source'], docs=wx['docs'], daily_vars=wx['daily_vars'], units=wx['units'],
                         timezone=wx['timezone'], start=wx['start'], end=wx['end'], sampling=wx['sampling'],
                         points=wx['points'], cached_files=wx['files'], assembled_utc=wx['assembled_utc'],
                         limitation='Reanalysis is not the forecast available on the issue date; 7-day lag applied.')),
        audits=dict(fires=json.loads((P / 'fires_audit.json').read_text()),
                    labels=json.loads((P / 'labels_audit.json').read_text())),
        derived_file_sha256={f: sha(P / f) for f in ('fires.csv', 'labels.csv', 'weather_daily.csv', 'features.csv')},
        missing_data_policy=('Fire records with missing date or invalid coordinates are dropped (none found). '
                             'Weather features require complete trailing windows; rows lacking them would stop '
                             'training rather than be imputed (none occurred). No values are simulated.'),
        cost='All sources are free public endpoints; no paid API, plan or compute used.')
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (config.OUTPUT_DIR / 'provenance.json').write_text(json.dumps(prov, indent=2))
    print('wrote', config.OUTPUT_DIR / 'provenance.json')


if __name__ == '__main__':
    main()
