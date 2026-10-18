EMBER Triple Upgrade — apply over EXISTING wildfire-forensics / EMBER-main folder.

CONTENTS (no replacement data, no checkpoint):
  scripts/expand_fire_dataset.py  -- NASA EONET -> FIRMS candidate fire expansion
  scripts/audit_sequences.py     -- QC/provenance checks, reports provisional cases
  scripts/gnn_forecast.py        -- stronger spatial-proximity benchmark; reviewed-fire allow list
  scripts/gnn_replay.py          -- export stronger baseline with existing GNN weights
  scripts/enrich_population.py   -- WorldPop GeoTIFF + optional Census place names
  src/wildfire/population.py     -- safe relative exposure scoring function
  frontend/forecast.html        -- clearer comparison and population-priority panel
  tests/test_upgrades.py        -- six regression tests for these changes
  docs/TRIPLE_UPGRADE.md        -- exact Windows/LinuxONE commands and limitations

FASTEST IBM SETUP:
  cd ~/EMBER-main
  python3 -m zipfile -e ~/EMBER_Triple_Upgrade_Patch.zip .
  PYTHONPATH=src python3 -m unittest discover -s tests -q

Then open docs/TRIPLE_UPGRADE.md for immediate replay and safe expansion commands.
Existing trained checkpoints and NASA CSVs are NOT modified by unpacking this ZIP.

The new WorldPop population feature is OPTIONAL until its REAL raster download
succeeds. No synthetic population values are bundled or represented as real.
