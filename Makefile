# casino project Makefile
# Two roles:
#   1) Project-root lifecycle (build, version, install, sdist, clean) - modeled after empyre
#   2) Test orchestration (test-unit, test-integration, test-phase-N, etc.) - pre-existing

PROJECT = casino
PYTHON = python3

.PHONY: all build version install sdist clean push
.PHONY: test test-unit test-integration test-all test-phase-1 test-phase-2 test-phase-3
.PHONY: test-quick test-file help

all:

# Per-subpackage backup-file cleanup. Recurses into src/, which in turn
# recurses into src/casino/ and each game subdir (poker, blackjack,
# yahtzee, tictactoe).
clean:
	-rm *~
	$(MAKE) -C src clean

push:
	git push

# Empyre-style: writes src/casino/_version.py. pyproject.toml reads
# version via setuptools dynamic attr `casino._version.__version__`
# (see [tool.setuptools.dynamic] in pyproject.toml).
version:
	@echo '__version__ = "0.0.1.dev'`date +%Y%m%d%H%M`'"' > src/casino/_version.py
	@echo 'githash = "'`git log -1 --format='%H' 2>/dev/null | cut -c 1-16`'"' >> src/casino/_version.py
	@echo 'datestamp = "'`date +%Y%m%d%H%M`'"' >> src/casino/_version.py

build: version
	$(PYTHON) -m build --outdir dist

sdist: version
	$(PYTHON) -m build --sdist --outdir dist

install:
	$(PYTHON) -m pip install .

# --- test targets (pre-existing) ---------------------------------------------

# Run unit tests only (fast, no external dependencies)
test-unit:
	cd src && python -m pytest casino/tests/ -v -m "not integration" --tb=short

# Run integration tests (requires BED server running)
test-integration:
	cd src && python -m pytest casino/tests/ -v -m "integration" --tb=short

# Run all tests
test-all:
	cd src && python -m pytest casino/tests/ -v --tb=short

# Phase 1: Unit tests (fast, no server needed)
test-phase-1:
	cd src && python -m pytest casino/tests/ -v -m "not integration" \
		--ignore=casino/tests/test_postoffice_*.py \
		--ignore=casino/tests/test_blackjack_flow.py \
		--ignore=casino/tests/test_new_features_integration.py \
		--tb=short

# Phase 2: Postoffice tests (require database)
test-phase-2:
	cd src && python -m pytest casino/tests/test_postoffice_config.py \
		casino/tests/test_postoffice_channel.py \
		casino/tests/test_postoffice_service.py \
		-v --tb=short

# Phase 3: Integration tests (require BED server)
test-phase-3:
	cd src && python -m pytest casino/tests/ -v -m "integration" --tb=short

# Quick test - just unit tests for changed files
test-quick:
	cd src && python -m pytest casino/tests/ -v -m "not integration" -x --tb=short

# Run specific test file
test-file:
	cd src && python -m pytest casino/tests/$(FILE) -v --tb=short

deploy: build

help:
	@echo "Available build targets:"
	@echo "  make build        - Bump version, run python -m build into ./dist"
	@echo "  make version      - Rewrite src/casino/_version.py from git + date"
	@echo "  make sdist        - Build sdist only into ./dist"
	@echo "  make install      - pip install . in current env"
	@echo "  make clean        - Remove ~ backups and recurse into src/"
	@echo "  make push         - git push"
	@echo ""
	@echo "Available test targets:"
	@echo "  make test-unit        - Run unit tests only (fast)"
	@echo "  make test-integration - Run integration tests (requires BED)"
	@echo "  make test-all         - Run all tests"
	@echo "  make test-phase-1     - Run Phase 1: unit tests (no server)"
	@echo "  make test-phase-2     - Run Phase 2: postoffice tests"
	@echo "  make test-phase-3     - Run Phase 3: integration tests"
	@echo "  make test-quick       - Quick unit test run"
	@echo "  make test-file FILE=<test> - Run specific test file"
