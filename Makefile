# Python 3.12+, standard-library core.
.PHONY: test fixture infer demo graph notebooks

# Run fast, dependency-free unit and integration tests.
test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

# Generate clearly marked fictional demo observations.
fixture:
	python3 scripts/make_synthetic.py

# Run the actual model on synthetic fixture, never claiming real-fire accuracy.
infer: fixture
	PYTHONPATH=src python3 -m wildfire.cli evaluate --detections data/synthetic/toy_firms.csv --weather data/synthetic/toy_weather.json --label data/synthetic/toy_reference.json --output artifacts/synthetic_demo.json

# Launch the local browser dashboard and inference API.
demo: fixture
	PYTHONPATH=src python3 scripts/serve_stdlib.py --dataset data/synthetic/toy_firms.csv --weather data/synthetic/toy_weather.json --powerlines data/synthetic/toy_powerlines.geojson --lightning data/synthetic/toy_lightning.csv --demo

# Export typed heterogeneous graph CSVs for optional graph databases.
graph: fixture
	PYTHONPATH=src python3 scripts/export_heterograph.py --detections data/synthetic/toy_firms.csv --weather data/synthetic/toy_weather.json --powerlines data/synthetic/toy_powerlines.geojson --lightning data/synthetic/toy_lightning.csv

# Rebuild the seven notebooks (requires nbformat on the generating machine).
notebooks:
	python3 scripts/create_notebooks.py
