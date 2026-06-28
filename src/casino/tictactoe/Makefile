all:

clean:
	-rm *~

.PHONY: test test-lib test-service lint

test: test-lib test-service

test-lib:
	cd ../.. && python -m pytest casino/tests/test_tictactoe_lib.py -v --tb=short

test-service:
	cd ../.. && python -m pytest casino/tests/test_tictactoe_service.py -v --tb=short

lint:
	cd ../.. && python -m ruff check casino/tictactoe
