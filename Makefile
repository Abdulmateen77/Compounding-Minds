demo:
	bash api/demo.sh

.PHONY: demo

test:
	python3 -m pytest -q

.PHONY: test
