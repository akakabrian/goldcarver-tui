.PHONY: all venv run test test-only perf playtest clean

# Pure-Python — no engine bootstrap step needed. The vendored
# reference is read as .js text for the level strings.

all: venv

venv: .venv/bin/python
.venv/bin/python:
	python3 -m venv .venv
	.venv/bin/pip install -e .

run: venv
	.venv/bin/python loderunner.py

# Full suite.
test: venv
	.venv/bin/python -m tests.qa

# Scenario subset by name pattern. Usage:  make test-only PAT=dig
test-only: venv
	.venv/bin/python -m tests.qa $(PAT)

perf: venv
	.venv/bin/python -m tests.perf

playtest: venv
	.venv/bin/python -m tests.playtest

clean:
	rm -rf __pycache__ */__pycache__ tests/out/*.svg
