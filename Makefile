.PHONY: submission verify viz demo schema test unit clean

# results/ holds the designs we actually submit, and it is committed. Only
# `make submission` may write it, and it scores the WHOLE pool. `make demo` is
# a fast illustration over a round-robin subset and writes elsewhere -- running
# it must never be able to replace the submission with a 24-design sample.

submission: ## THE ARTEFACT. Score the full pool and write results/ (what we send)
	python3 -m fourwells.cli run --candidates 1000 --out results/ --seed 0
	@python3 -I scripts/verify_submission.py
	@python3 -I viz/build_results.py

verify: ## Re-derive every submitted construct from its design record. Offline.
	python3 -I scripts/verify_submission.py

viz:    ## Rebuild viz/results.html from results/. `--check` fails if it is stale.
	python3 -I viz/build_results.py

demo:   ## Fast illustration over a subset, offline, no arguments. Writes results/demo/
	python3 -m fourwells.cli run --out results/demo/ --seed 0

unit:   ## Ranking-engine tests (gates, three axes, portfolio). Offline, ~0.1s
	python3 -m unittest discover -s tests -t . -v

schema: ## Print the frozen design-record contract
	python3 -m fourwells.cli schema

test:   ## Blind run on a target the pipeline has not seen
	python3 -m fourwells.cli run --target examples/unseen_target.fasta --out /tmp/fw-blind --seed 7

clean:  ## Caches only. Never results/ -- that is committed submission output.
	rm -rf results/demo __pycache__ fourwells/__pycache__ fourwells/stages/__pycache__
