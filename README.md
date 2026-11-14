# AntibodyLab AI — Team 13, Oslo

Improving **trastuzumab** (anti-HER2). Designs are measured by Adaptyv on three axes:
binding (SPR), epitope preservation, thermostability. Beat all three = S-tier.
Two S-tier designs beat ten that each improve one thing.

Full brief: **[docs/brief.md](docs/brief.md)** — submission rules, data, models, scoring.
The plan: **[docs/plan.md](docs/plan.md)** — strategy, who owns what, the day, the pitch.

## Run locally

Python 3.10+ is enough for the offline demo; no packages or API keys are needed.
From this project directory:

```bash
make local
```

Open http://127.0.0.1:4173/experiments and select **New offline experiment**.
The workspace preserves iteration questions, parent runs, seeds, validation,
three separate objectives, structures and decisions. Compare iterations at
`/compare`. Press Ctrl-C to stop the web server; detached scientific workers
continue independently. Demo sequences are clearly marked and never enter a
submission export. Missing evidence stays unknown.

`make experiment-demo` starts an offline iteration from the terminal;
`make inventory` lists local tools/data with checksums; `make unit` runs tests.
`make demo` and the dashboard's **Legacy runs** retain the earlier heuristic
prototype for comparison. Those scores are not calibrated probabilities or
experimental outcomes. `make watch` opens the legacy call log on localhost.
Project Claude sessions are saved locally in `chat-history/claude-project/`.
That directory is gitignored; raw histories can contain credentials.

## Scientific workflow

Read the [project specification](antibodylab_ai_project_README.md),
[scientific method](docs/scientific-method.md),
[evidence schema](docs/data-dictionary.md), and
[model adapter instructions](docs/model-usage.md).

```bash
python3 -m fourwells.experiments start --mode import \
  --input candidates.jsonl --question 'Inspect the first saved pilot'
python3 -m fourwells.experiments list
```

An import without an official validation adapter remains visible but cannot
be shortlisted. On the supplied GPU VM, configure documented commands in a
local copy of `config/model-profile.example.json`, then run:

```bash
python3 -m fourwells.experiments start --mode live \
  --profile config/my-verified-vm-profile.json --seed 13 --candidates 8 \
  --question 'Does the documented HER2 design setting produce eligible candidates?'
```

Every attempt gets a new directory under `artifacts/antibodylab/`; SQLite tracks
job state. The iteration export includes the final FASTA (at most 20 official
passes), CSV evidence, reference/input snapshots, model logs and checksums.
Runtime settings are explicit CLI arguments; the model profile controls external
stage commands. The HTTP API can start offline demos only.

Real RFD4-Proteina generation, official `abguard` validation and co-folding
still require the supplied VM tools and verified organizer documentation.
No suitable thermostability predictor or real validated candidate batch is
bundled. See [implementation status](docs/implementation-status.md) for the
exact completed features and external prerequisites.

## Start here

Ask in `#team-13` for the **VM IP and the SSH key**. The API keys are already on the
VM, so that is all you need from us. Nothing secret is in this repo. 5 minutes, in order:

**1 · Get on the GPU box**

```bash
mv ~/Downloads/team-13 ~/.ssh/team-13 && chmod 600 ~/.ssh/team-13
ssh -i ~/.ssh/team-13 hackathon@<ip-from-slack>
mkdir -p ~/<yourname> && cd ~/<yourname>      # we share one home — stay in your folder
```

One H100, shared by all of us. Claude Code is on it: `ssh ... -t bash -l`, then `claude`.

**2 · Hosted models, no GPU needed**

Unzip `participant-14.zip` from Slack *outside this repo*, then:

```bash
cd participant-14 && bash agent/install.sh
export NEBIUS_CREDS="$PWD/credentials.private.json"
python3 ~/.claude/skills/nebius-scientific-ai/forge.py models
```

Start `claude` from that shell and ask it to fold something. Jobs print an id
(`op-1234abcd`); `forge.py status|fetch <id>` picks them back up later.

**3 · The paid-for extras — JapanFold and AMASS**

Both keys are already on the VM, in the shared home directory:

```bash
set -a && . ~/team-13-keys.env && set +a
npx skills add japanfold/japanfold      # optional, adds it to Claude Code
```

Working from your own laptop instead? Ask in `#team-13` for a copy of that file.

That loads both keys at once: **JapanFold** ($1,100, no expiry — RoseTTAFold3, OpenDDE,
AF2-IG) and **AMASS** ($100, expires 14 Dec — papers, trials, patents).

Done. You can run a model from any of the three.

## Four things that will bite you

- **The VM dies Saturday night.** Commit results here as you go.
- **First model call can queue 15 min.** Start long jobs early; never submit the same job twice.
- **`abguard` rejects designs silently if you forget the filters** — ≤250 aa, no unpaired
  cysteines, and the novelty rules in [the brief](docs/brief.md#submission-rules).
- **Never paste a key into Slack or a prompt.** Keys go in `*.env`, which is gitignored.

## Where things go

`artifacts/antibodylab/` scientific iterations and SQLite metadata (gitignored) ·
`results/` legacy reports · `nebius-runs/` hosted run IDs. Review exports before
sharing: raw model logs and profiles may contain environment-specific details.
