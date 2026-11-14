.PHONY: demo schema test blind unit report order logs watch clean

unit:   ## All tests: gates, three axes, portfolio, report. Offline, ~0.3s
	python3 -m unittest discover -s tests -t . -v

demo:   ## Run the bundled example end to end, no arguments, offline
	python3 -m fourwells.cli run --out results/ --seed 0

report: ## Re-render the newest run's report without re-running any model
	python3 -m fourwells.cli report "$$(ls -td results/*/ | head -1)"

order:  ## Re-render the newest run's one-page order sheet for the lab
	python3 -m fourwells.cli order-sheet "$$(ls -td results/*/ | head -1)"

logs:   ## Write the call-log UI to logs/index.html
	python3 -m fourwells.cli logs

watch:  ## Live call-log UI on localhost, re-read on every refresh
	python3 -m fourwells.cli logs --serve

schema: ## Print the frozen design-record contract
	python3 -m fourwells.cli schema

test:   ## Blind run on a target the pipeline has not seen
	python3 -m fourwells.cli run --target examples/unseen_target.fasta --out /tmp/fw-blind --seed 7

blind:  ## The full blind rehearsal: two unseen antigens + the decoy. Offline. docs/blind-rehearsal.md
	python3 -m fourwells.cli run --target Q9NZQ7 --out /tmp/fw-blind/pdl1 --seed 7
	python3 -m fourwells.cli run --target P01375 --out /tmp/fw-blind/tnf  --seed 7
	python3 -m fourwells.cli run --target examples/unseen_target.fasta --out /tmp/fw-blind/decoy --seed 7

clean:
	rm -rf results/ __pycache__ fourwells/__pycache__ fourwells/stages/__pycache__

.PHONY: local web experiment-demo inventory
local: web ## Open the scientific workspace; start an offline demo in the browser

experiment-demo: ## Start a durable offline scientific iteration (no eligible designs)
	python3 -m fourwells.experiments start --mode demo --question 'Exercise the offline scientific workflow' --seed 0

inventory: ## Print local tool/data inventory and source checksums
	python3 -m fourwells.experiments inventory

web:    ## Scientific iterations, evidence, structures, comparison and legacy reports
	python3 -m fourwells.web
