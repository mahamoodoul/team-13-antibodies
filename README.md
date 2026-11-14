# team-13 — AI × Antibodies Hackathon, Oslo

Our working repo for the [AI × Antibodies Hackathon](https://oslo-ai-antibodies-hackathon.vercel.app)
(BI Norwegian Business School, 14 November 2026).

**The task:** improve **trastuzumab** (anti-HER2). Submit VHH, scFv or Fab designs on
either track — *optimisation* (point mutations) or *de novo* — and they get measured
by Adaptyv on three axes against the real trastuzumab baseline:

| Property | Measured by |
| --- | --- |
| Binding to HER2 | SPR |
| Epitope preservation | competitive binding vs trastuzumab |
| Thermostability | direct measurement |

S-tier beats all three, A-tier two, B-tier one. **Two designs that improve all three
beat ten that each improve one** — so we optimise for depth, not volume.

---

## Setup for teammates

Work through these in order. Steps 1 and 2 are needed by everyone; 3 and 4 are shared
credits that are already claimed, so you just need the keys.

### 0. Before you start

You need `git`, Python 3, an SSH client, and [Claude Code](https://claude.com/claude-code).
Ask in `#team-13` for the **secrets bundle** — the VM IP, the SSH key and the two API
keys. None of them are in this repo, and none of them should ever be pasted into Slack
in plain text or into a chat with a model.

### 1. The GPU box

Each team has one VM on Nebius AI Cloud: **1× H100 80GB, 16 vCPU, 200 GB RAM, 500 GB disk,
Ubuntu 24.04**. The IP and the SSH key are in Davide Campagna's message in `#team-13`
(Bitwarden Send link).

```bash
mv ~/Downloads/team-13 ~/.ssh/team-13
chmod 600 ~/.ssh/team-13
```

Add a host entry so you can type `ssh team13` instead of the full command — substitute
the IP from Slack:

```
Host team13
  HostName <ip-from-slack>
  User hackathon
  IdentityFile ~/.ssh/team-13
  IdentitiesOnly yes
  ServerAliveInterval 60
```

**We all share one user, one home directory and one GPU.** Make yourself a folder
(`mkdir ~/<yourname>`) and stay in it, or we will overwrite each other.

What is already on the box:

- `claude` at `~/.local/bin/claude` — only on PATH in a login shell, so use `ssh team13 -t bash -l`
- `foundry-toolkit` — run `foundry-toolkit login` once, then `foundry-toolkit module list`
- Apheris Foundry models as pre-pulled Docker images
- read-only creds for the data bucket: `aws s3 sync s3://apheris-oslo-hackathon/<folder> ./data`
- RCSB MCP for protein structures
- `abguard` — **not on PATH as of 14 Nov, ask the Apheris team on site**

> **The VM is destroyed at the end of Saturday 14 November.** Anything you want to keep
> must be copied off before then. Commit results here as you go.

### 2. Nebius Scientific AI — ~60 hosted models, no GPU needed

The kit is a Slack attachment (`participant-14.zip`, in `#team-13`) and is **not** in this
repo, because it carries our private credentials. Unzip it somewhere outside the repo, then:

```bash
cd participant-14
bash agent/install.sh
export NEBIUS_CREDS="$PWD/credentials.private.json"
python3 ~/.claude/skills/nebius-scientific-ai/forge.py models
```

That installs 51 model skills into `~/.claude/skills` and lists what you can call —
34 of 59 models have a tested input format. The useful ones for us:

| Model | Time | What for |
| --- | --- | --- |
| `boltz2` | ~80s | fast structure of a complex, needs an A3M per chain |
| `nanobodybuilder2` | ~2m | VHH structure from one sequence |
| `abodybuilder3` | ~2m | paired antibody structure from H/L FASTA |
| `antifold` | ~110s | antibody CDR redesign |
| `stab-ddg` | ~12m | binding ddG for point mutations — directly relevant to our thermostability axis |
| `proteinmpnn` | ~100s | sequences for a fixed backbone |
| `rfd4-proteina` | ~5m | binder design guided to a site |
| `esm2-650m` | ~4m | sequence likelihood scores |

Jobs return an id like `op-1234abcd`. Keep it — you can close the laptop and come back:

```bash
F=~/.claude/skills/nebius-scientific-ai/forge.py
python3 "$F" runs                       # everything you started
python3 "$F" status op-1234abcd
python3 "$F" fetch  op-1234abcd --dest results/run1
```

A first call can queue for up to 15 minutes while the model loads, and sixteen teams
share the platform — **start long jobs early and never submit the same job twice.**
Browser alternative: the `workbench_url` in the credentials file; pick *GLM 5.3 Flash*
in chat, the default is slow.

### 3. JapanFold — $1,000 of credit, redeemed

Balance is **$1,100** and does not expire. $0.26 per processor-hour, and you are not
charged for queue time or for runs that fail. A 512-residue Boltz-2 fold costs about
$0.006, so this is effectively unlimited for our purposes.

Sign-in is a code emailed to the account holder, so **use the API token, not the login**:

```bash
export JAPANFOLD_API_KEY=<ask in #team-13>
export JAPANFOLD_BASE_URL=https://api.japanfold.aiand.com
```

```bash
npx skills add japanfold/japanfold     # then start Claude Code from that same shell
```

Worth it for three models nothing else in our stack has: **RoseTTAFold3**, **OpenDDE**
(built for antibody–antigen complexes) and **AF2-IG** (scores a binder you already
designed — slots straight into our ranking step). Also serves BoltzGen, RFdiffusion3,
PXDesign, Mol-1, ESMC and SaProt.

### 4. AMASS — $100 of credit, claimed

**Expires 14 December 2026**, unlike the JapanFold credit, so use it now.

```bash
export AMASS_API_KEY=<ask in #team-13>
```

Plain-language search over papers, clinical trials, patents and drug records, with every
answer linked back to source. This is our cheapest route to points: **judgment is 40% of
the pitch score** — "clear reasoning behind the molecules you chose" — and AMASS is how we
cite that reasoning instead of asserting it. Best use of the platform also wins a free month.

---

## Rules that decide whether a design even counts

Every submission is checked by `abguard` before it goes anywhere. A design that fails is
not submitted — it is never moved to the other track.

**Everyone:** format is VHH, scFv or Fab · ≤250 aa total (combined for VH+VL) · no unpaired
cysteines · immunum numbering confidence ≥0.1.

**De novo track** (<70% identity to any known antibody): needs ≥2 CDRH3 mutations from trastuzumab.

**Optimisation track** (everything else): needs <70% CDRH3 identity to trastuzumab **and**
strictly more than 2 point mutations from any antibody in the provided data.

Designs also have to survive cell-free expression to be measured at all. Adaptyv's prior
rounds improved once teams scored candidates with **Aggrescan 3D, SoluProt, NetSolP and
ProteinMPNN soluble weights** — cheap filters, worth running before we rank.

## Data we have been given

| Dataset | Size | Modality |
| --- | --- | --- |
| Trastuzumab CDRH3 variants vs HER2 | 524,346 variants, ≤10 mutated positions | FACS, 3 affinity classes |
| Optimisation designs from the same study | ~700, of which 190 measured | SPR |
| VHH–antigen true negatives | 454 pairs | SPR, no measurable binding |
| Cognate VHH–antigen affinities | 15 | SPR, all sub-µM |
| Predicted complexes | 1.8M structures, AF3 + Boltz-2 + Chai-1 | computational |

The true negatives are the interesting ones: they are the only way to calibrate a
structure-confidence cutoff before trusting it to rank our designs.

## RFD4-Proteina weights on the VM

| Weight | Known binders | Passes novelty | Interface err | Use for |
| --- | --- | --- | --- | --- |
| `antibody-2026-10-30` | 0% | 100% | 8.2 Å | any CDR, fixed framework |
| `her2-2026-11-07` balanced | 21% | 6% | 9.1 Å | CDRH3, leans on measured binders |
| `her2-2026-11-07` exploratory | 0.3% | 74% | 9.1 Å | CDRH3, more varied loops |
| `her2-novel-2026-11-09` | 4% | 86% | **6.8 Å** | CDRH3, best confident fit |

A known binder *fails* the novelty filter, so filter before ranking. Pipeline is
`design` → `refold-prepare` → fold with a template-taking model (OpenFold3 / Protenix /
Boltz-2 / Mol-1 — not ESMFold2, which folds the target unguided) → `refold-score`.
The pass column is empty for the HER2 exercise, so rank on `min_ipae`, `iptm`, `binder_plddt`.
Tutorial and a ready-made HER2 script: `rfd4-proteina/docs/Tutorial.html` in the data bucket.

## How we are scored

**Pitch (today):** 40% judgment · 20% execution (this repo, reproducible) · 20% user fit ·
20% path to value.

Placing well buys us more wet-lab slots: every team gets 4 designs tested, 1st place 16,
2nd 12, 3rd 8, and each of the 6 judges nominates a favourite for +2. We submit a ranked
list of up to 20.

**Prizes:** €3000 split evenly across the two tracks (€800 / €500 / €200 each), plus $500
for best pitch.

## Secrets

Credentials live in gitignored files (`*.env`, `*.private.json`) and are shared person to
person, never in the channel and never in a prompt. If you leak one: JapanFold and AMASS
keys can be revoked and reissued from their dashboards in under a minute — do that rather
than hoping.

## Layout

```
README.md            this guide
.gitignore           every credential pattern we use
results/             model outputs, safe to commit (no keys)
nebius-runs/         run ids, safe to commit
```
