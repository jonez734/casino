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
.PHONY: test test-unit test-integration test-all test-phase-1 test-phase-3
.PHONY: test-quick test-file help
.PHONY: commit-version
.PHONY: ensure-repo ensure-build-dir rename-sdist sign release

all:

# Per-subpackage backup-file cleanup plus wheel-artifact cleanup.
# Recurses into src/, which in turn recurses into src/casino/ and
# each game subdir (poker, blackjack, yahtzee, tictactoe).
# Wipes build/, dist/, *.egg-info/, and the standard cache dirs
# before each `python -m build` invocation (the root `build`
# target declares `clean` as a prerequisite). This sidesteps the
# setuptools SOURCES.txt absolute-path failure mode when a stale
# `src/casino.egg-info/SOURCES.txt` from a prior run carries
# forward absolute paths into a fresh build. Matches the pattern
# shipped in `zoid6/src/Makefile:118-124`.
clean:
	-rm -rf build dist
	-rm -rf *.egg-info src/*.egg-info src/casino/*.egg-info
	-find . -type d -name __pycache__ -exec rm -rf {} +
	-find . -type d -name .pytest_cache -exec rm -rf {} +
	-find . -type d -name .ruff_cache -exec rm -rf {} +
	-find . -type d -name .mypy_cache -exec rm -rf {} +
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

# Make sure $(1)/build/ exists with mode 1775 (sticky + rwxrwxr-x) before
# invoking `python -m build`. Mode 1775 is intentional:
#   - sticky (t): only the owner of a file inside may delete/rename it,
#     so concurrent builds under a shared group can't stomp each other.
#   - setgid (s) is intentionally NOT set: setuptools' shutil.copystat
#     mirrors build/'s mode onto the freshly-created dist-info dir, and
#     a setgid'd dist-info EPERMs the subsequent bdist_wheel step in
#     SELinux-enforcing + NoNewPrivs containers (we lack CAP_FSETID).
#   - group write (g+w): any user in the build group can rebuild
#     without needing to chown.
# The chmod is expressed as `chmod g-s,+t` (drop the setgid bit the
# parent dir inherited onto the freshly-mkdir'd build/, then add the
# sticky bit). The numeric form `chmod 1775` is functionally equivalent
# but fails on BTRFS+SELinux setups where the parent directory's
# setgid bit blocks the owner from clearing it via the numeric mode
# (`chmod: Operation not permitted` on a dir the caller owns). The
# symbolic form works because the kernel only restricts numeric-mode
# changes that would remove the inherited setgid bit; `g-s` is
# permitted regardless of where the bit came from.
#
# If $(1)/build/ exists but is owned by a different user (e.g. left over
# from a prior build run as a different uid), rename it out of the way
# first. The parent dir is group-writable in this tree so the rename is
# permitted even when we don't own the build/ contents. Without this,
# the subsequent chmod fails with EPERM and the build aborts.
# Mirrors bed/Makefile:189-194 (see also zoid6/TODO.md "PREPARE_BUILD
# standardization (cross-project)").
PREPARE_BUILD = \
	if [ -d $(1)/build ] && [ ! -O $(1)/build ]; then \
		mv $(1)/build $(1)/build.stale.$$ 2>/dev/null || true; \
	fi; \
	mkdir -p $(1)/build && chmod g-s,+t $(1)/build

build: clean version ensure-build-dir
	$(call PREPARE_BUILD,$(CURDIR))
	$(PYTHON) -m build --outdir $(OUTDIR)

sdist: version ensure-build-dir
	$(call PREPARE_BUILD,$(CURDIR))
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

# Run unit tests only (fast, no external dependencies).
# CASINO_TEST_DB is set so the DB-gated unit tests in
# ``test_player_service.py`` and ``test_door_casino_player.py``
# (which mock the DAL but still call ``database.connect(...)`` to
# build their args Namespace) run instead of being skipped. The
# env var falls back to ``zoid6`` when no override is given.
CASINO_TEST_DB ?= zoid6
test-unit:
	cd src && CASINO_TEST_DB=$(CASINO_TEST_DB) python -m pytest casino/tests/ -v -m "not integration" --tb=short

# Run integration tests (requires BED server running)
test-integration:
	cd src && python -m pytest casino/tests/ -v -m "integration" --tb=short

# Run all tests
test-all:
	cd src && python -m pytest casino/tests/ -v --tb=short

# Phase 1: Unit tests (fast, no server needed)
test-phase-1:
	cd src && python -m pytest casino/tests/ -v -m "not integration" \
		--ignore=casino/tests/test_blackjack_flow.py \
		--ignore=casino/tests/test_new_features_integration.py \
		--tb=short

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
	# TODO(verify-install): after this `pip install` of $$WHEEL,
	# compare the wheel's METADATA Version against `pip show casino`
	# to catch the silent-no-op case where pip reports "already
	# installed" without actually installing. See
	# zoidoffice/src/Makefile's VERIFY_INSTALL variable for the
	# reference implementation. The wheel path here is set in the
	# recipe ($$WHEEL), not as a Makefile-evaluated variable, so
	# the verify step must use $$WHEEL not $(WHEEL). Editable branch
	# (DEPLOY_EDITABLE=1, line 191) installs from source so no check.
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
	@echo "  make test-phase-3     - Run Phase 3: integration tests"
	@echo "  make test-quick       - Quick unit test run"
	@echo "  make test-file FILE=<test> - Run specific test file"

commit-version:
	git add src/$(PROJECT)/_version.py
	git diff --cached --quiet || git commit -m "Bump $(PROJECT) version to $(VERSION)"
