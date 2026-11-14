"""Sequence features shared by the gate stage and the three axis predictors.

Everything here is pure sequence arithmetic on the standard library, because
the demo has to run on a judge's laptop with no network. Where a feature is a
local approximation of a hosted tool the team has access to, the docstring says
so and names the tool — the honest version of "expression screened" is "we
screened it with a proxy and here is which one", not a tool name we did not
actually call.

Scales used, named so they can be checked:

  hydropathy      Kyte & Doolittle (1982), the standard -4.5..4.5 scale
  pKa             EMBOSS-style side-chain values, used only for pI by bisection
  volume          relative side-chain bulk, used for the substitution-severity
                  term in the binding prior

No published Aggrescan a3v values are reproduced here. The aggregation term is
a windowed-hydropathy proxy and is labelled as such everywhere it surfaces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NATURAL_AA = frozenset("ACDEFGHIKLMNPQRSTVWY")

# Kyte & Doolittle hydropathy.
HYDROPATHY = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5,
    "Q": -3.5, "E": -3.5, "G": -0.4, "H": -3.2, "I": 4.5,
    "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6,
    "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}

# Side-chain pKa values (EMBOSS-style) plus terminal groups, for pI only.
_PKA_ACID = {"D": 3.65, "E": 4.25, "C": 8.18, "Y": 10.07}
_PKA_BASE = {"K": 10.53, "R": 12.48, "H": 6.00}
_PKA_NTERM, _PKA_CTERM = 9.69, 2.34

# Relative side-chain volume (A^3, Zamyatnin-style ordering). Used only as a
# "how big a change was that" term, so the ordering matters more than the units.
VOLUME = {
    "G": 60, "A": 89, "S": 89, "C": 109, "D": 111, "P": 113, "N": 114,
    "T": 116, "E": 138, "V": 140, "Q": 144, "H": 153, "M": 163, "I": 167,
    "L": 167, "K": 169, "R": 174, "F": 190, "Y": 194, "W": 228,
}

CHARGED = frozenset("DEKRH")
AROMATIC = frozenset("FWY")
# Residues that dominate antibody-antigen paratopes; Y/W/S/G enrichment in CDRs
# is one of the most reproducible observations in the structural literature.
PARATOPE_FAVOURED = frozenset("YWSGDNTR")

# scFv linkers are GS-rich. Splitting on one lets us check cysteine parity per
# chain, which is how the lab sees it: two chains each with one free cysteine
# read as "even" if you count the joined construct in one go.
_LINKER_RE = re.compile(r"(?:GGGGS){2,}|(?:GGGS){3,}|(?:GS){6,}")

# CDRH3 sits between the conserved FR3 cysteine (with its two-residue stub,
# A-R in most germlines, S-R in trastuzumab) and the W-G-x-G of FR4. The stub
# must be consumed, not captured: including it shifts the alignment against the
# reference loop by two positions and silently understates identity, which is
# the direction that lets a near-copy of trastuzumab through the ceiling.
#
# WHERE THE LOOP ENDS IS NOT A CONSTANT. Strict Kabat runs the loop up to the
# residue before the W of FR4's W-G-x-G, which reads trastuzumab's CDRH3 as the
# 11-mer WGGDGFYAMDY. The challenge datasets do not: every one of the 524k
# variant rows and every SPR row is a 10-mer, placing that trailing Y in the
# framework — ...YYCSR-[WGGDGFYAMD]-Y-WGQGTLV... So the convention is a
# property of the reference we were given, not something to hardcode, and
# `detect_fr4_offset` reads it off the reference instead of assuming. Getting
# this wrong is silent and total: under the Kabat reading the parent scores
# 10/11 identity against *itself* and every identity gate shifts with it.
_CDRH3_TEMPLATE = r"C[A-Z]{{2}}([A-Z]{{1,32}}?)[A-Z]{{{offset}}}WG[A-Z]G"
_CDRH3_CACHE: dict[int, re.Pattern] = {}
# CDRH1/H2 anchors, Kabat-ish. Best effort only — immunum is the authority and
# these exist so the stability axis can see framework-vs-loop, not to gate on.
_CDRH1_RE = re.compile(r"C[A-Z]{4}([A-Z]{8,12})W[VIF][RKQ]Q")
_CDRH2_RE = re.compile(r"W[VIF][RKQ]Q[A-Z]{8,12}([A-Z]{16,19})(?:RF|KA|RV)")


def _cdrh3_re(fr4_offset: int = 0) -> re.Pattern:
    if fr4_offset not in _CDRH3_CACHE:
        _CDRH3_CACHE[fr4_offset] = re.compile(_CDRH3_TEMPLATE.format(offset=fr4_offset))
    return _CDRH3_CACHE[fr4_offset]


def detect_fr4_offset(vh: str | None, cdrh3: str | None) -> int:
    """How many residues the reference's convention puts between CDRH3 and FR4.

    0 is the strict Kabat reading, 1 is the 10-mer convention both challenge
    datasets use. Derived, never assumed: pass the reference VH and its stated
    CDRH3 and this reports which convention they are written in, so the
    extractor agrees with whatever the organisers' files say.
    """
    vh, cdrh3 = clean(vh), clean(cdrh3)
    if not vh or not cdrh3:
        return 0
    idx = vh.find(cdrh3)
    if idx < 0:
        return 0
    m = re.search(r"WG[A-Z]G", vh[idx + len(cdrh3) :])
    return m.start() if m else 0


def clean(seq: str | None) -> str:
    return (seq or "").upper().strip().replace(" ", "").replace("\n", "")


def chains_of(seq: str, declared: list[str] | None = None) -> list[str]:
    """Split a construct into chains. scFv linkers are detected, not assumed."""
    if declared:
        return [clean(c) for c in declared if clean(c)]
    seq = clean(seq)
    if not seq:
        return []
    parts = [p for p in _LINKER_RE.split(seq) if p]
    return parts or [seq]


def unpaired_cysteines(seq: str) -> bool:
    """Odd cysteine count in a single chain. Parity is the cheap proxy for the
    real question (is every cysteine in a disulfide), and the entry rules are
    written in terms of unpaired cysteines, so parity is what we gate on."""
    return clean(seq).count("C") % 2 == 1


def net_charge(seq: str, ph: float = 7.4) -> float:
    """Net charge at pH, Henderson-Hasselbalch over side chains and termini."""
    seq = clean(seq)
    if not seq:
        return 0.0
    q = 0.0
    for aa, pka in _PKA_BASE.items():
        q += seq.count(aa) / (1.0 + 10.0 ** (ph - pka))
    for aa, pka in _PKA_ACID.items():
        q -= seq.count(aa) / (1.0 + 10.0 ** (pka - ph))
    q += 1.0 / (1.0 + 10.0 ** (ph - _PKA_NTERM))
    q -= 1.0 / (1.0 + 10.0 ** (_PKA_CTERM - ph))
    return q


def isoelectric_point(seq: str) -> float:
    """pI by bisection on net_charge. Matters because a formulation buffer near
    the pI is where antibodies aggregate, and aggregation is a thermostability
    failure the assay will see."""
    lo, hi = 2.0, 13.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if net_charge(seq, mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def gravy(seq: str) -> float:
    """Mean hydropathy. Standard developability readout."""
    seq = clean(seq)
    vals = [HYDROPATHY[a] for a in seq if a in HYDROPATHY]
    return sum(vals) / len(vals) if vals else 0.0


def hydrophobic_patches(seq: str, window: int = 5, threshold: float = 1.6) -> list[tuple[int, float]]:
    """Windows whose mean hydropathy clears `threshold`.

    A LOCAL PROXY for Aggrescan 3D, which is structure-aware and which we
    should call on the shortlist when the VM is free. Surface-exposed
    hydrophobic patches are the classic aggregation nucleus; a sequence-only
    window cannot know what is exposed, so this over-reports buried core
    stretches and is used as a relative signal against trastuzumab, never as
    an absolute pass/fail.
    """
    seq = clean(seq)
    out: list[tuple[int, float]] = []
    if len(seq) < window:
        return out
    for i in range(len(seq) - window + 1):
        w = seq[i : i + window]
        mean = sum(HYDROPATHY.get(a, 0.0) for a in w) / window
        if mean >= threshold:
            out.append((i, round(mean, 3)))
    return out


def patch_burden(seq: str, window: int = 5, threshold: float = 1.6) -> float:
    """Total excess hydropathy over threshold across all patches.

    One number for "how much sticky surface is there", so the stability axis
    can compare a design against the baseline rather than against a constant.
    """
    return round(sum(m - threshold for _, m in hydrophobic_patches(seq, window, threshold)), 3)


def extract_cdrh3(seq: str, fr4_offset: int = 0) -> str | None:
    """Best-effort CDRH3 from a heavy chain. None when the anchors are absent.

    `fr4_offset` selects the loop-boundary convention; get it from
    `detect_fr4_offset(ref.vh, ref.cdrh3)` so the extraction agrees with the
    reference rather than with a scheme we picked.

    Heuristic for the fast path only. immunum/abguard is the authority, and a
    design whose CDRH3 we cannot locate is flagged rather than guessed at.
    """
    hits = _cdrh3_re(fr4_offset).findall(clean(seq))
    return max(hits, key=len) if hits else None


def extract_cdrs(seq: str, fr4_offset: int = 0) -> dict[str, str | None]:
    """H1/H2/H3 by anchor match. Any of them may be None."""
    seq = clean(seq)
    h1 = _CDRH1_RE.findall(seq)
    h2 = _CDRH2_RE.findall(seq)
    return {
        "h1": h1[0] if h1 else None,
        "h2": h2[0] if h2 else None,
        "h3": extract_cdrh3(seq, fr4_offset),
    }


def framework_of(seq: str, fr4_offset: int = 0) -> str:
    """The chain with its detectable CDR loops removed.

    The split matters because the two axes pull in opposite directions: CDR
    change is what the optimisation track *requires*, while framework change
    is nearly all downside on thermostability. Scoring them together would
    average away the only actionable signal.
    """
    seq = clean(seq)
    for loop in extract_cdrs(seq, fr4_offset).values():
        if loop:
            seq = seq.replace(loop, "", 1)
    return seq


@dataclass
class Developability:
    """The expression pre-screen readout for one construct.

    A design that does not express is measured on nothing and scores nothing on
    all three axes, so this runs inside the gate stage rather than as polish
    later. `verdict` is advisory by default: we do not have measured expression
    data for these constructs, and hard-failing a design on a sequence proxy
    would be exactly the overconfidence we are criticising other teams for.
    """

    length: int = 0
    n_chains: int = 1
    cysteines: int = 0
    unpaired_cys_chains: list[int] = field(default_factory=list)
    net_charge: float = 0.0
    pi: float = 0.0
    gravy: float = 0.0
    patch_burden: float = 0.0
    n_patches: int = 0
    flags: list[str] = field(default_factory=list)
    tools_not_called: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


# Thresholds are deliberately loose. They are aggregation/solubility rules of
# thumb from antibody developability practice, not measurements on this target,
# and they exist to raise a flag a human reads, not to silently drop designs.
_PI_WINDOW = 1.0  # |pI - 7.4| below this = aggregation risk in neutral buffer
_GRAVY_CEILING = -0.10
_PATCH_BURDEN_CEILING = 3.0


def developability(seq: str, declared_chains: list[str] | None = None) -> Developability:
    """Local expression/solubility screen.

    Implemented locally: length, chain-aware cysteine parity, net charge, pI,
    GRAVY, windowed hydrophobic-patch burden.

    NOT called here, and named so nobody mistakes this for them: Aggrescan 3D
    (structure-aware aggregation), SoluProt and NetSolP (learned solubility),
    ProteinMPNN soluble weights (sequence redesign for solubility). Those are
    the tools the brief credits for lifting Adaptyv's earlier rounds and they
    want a GPU or a hosted call. Run them over the shortlist once generation
    frees the H100 — twenty designs, not twenty thousand — and overwrite these
    numbers with theirs.
    """
    chains = chains_of(seq, declared_chains)
    joined = "".join(chains)
    d = Developability(
        length=len(joined),
        n_chains=len(chains),
        cysteines=joined.count("C"),
        unpaired_cys_chains=[i for i, c in enumerate(chains) if unpaired_cysteines(c)],
        net_charge=round(net_charge(joined), 2),
        pi=round(isoelectric_point(joined), 2),
        gravy=round(gravy(joined), 3),
        patch_burden=patch_burden(joined),
        n_patches=len(hydrophobic_patches(joined)),
        tools_not_called=["aggrescan3d", "soluprot", "netsolp", "proteinmpnn-soluble"],
    )
    if abs(d.pi - 7.4) < _PI_WINDOW:
        d.flags.append(f"pi_near_neutral:{d.pi}")
    if d.gravy > _GRAVY_CEILING:
        d.flags.append(f"gravy_high:{d.gravy}")
    if d.patch_burden > _PATCH_BURDEN_CEILING:
        d.flags.append(f"hydrophobic_patch_burden:{d.patch_burden}")
    if d.unpaired_cys_chains:
        d.flags.append(f"unpaired_cysteine_chains:{d.unpaired_cys_chains}")
    return d
