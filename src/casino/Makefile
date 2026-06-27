# casino package Makefile
# Two roles:
#   1) Per-subpackage ~ cleanup (clean) - was here originally
#   2) Build/release packaging (build, release, sign, etc.) - moved from src/Makefile
#
# Run from the project root: `make -C src/casino <target>`
# or from src/casino/:        `make <target>`

PROJECT = casino
OUTDIR = dist
VERSION = $(shell date +%Y%m%d%H%M)
PYTHON = python3

.PHONY: build version
.PHONY: clean buildclean rename-sdist sign release all
.PHONY: push tag

all:

# Per-subpackage backup-file cleanup. Recurses into each game's subdir.
# Subdirs without their own Makefile (e.g. slots) are ignored via the
# leading `-` on the $(MAKE) line.
clean:
	-rm *~
	$(MAKE) -C poker clean
	$(MAKE) -C blackjack clean
	$(MAKE) -C yahtzee clean
	-$(MAKE) -C slots clean

# Build-artifact cleanup (renamed from `clean` to avoid collision with the
# per-subpackage dispatcher above).
buildclean:
	-rm -rf build dist *.egg-info

build: version
	cd ../.. && $(PYTHON) -m build --outdir $(OUTDIR)

rename-sdist:
	@cd ../.. && for f in $(OUTDIR)/*.tar.gz; do \
		if [ -f "$$f" ] && echo "$$f" | grep -vq '\-src\.tar\.gz' ; then \
			mv "$$f" "$${f%.tar.gz}-src.tar.gz"; \
			echo "Renamed $$f -> $${f%.tar.gz}-src.tar.gz"; \
		fi \
	done

sign:
	@cd ../.. && for f in $(OUTDIR)/*; do \
		if [ -f "$$f" ] && [ ! -f "$$f.asc" ] && [ "$${f##*.}" != "asc" ]; then \
			gpg --armor --detach-sign "$$f"; \
			echo "Signed $$f"; \
		fi \
	done

release: buildclean build rename-sdist sign

version:
	@echo '__version__ = "0.0.1.dev$(VERSION)"' > _version.py
	@echo 'githash = "'`git log -1 --format='%H' 2>/dev/null | cut -c 1-16`'"' >> _version.py
	@echo 'datestamp = "$(VERSION)"' >> _version.py

push: tag
	git push -u github v$(VERSION)

tag:
	@if git rev-parse v$(VERSION) >/dev/null 2>&1; then \
		echo "Tag v$(VERSION) already exists. Skipping."; \
	else \
		git tag -a v$(VERSION) -m "Release v$(VERSION)"; \
		echo "Tag v$(VERSION) created locally."; \
	fi

# TODO: standardize OUTDIR across packages (../../dist/ vs ../dist/ vs /srv/repo/$(PROJECT)/)
# TODO: standardize version label names across packages (drop __ prefix/suffix on __datestamp__/__version__)
