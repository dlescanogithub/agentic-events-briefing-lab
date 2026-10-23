# Plain equivalents (use these when make is absent):
#   setup:            python -m pip install -e ".[dev]"
#   lint:             python -m ruff check src tests && python -m ruff format --check src tests
#   typecheck:        python -m mypy
#   test:             python -m pytest
#   eval:             python -m events_briefing eval
#   eval-regression:  python -m events_briefing eval-regression
#   demo:             python -m events_briefing demo --offline
#   secretscan:       python -m events_briefing secretscan
#   briefing:         python -m events_briefing briefing

# Public lab fixture for the approval gate (simulated actor). Not a production credential.
# demo and eval may use it. briefing refuses it. Rotate APPROVAL_STATE_KEY
# before make briefing or any non-demo run. Anyone who can read this file can
# forge a signature if a deployment still uses the fixture.
export APPROVAL_STATE_KEY ?= lab-simulated-not-a-secret

.PHONY: setup lint typecheck test eval eval-regression demo secretscan briefing

setup:
	python -m pip install -e ".[dev]"

lint:
	python -m ruff check src tests
	python -m ruff format --check src tests

typecheck:
	python -m mypy

test:
	python -m pytest

eval:
	python -m events_briefing eval

# This target is expected to exit 1. That is the proof that the gate can go red.
eval-regression:
	python -m events_briefing eval-regression

demo:
	python -m events_briefing demo --offline

briefing:
	python -m events_briefing briefing

secretscan:
	python -m events_briefing secretscan
