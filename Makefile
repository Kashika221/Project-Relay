.PHONY: setup demo run eval test lint clean report

PYTHON ?= python

setup:
	$(PYTHON) -m pip install -r requirements.txt

demo:
	$(PYTHON) -m relay.cli demo

run:
	$(PYTHON) -m relay.cli run --inbox $(INBOX)

eval:
	$(PYTHON) -m relay.cli eval --runs $(or $(RUNS),5)

test:
	$(PYTHON) -m pytest tests -v

report:
	$(PYTHON) -m relay.cli report --view $(or $(VIEW),internal)

clean:
	rm -rf out/*.jsonl eval/runs/*.jsonl .pytest_cache
