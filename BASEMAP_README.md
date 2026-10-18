# EMBER OpenStreetMap underlay (frontend-only upgrade)

This patch adds a real **OpenStreetMap geographic basemap** behind the same inferred-origin points, satellite observations, optional perimeter, power lines and lightning overlays. The underlying wildfire inference is **unchanged**.

It uses Leaflet 1.9.4 (loaded from unpkg.com) and live OpenStreetMap tiles from `tile.openstreetmap.org`, so an internet connection is required to see the basemap. If either source is unavailable, the previous dependency-free coordinate grid remains functional. A map toggle allows switching between them when online.

**Windows PowerShell upgrade** (from your existing `wildfire-forensics` folder):

```powershell
# Stop the running demo with Ctrl+C first.
Expand-Archive -Path "$HOME\Downloads\EMBER_Basemap_Patch.zip" -DestinationPath . -Force
py scripts\serve_stdlib.py --dataset data/synthetic/toy_firms.csv --weather data/synthetic/toy_weather.json --powerlines data/synthetic/toy_powerlines.geojson --lightning data/synthetic/toy_lightning.csv --demo
```

Open http://127.0.0.1:8000 and hard-refresh with Ctrl+Shift+R. A working connection should load the map automatically and show an `OFFLINE GRID` button; clicking it changes back to the old view. If there is no connection, the coordinate grid persists and the button reads `GRID · OFFLINE`.

Map attribution remains visible. This is an investigation visualisation only: **present-day OpenStreetMap features are not evidence of historical infrastructure, wildfire perimeter or cause.** Avoid bulk tile downloading, offline tile scrapers, or heavy load on the OpenStreetMap community tile service; see https://operations.osmfoundation.org/policies/tiles/.

To revert to the prior UI, restore the three frontend files from your original MVP ZIP.
