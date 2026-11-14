.PHONY: demo schema test unit report logs watch clean

unit:   ## All tests: gates, three axes, portfolio, report. Offline, ~0.3s
	python3 -m unittest discover -s tests -t . -v

demo:   ## Run the bundled example end to end, no arguments, offline
	python3 -m fourwells.cli run --out results/ --seed 0

report: ## Re-render the newest run's report without re-running any model
	python3 -m fourwells.cli report "$$(ls -td results/*/ | head -1)"

logs:   ## Write the call-log UI to logs/index.html
	python3 -m fourwells.cli logs

watch:  ## Live call-log UI on localhost, re-read on every refresh
	python3 -m fourwells.cli logs --serve

schema: ## Print the frozen design-record contract
	python3 -m fourwells.cli schema

test:   ## Blind run on a target the pipeline has not seen
	python3 -m fourwells.cli run --target examples/unseen_target.fasta --out /tmp/fw-blind --seed 7

clean:
	rm -rf results/ __pycache__ fourwells/__pycache__ fourwells/stages/__pycache__

.PHONY: local
local: demo ## Run the demo, then open everything in a browser: report + live call log
	python3 -m fourwells.cli serve
