# casino project Makefile
# Two roles:
#   1) Project-root lifecycle (build, version, install, sdist, clean) - modeled after empyre
#   2) Test orchestration (test-unit, test-integration, test-phase-N, etc.) - pre-existing

export PROJECT = casino
export STAGE = /srv/www/vhosts/zoidtechnologies.com/html/$(PROJECT)/
export SKINDIR = $(STAGE)skin/
export HOST = merlin

export SCSSLOADPATH = --load-path /home/opencode/data/work/zoid6/shared/skin/scss/ \
	--load-path /home/opencode/data/work/bbsengine6/skin/scss/ \
	--load-path /home/opencode/data/work/casino/www/skin/scss/
export SCSS = sass $(SCSSLOADPATH) --sourcemap=none --stop-on-error --trace --style expanded

export RSYNC = rsync --chmod=Dg=rwxs,Fgu=rw,Fo=r --verbose \
	--archive --times --no-group --update --backup --recursive \
	--human-readable --checksum --rsh=ssh \
	--mkpath --exclude='*~'

PYTHON = python3
VERSION = $(shell date +%Y%m%d%H%M)
OUTDIR = /srv/repo/$(PROJECT)/

.PHONY: all build version install sdist clean push
.PHONY: deploy-www deploy-tui
.PHONY: test test-unit test-integration test-all test-phase-1 test-phase-2 test-phase-3
.PHONY: test-quick test-file help
.PHONY: commit-version
.PHONY: ensure-repo ensure-build-dir rename-sdist sign release

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

.PHONY: ensure-repo
ensure-repo:
	@stat -c '%G' /srv/repo 2>/dev/null | grep -qx repo || sudo chgrp repo /srv/repo
	@stat -c '%a' /srv/repo 2>/dev/null | grep -q '^2775$$' || sudo chmod 2775 /srv/repo

.PHONY: ensure-build-dir
ensure-build-dir: ensure-repo
	@mkdir -p /srv/repo/$(PROJECT)/
	@stat -c '%G' /srv/repo/$(PROJECT)/ 2>/dev/null | grep -qx repo || sudo chgrp repo /srv/repo/$(PROJECT)/
	@stat -c '%a' /srv/repo/$(PROJECT)/ 2>/dev/null | grep -q '^2775$$' || sudo chmod 2775 /srv/repo/$(PROJECT)/

build: version ensure-build-dir
	$(PYTHON) -m build --outdir $(OUTDIR)

sdist: version ensure-build-dir
	$(PYTHON) -m build --sdist --outdir $(OUTDIR)

rename-sdist:
	@for f in $(OUTDIR)/*.tar.gz; do \
		if [ -f "$$f" ] && echo "$$f" | grep -vq '\-src\.tar\.gz' ; then \
			mv "$$f" "$${f%.tar.gz}-src.tar.gz"; \
			echo "Renamed $$f -> $${f%.tar.gz}-src.tar.gz"; \
		fi \
	done

sign:
	@for f in $(OUTDIR)/*; do \
		if [ -f "$$f" ] && [ ! -f "$$f.asc" ] && [ "$${f##*.}" != "asc" ]; then \
			gpg --armor --detach-sign "$$f"; \
			echo "Signed $$f"; \
		fi \
	done

release: clean version build rename-sdist sign

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

deploy-www:
	$(MAKE) -C www prod
	$(RSYNC) $(STAGE) $(HOST):$(STAGE)

# Build a fresh wheel then install it into the active venv. Mirrors
# bbsengine6's deploy-tui so the install artifact path is uniform
# across projects (always via /srv/repo/<project>/ wheels).
# DEPLOY_EDITABLE=1: install editable from the source tree instead
# (set by `deploytool --editable`). Live edits to src/ are visible
# to the active venv without a rebuild.
DEPLOY_EDITABLE ?=
deploy-tui: build
ifeq ($(DEPLOY_EDITABLE),1)
	$(MAKE) version
	$(PYTHON) -m pip install --no-cache-dir -e .
	-rm -rf src/casino.egg-info
else
	@WHEEL=$$(ls -t $(OUTDIR)/$(PROJECT)-*.whl 2>/dev/null | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "no wheel found in $(OUTDIR); run \`make build\` first" >&2; \
		exit 1; \
	fi; \
	echo "installing $$WHEEL"; \
	$(PYTHON) -m pip install --no-cache-dir "$$WHEEL"
endif

help:
	@echo "Available build targets:"
	@echo "  make build        - Bump version, run python -m build into $(OUTDIR)"
	@echo "  make version      - Rewrite src/casino/_version.py from git + date"
	@echo "  make sdist        - Build sdist only into $(OUTDIR)"
	@echo "  make install      - pip install . in current env"
	@echo "  make deploy-tui                       - install casino into the active venv (shared zoid6 venv)"
	@echo "  make deploy-tui DEPLOY_EDITABLE=1     - install editable from src/ (live edits; set by deploytool --editable)"
	@echo "  make deploy-www   - build www and rsync to $(HOST)"
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

commit-version:
	git add src/$(PROJECT)/_version.py
	git diff --cached --quiet || git commit -m "Bump $(PROJECT) version to $(VERSION)"
