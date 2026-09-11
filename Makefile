# monday-axi — build/test/lint/install. The distributable is a single-file zipapp
# (dist/monday-axi.pyz): stdlib-only, runs on any Python 3.10+, no install.
.PHONY: build install test lint clean

DIST := dist
BIN  := $(HOME)/.local/bin/monday-axi

build:
	@rm -rf build/stage $(DIST)
	@mkdir -p build/stage $(DIST)
	@cp -r monday_axi build/stage/
	python3 -m zipapp build/stage -m "monday_axi.cli:main" -o $(DIST)/monday-axi.pyz -p "/usr/bin/env python3"
	@rm -rf build/stage
	@echo "built $(DIST)/monday-axi.pyz"

install: build
	@mkdir -p $(dir $(BIN))
	@cp $(DIST)/monday-axi.pyz $(BIN)
	@chmod +x $(BIN)
	@echo "installed $(BIN)"

test:
	python3 -m unittest discover -s tests

lint:
	ruff check .

clean:
	rm -rf $(DIST) build
