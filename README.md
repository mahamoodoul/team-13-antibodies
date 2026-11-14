# team-13 — AI × Antibodies Hackathon, Oslo

Improving **trastuzumab** (anti-HER2). Designs are measured by Adaptyv on three axes:
binding (SPR), epitope preservation, thermostability. Beat all three = S-tier.
Two S-tier designs beat ten that each improve one thing.

Full brief: **[docs/brief.md](docs/brief.md)** — submission rules, data, models, scoring.
The plan: **[docs/plan.md](docs/plan.md)** — strategy, who owns what, the day, the pitch.

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

`results/` model outputs · `nebius-runs/` run ids · both safe to commit, both help us
show where a number came from.
