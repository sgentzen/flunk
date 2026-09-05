# flunk
#
# TESTSLOT bounds how many test runs execute at once across concurrent
# sessions. Set TESTSLOT= (empty) to bypass it for a one-off run.

.PHONY: test

PYTHON   ?= python
TESTSLOT ?= python $(HOME)/.claude/bin/testslot.py --

## test: Run the test suite, holding a machine-wide test slot
test:
	$(TESTSLOT) $(PYTHON) -m pytest $(ARGS)
