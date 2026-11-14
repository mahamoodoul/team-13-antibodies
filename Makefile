.PHONY: demo schema test clean

demo:   ## Run the bundled example end to end, no arguments, offline
	python3 -m fourwells.cli run --out results/ --seed 0

schema: ## Print the frozen design-record contract
	python3 -m fourwells.cli schema

test:   ## Blind run on a target the pipeline has not seen
	python3 -m fourwells.cli run --target examples/unseen_target.fasta --out /tmp/fw-blind --seed 7

clean:
	rm -rf results/ __pycache__ fourwells/__pycache__ fourwells/stages/__pycache__
