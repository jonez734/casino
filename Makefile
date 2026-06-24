.PHONY: test test-unit test-integration test-all test-phase-1 test-phase-2 test-phase-3

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

help:
	@echo "Available test targets:"
	@echo "  make test-unit        - Run unit tests only (fast)"
	@echo "  make test-integration - Run integration tests (requires BED)"
	@echo "  make test-all         - Run all tests"
	@echo "  make test-phase-1     - Run Phase 1: unit tests (no server)"
	@echo "  make test-phase-2     - Run Phase 2: postoffice tests"
	@echo "  make test-phase-3     - Run Phase 3: integration tests"
	@echo "  make test-quick       - Quick unit test run"
	@echo "  make test-file FILE=<test> - Run specific test file"
