.PHONY: doctor test lint fetch-public qgis-smoke qgis-projects manifest clean

doctor:
	python -m mgrb.cli doctor

test:
	pytest -q

lint:
	ruff check mgrb scripts tests

fetch-public:
	python scripts/fetch_public.py

qgis-smoke:
	QT_QPA_PLATFORM=offscreen python3 scripts/qgis_smoke.py

qgis-projects:
	QT_QPA_PLATFORM=offscreen python3 scripts/build_qgis_projects.py

manifest:
	python -m mgrb.cli manifest metadata/provenance.json data/derived

clean:
	rm -rf data/derived/* qgis-projects/generated/* outputs/*
