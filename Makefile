# flunk

.PHONY: test

PYTHON   ?= python

## test: Run the test suite
test:
	$(PYTHON) -m pytest $(ARGS)
