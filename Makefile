.PHONY: doctor test lint fetch-public prepare-owner-review qgis-smoke qgis-projects acceptance manifest clean

doctor:
	python -m mgrb.cli doctor

test:
	pytest -q

lint:
	ruff check mgrb scripts tests

fetch-public:
	python scripts/fetch_public.py

prepare-owner-review:
	python scripts/prepare_owner_review.py

qgis-smoke:
	QT_QPA_PLATFORM=offscreen python3 scripts/qgis_smoke.py

qgis-projects:
	QT_QPA_PLATFORM=offscreen python3 scripts/build_qgis_projects.py

acceptance:
	python -m pytest -q
	python -m compileall -q mgrb scripts tests
	ruff check mgrb scripts tests
	QT_QPA_PLATFORM=offscreen python3 scripts/qgis_smoke.py
	python scripts/prepare_owner_review.py
	QT_QPA_PLATFORM=offscreen python3 scripts/build_qgis_projects.py

manifest:
	python -m mgrb.cli manifest metadata/provenance.json data/derived

clean:
	rm -rf data/derived/* qgis-projects/generated/* outputs/*
