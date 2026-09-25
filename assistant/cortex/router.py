"""The universal intent router — the cortex layer's decision core.

Ranks EVERY routable surface (277 registry tools, 5 presets, the coarse
explain/undo/history/scheme/wallpaper/diagnose/search/brain/issue
surfaces) against one user phrase, using four complementary signals:

1. LEXICAL — BM25+ (vectorize.TfidfIndex) with query expansion:
   typo correction (bounded Levenshtein, distance <= 2) then synonym
   expansion (lexicon.SYNONYMS, including hyphen-bigram forms like
   "see through" -> transparency) then stemming. Expansion happens on
   the QUERY side only — the index stays pure registry vocabulary.
2. SEMANTIC — PPMI cosine (vectorize.PpmiEmbedder) between the query
   embedding and each candidate's document embedding: catches phrases
   whose words never literally overlap any tool vocabulary.
3. FUZZY — character 3-gram cosine between the raw query and the
   candidate's name atoms: catches compound-name addressing
   ("greeter morning start" vs ``setGreeterMorningStart``).
4. NOUN — the frozen noun regexes of the 18 core tools (parser.py's
   own grammar, rebuilt from the registry so the surfaces cannot drift):
   an exact noun hit is the strongest single lexical signal there is.

On top of the four signals sit two DETERMINISTIC structural layers
(grammar, not statistics — deliberately so they can be audited):

- PATTERN BOOSTS: why-questions floor the ``explain`` surface; leading
  undo/revert/restore/rollback floors ``undo``; history phrasings floor
  ``history``; preset trigger words floor their preset (mirroring the
  frozen parser's own precedence: preset triggers fire BEFORE per-tool
  nouns — "make my bar compact" is the compact preset, exactly as
  parser.py §3.7 treats it).
- CUE-KIND AGREEMENT: extracted value cues must AGREE with the
  candidate's kind. A direction cue ("thinner") boosts numeric tools
  and penalizes bool/enum ones; a bool cue boosts bool tools; a
  position cue and literal enum-value words boost enum tools. This is
  the router-side mirror of parser.py §3.3 step 5's direction classes,
  generalized to all 277 tools via the registry's kind metadata.

Verdicts (honest, never a silent guess):

- ``ROUTED``   — clear winner (score >= min_score, margin >= min_margin)
- ``AMBIGUOUS``— near-tie: question + top candidates listed
- ``ABSTAIN``  — nothing scored well: "no setting clearly matches"

The router NEVER writes: its output is candidates + cues + evidence.
All value resolution and all writes stay in the settings
planner/applier spine. Deterministic: pure function of (text, state);
the embedder's projection uses a fixed seed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..settings.registry import PRESETS, TOOL_SPECS
from .corpus import tool_atoms, tool_document
from .lexicon import (
    ABSOLUTE_WORDS,
    BOOL_OFF_WORDS,
    BOOL_ON_WORDS,
    DIRECTION_WORDS,
    SYNONYMS,
    camel_split,
    levenshtein,
    ngram_similarity,
    stem,
)
from .vectorize import TfidfIndex, embedder, tokenize

# ---------------------------------------------------------------------------
# Router state (the learnable part).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouterState:
    """Weights and thresholds. Defaults are hand-set priors; ``learn.py``
    fits ``w_lex/w_sem/w_fuzz/w_noun`` and ``bias`` from ledger decisions
    via online logistic regression, and adapts ``min_score``/``min_margin``
    from calibration. Frozen-friendly (dataclasses.replace)."""

    w_lex: float = 0.42
    w_sem: float = 0.22
    w_fuzz: float = 0.14
    w_noun: float = 0.18
    bias: float = 0.04
    min_score: float = 0.30
    min_margin: float = 0.06
    temperature: float = 0.45

    def weights_vector(self) -> Tuple[float, float, float, float, float]:
        return (self.w_lex, self.w_sem, self.w_fuzz, self.w_noun, self.bias)

    def to_dict(self) -> Dict[str, float]:
        return {
            "w_lex": self.w_lex, "w_sem": self.w_sem, "w_fuzz": self.w_fuzz,
            "w_noun": self.w_noun, "bias": self.bias,
            "min_score": self.min_score, "min_margin": self.min_margin,
            "temperature": self.temperature,
        }

    @staticmethod
    def from_dict(data: Optional[Dict[str, float]]) -> "RouterState":
        if not data:
            return RouterState()
        fields = RouterState.__dataclass_fields__
        return RouterState(**{k: float(v) for k, v in data.items() if k in fields})


DEFAULT_STATE = RouterState()


# ---------------------------------------------------------------------------
# Result shapes.
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    surface: str                 # tool name, "preset:<name>", or coarse label
    kind: str                    # "tool" | "preset" | "surface"
    score: float                 # raw hybrid score
    p: float                     # softmax probability
    cues: Dict[str, object]      # value-extraction hints (direction/bool/...)
    evidence: List[str] = field(default_factory=list)


@dataclass
class RouteResult:
    verdict: str                 # ROUTED | AMBIGUOUS | ABSTAIN
    candidates: List[Candidate]
    question: Optional[str] = None
    features: Dict[str, Dict[str, float]] = field(default_factory=dict)

    @property
    def top(self) -> Optional[Candidate]:
        return self.candidates[0] if self.candidates else None


# ---------------------------------------------------------------------------
# Deterministic structural layers.
# ---------------------------------------------------------------------------

# Coarse surfaces and their canonical seed documents.
_SURFACE_DOCS: Tuple[Tuple[str, str], ...] = (
    ("explain", "explain why what controls which setting"),
    ("undo", "undo revert rollback restore last change back"),
    ("history", "history recent changes what did i change log"),
    ("scheme", "scheme color colour palette theme accent"),
    ("wallpaper", "wallpaper background image desktop"),
    ("diagnose", "broken crash error not working fails troubleshoot problem"),
    ("search", "docs documentation how do i find look up"),
    ("brain", "plan tasks focus estimate organize notes remind"),
    ("issue", "bug report issue draft file"),
    # genius: the universal intelligence layer (math/logic/probability/
    # statistics/decision/text-analysis questions). Seeded deliberately
    # with vocabulary that no settings tool owns, so a settings phrase
    # can never lose to a coincidental genius word.
    ("genius", "solve calculate compute derivative integral equation root "
               "probability bayes matrix eigenvalue tautology truth table "
               "permutation regression correlation outlier average numbers"),
)

# Pattern boosts: (regex, surface, floor). A matching pattern floors the
# candidate's score at the given value — grammar beats statistics, so a
# why-question can never lose to a coincidental noun overlap. "what did"
# is deliberately NOT a why-question ("what did i change" is history).
_WHY_RE = re.compile(r"^\s*(?:why\s+(?:is|are|was|were|does|do|did)|what\s+(?:is|are|does|do))\b")
_EXPLAIN_HINT_RE = re.compile(r"\b(?:explain|what\s+controls|which\s+setting|what\s+setting)\b")
_UNDO_RE = re.compile(r"^\s*(?:undo|revert|roll\s?back|restore)\b")
_HISTORY_RE = re.compile(r"\b(?:what\s+did\s+i\s+change|change\s+history|my\s+changes|show\s+history|\bhistory\b)\b")
# genius shapes: arithmetic, equations, and named math/logic questions are
# never settings requests — high-precision only, so no settings phrase
# can trip it by accident.
_GENIUS_RE = re.compile(r"\d\s*[+\-*/^%]\s*\d|\d+(?:\.\d+)?\s*%\s*(?:of|off)\s*\d+|"
                        r"\bsolve\b|\bderivative\b|\bintegral\b|"
                        r"\btaylor\b|\btautolog\w*\b|\bsatisfiable\b|\btruth table\b|"
                        r"\bbayes\b|\beigenvalue\b|\bhow many ways\b")

PATTERN_BOOSTS: Tuple[Tuple[re.Pattern[str], str, float], ...] = (
    (_WHY_RE, "explain", 0.78),
    (_EXPLAIN_HINT_RE, "explain", 0.66),
    (_UNDO_RE, "undo", 0.78),
    (_HISTORY_RE, "history", 0.80),
    (_GENIUS_RE, "genius", 0.82),
)

# Preset triggers (parser.py §3.7 precedence: preset BEFORE per-tool
# nouns — "make my bar compact" IS the compact preset there, and here).
# Floors sit above every tool-level hybrid (noun floor + BM25 + cue
# agreement tops out ~0.8) so preset precedence is decisive, mirroring
# the frozen grammar's own ordering.
_PRESET_TRIGGERS: Tuple[Tuple[re.Pattern[str], str, float], ...] = (
    (re.compile(r"\b(?:more\s+compact|compact|denser|tighter)\b"), "preset:compact", 0.88),
    (re.compile(r"\b(?:minimalist|minimal\s+look|minimal\s+setup|minimal|cleaner\s+look|simpler\s+look|declutter)\b"), "preset:minimal", 0.88),
    (re.compile(r"\b(?:gaming|game\s+mode\s+look|optimize\s+for\s+gaming|for\s+games?)\b"), "preset:gaming", 0.86),
    (re.compile(r"\b(?:battery|power\s+sav(?:ing|er))\b"), "preset:battery-saver", 0.86),
    (re.compile(r"\b(?:macos|mac\s?os|apple\s+style|more\s+like\s+apple)\b"), "preset:macos-like", 0.86),
)

# Position vocabulary (parser.py §3.4) — a cue AND enum vocabulary.
_POSITION_RE = re.compile(r"\b(top|bottom|left|right)\b(?:\s+(?:edge|side))?")
_POSITION_VALUES = frozenset({"top", "bottom", "left", "right"})

# "Move the dock/bar to the left" — issue #120's own example. A position
# word together with a shell-surface noun (dock/bar/panel/taskbar/shell)
# is position-setting grammar, decisive over size tooling on the same noun.
_SURFACE_POS_RE = re.compile(
    r"\b(?:dock|bar|panel|taskbar|shell)\b[^.!?]{0,40}\b(?:left|right|top|bottom)\b"
    r"|\b(?:left|right|top|bottom)\b[^.!?]{0,40}\b(?:dock|bar|panel|taskbar|shell)\b"
)
_BAR_POSITION_FLOOR = 0.80

# Scheme/wallpaper SYSTEM requests (parser.py §3.3 step 3's dead-ends):
# "change my wallpaper" / "new background" live OUTSIDE shell.json and
# must floor the inert-suggestion surfaces over the wallpaper-ADJACENT
# tools (recolor strength, wallpaper enabled...). A qualifier word
# (recolor/recolour/strength/saturation) means the shell.json tool and
# suppresses the system floor.
_SCHEME_SYS_RE = re.compile(
    r"\b(?:change|set|new|switch|pick|choose|different|random)\b[^.!?]{0,30}\b"
    r"(?:scheme|schemes|colou?rs?|palette|palettes|theme|themes|accent|accents)\b"
    r"|\b(?:scheme|colou?rs?|palette|theme|accent)s?\b[^.!?]{0,30}\b(?:change|new|switch)\b"
)
_WALLPAPER_SYS_RE = re.compile(
    r"\b(?:change|set|new|switch|random|shuffle|pick|choose|different)\b[^.!?]{0,30}\b"
    r"(?:wallpapers?|backgrounds?)\b"
    r"|\b(?:wallpapers?|backgrounds?)\b[^.!?]{0,30}\b(?:change|new|switch|random|shuffle)\b"
)
_SYS_QUALIFIER_RE = re.compile(r"\b(?:recolou?r|strength|saturation|intensity|enabled|disable|enable)\b")
_SCHEME_FLOOR = 0.74
_WALLPAPER_FLOOR = 0.74

# Cue-kind agreement factors (multiples of w_noun).
_K_DIRECTION_NUMERIC = 0.55     # direction cue + float/int tool: agree
_K_DIRECTION_OTHER = -0.35      # direction cue + non-numeric: disagree
_K_BOOL_BOOL = 0.55             # on/off cue + bool tool: agree
_K_BOOL_OTHER = -0.25           # on/off cue + non-bool: disagree
_K_POSITION_ENUM = 0.65         # position cue/word + enum tool: agree
_K_POSITION_OTHER = -0.30       # position cue + non-enum: disagree
_K_ENUM_WORD = 0.60             # literal enum value present: agree
_K_NUMBER_NUMERIC = 0.30        # explicit number/percent + numeric: agree
_K_TRANSPARENCY_AGREE = 0.90    # see-through/translucent cue + transparency tool (property words
                                 # determine the tool class; they must be decisive)
_K_TRANSPARENCY_OTHER = -0.50   # see-through/translucent cue + unrelated tool

# Transparency vocabulary: multi-word cue the single-word DIRECTION scan
# cannot see, with its own tool class (path or nouns mention
# transparency/opacity — the property words determine the tool class;
# surface nouns like "panels" only refine which thing).
_TRANSPARENCY_CUE_RE = re.compile(r"\b(?:see\s*-?\s*through|translucent|transparent|transparency)\b")
_TRANSPARENCY_TOOL_RE = re.compile(r"(?:^|\.)(?:transparency|opacity)|transparency|opacity", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Candidate universe + per-surface documents.
# ---------------------------------------------------------------------------


def _enum_value_words(spec) -> List[str]:
    """Serialized enum values as addressable vocabulary ("bottom" for
    setBarPosition, "timeOfDay" -> "time of day", metaenum keys split)."""
    if spec.kind != "enum" or not spec.enum:
        return []
    out: List[str] = []
    for value in spec.enum:
        text = str(value).replace("_", " ")
        out.extend(w.lower() for w in text.replace("-", " ").split())
    return [w for w in out if w]


def _candidate_documents() -> Dict[str, Tuple[str, str]]:
    """{surface: (document, kind)} for the full candidate universe.
    Preset documents are built from the registry's own preset metadata
    (name, label, description, called tool names) — mechanical facts,
    no invented vocabulary."""
    out: Dict[str, Tuple[str, str]] = {}
    for spec in TOOL_SPECS:
        doc = tool_document(spec)
        enum_words = _enum_value_words(spec)
        if enum_words:
            doc = doc + " " + " ".join(enum_words)
        out[spec.name] = (doc, "tool")
    for preset in PRESETS:
        name = str(preset.get("name", ""))
        label = str(preset.get("label", ""))
        description = str(preset.get("description", ""))
        calls = " ".join(str(tool) for tool, _value in preset.get("calls", ()))
        out[f"preset:{name}"] = (f"{name} {label} {description} {calls}", "preset")
    for surface, doc in _SURFACE_DOCS:
        out[surface] = (doc, "surface")
    return out


# Noun regexes of the 18 core tools (parser.py's own grammar, rebuilt
# here from the registry so the two surfaces can never drift).
_NOUN_RES: Dict[str, List[re.Pattern[str]]] = {
    spec.name: [re.compile(r"\b(?:" + group + r")\b") for group in spec.nouns]
    for spec in TOOL_SPECS if spec.nouns
}


def _noun_hit(text: str) -> List[str]:
    """Tools whose noun groups ALL appear (the parser.py rule)."""
    hits = []
    for name, regexes in _NOUN_RES.items():
        if all(rx.search(text) for rx in regexes):
            hits.append(name)
    return hits


# ---------------------------------------------------------------------------
# Query expansion: typo correction + synonyms (incl. hyphen bigrams).
# ---------------------------------------------------------------------------

_WORD_SPLIT_RE = re.compile(r"[a-z]+")


def _typo_fix(text: str, vocab: Sequence[str], max_distance: int = 1) -> Tuple[str, List[str]]:
    """Bounded-edit-distance query correction against the indexed
    vocabulary. Distance is deliberately 1 (the dominant real-typo case,
    "transparncy" -> "transparency") and words shorter than 5 characters
    are never touched — at distance 2 short garbage words start matching
    real vocabulary ("flurb" -> "blur") and the router would route pure
    noise. Only replaces a word when the correction is UNIQUE (ambiguous
    corrections are left alone — honest abstention beats confident
    mangling)."""
    vocab_set = set(vocab)
    words = _WORD_SPLIT_RE.findall(text.lower())
    fixed: List[str] = []
    evidence: List[str] = []
    for word in words:
        # A word whose STEM is already indexed vocabulary ("panels" with
        # "panel" indexed) is not a typo — the tokenizer stems both sides
        # anyway; "correcting" it would only pollute the evidence log.
        if word in vocab_set or stem(word) in vocab_set or len(word) <= 4:
            fixed.append(word)
            continue
        candidates: List[Tuple[int, str]] = []
        for cand in vocab:
            if abs(len(cand) - len(word)) > max_distance:
                continue
            d = levenshtein(word, cand, cap=max_distance)
            if d <= max_distance:
                candidates.append((d, cand))
        if len(candidates) == 1:
            best = candidates[0][1]
            evidence.append(f"typo: {word} -> {best} (edit distance {candidates[0][0]})")
            fixed.append(best)
        else:
            fixed.append(word)
    return " ".join(fixed), evidence


def _expand_query(text: str) -> Tuple[str, List[str]]:
    """Query-side expansion: typo fix, then synonym mapping of single
    words AND adjacent-pair bigrams ("see through" -> transparency via
    the "see-through" lexicon key). Original words are KEPT — synonyms
    are additive, never replacements."""
    vocab = embedder().vocab
    fixed, evidence = _typo_fix(text, vocab)
    words = _WORD_SPLIT_RE.findall(fixed)
    expanded: List[str] = list(words)
    for word in words:
        for key in (word, stem(word)):
            for mapped in SYNONYMS.get(key, ()):
                if mapped not in expanded:
                    expanded.append(mapped)
                    evidence.append(f"synonym: {word} -> {mapped}")
    for a, b in zip(words, words[1:]):
        for joined in (f"{a}-{b}", f"{a}{b}"):
            for mapped in SYNONYMS.get(joined, ()):
                if mapped not in expanded:
                    expanded.append(mapped)
                    evidence.append(f"synonym: {a} {b} -> {mapped}")
    return " ".join(expanded), evidence


# ---------------------------------------------------------------------------
# Cue extraction (value hints — hints only, never values).
# ---------------------------------------------------------------------------


def extract_cues(text: str) -> Dict[str, object]:
    """Value-extraction hints for the pipeline: direction, bool intent,
    absolute targets, reset/toggle requests, position words, plain
    numbers and percents. Mirrors parser.py's scanners where they
    overlap; used for the 259 noun-silent tools the frozen grammar
    cannot parse.

    Weak-bool rule: "show fewer notifications" is a MAGNITUDE statement,
    not an on/off statement — when a direction cue is present, bool cues
    derived from weak verbs (show/hide/display/reveal) are dropped; only
    strong verbs (on/off/enable/disable/activate/deactivate) survive.
    """
    cues: Dict[str, object] = {}
    lowered = text.lower()
    direction = 0
    for word in _WORD_SPLIT_RE.findall(lowered):
        direction += DIRECTION_WORDS.get(word, DIRECTION_WORDS.get(stem(word), 0))
    if direction:
        cues["direction"] = 1 if direction > 0 else -1
    words = set(_WORD_SPLIT_RE.findall(lowered))
    on = sorted(BOOL_ON_WORDS.intersection(words))
    off = sorted(BOOL_OFF_WORDS.intersection(words))
    if cues.get("direction"):
        # keep only STRONG bool words under a direction cue
        strong = {"on", "enable", "enabled", "activate", "off", "disable", "disabled", "deactivate"}
        on = [w for w in on if w in strong]
        off = [w for w in off if w in strong]
    if on and not off:
        cues["bool"] = True
    elif off and not on:
        cues["bool"] = False
    elif on and off:
        cues["bool"] = "mixed"
    for word, value in ABSOLUTE_WORDS.items():
        if word in lowered:
            cues["absolute"] = value
            break
    if re.search(r"\b(?:reset|default|factory)\b", lowered):
        cues["reset"] = True
    if re.search(r"\btoggle\b", lowered):
        cues["toggle"] = True
    position = _POSITION_RE.search(lowered)
    if position:
        cues["position"] = position.group(1)
    if _TRANSPARENCY_CUE_RE.search(lowered):
        cues["transparency"] = True
    pct = re.search(r"(\d+(?:\.\d+)?)\s*%", lowered)
    if pct:
        cues["percent"] = float(pct.group(1))
    num = re.search(r"\b-?\d+(?:\.\d+)?\b", lowered)
    if num:
        cues["number"] = float(num.group(0))
    return cues


# ---------------------------------------------------------------------------
# The router.
# ---------------------------------------------------------------------------


class Router:
    """One router instance = one candidate universe + one index. Build
    once per process (module-level ``router()``); route as often as
    needed. ``route()`` is a pure function of (text, state)."""

    def __init__(self) -> None:
        self.documents = _candidate_documents()
        self.index = TfidfIndex({k: doc for k, (doc, _kind) in self.documents.items()})
        self.embedder = embedder()
        self.doc_vectors = {k: self.embedder.embed(doc) for k, (doc, _kind) in self.documents.items()}
        # Fuzzy-matching surface: the addressable name atoms per candidate
        # (tool atoms from the registry; preset/surface names split as words).
        # name_atom_sets feeds the coverage signal: a tool whose compound
        # name atoms ALL appear in the query is addressing that tool
        # specifically, which outranks a generic single-noun hit.
        self.name_atoms: Dict[str, str] = {}
        self.name_atom_sets: Dict[str, frozenset] = {}
        for spec in TOOL_SPECS:
            atoms = tool_atoms(spec)
            self.name_atoms[spec.name] = " ".join(atoms)
            self.name_atom_sets[spec.name] = frozenset(atoms)
        for key, (_doc, kind) in self.documents.items():
            if kind != "tool" and key not in self.name_atoms:
                words = camel_split(key.replace("preset:", ""))
                self.name_atoms[key] = " ".join(words)
                self.name_atom_sets[key] = frozenset(words)
        self.spec_by_name = {spec.name: spec for spec in TOOL_SPECS}
        self.enum_words: Dict[str, List[str]] = {
            spec.name: _enum_value_words(spec) for spec in TOOL_SPECS if spec.kind == "enum"
        }

    # -- structural layers --------------------------------------------------

    def _pattern_floor(self, raw: str) -> Dict[str, float]:
        """{surface: floor} from pattern boosts, preset triggers, the
        position grammar (a position word + shell-surface noun floors
        setBarPosition — issue #120's "move the dock to the left"), and
        the scheme/wallpaper system dead-ends (floored only when no
        shell.json qualifier word is present)."""
        floors: Dict[str, float] = {}
        for regex, surface, floor in PATTERN_BOOSTS:
            if regex.search(raw):
                floors[surface] = max(floors.get(surface, 0.0), floor)
        for regex, surface, floor in _PRESET_TRIGGERS:
            if regex.search(raw):
                floors[surface] = max(floors.get(surface, 0.0), floor)
        if _SURFACE_POS_RE.search(raw):
            floors["setBarPosition"] = max(floors.get("setBarPosition", 0.0), _BAR_POSITION_FLOOR)
        if not _SYS_QUALIFIER_RE.search(raw):
            if _SCHEME_SYS_RE.search(raw):
                floors["scheme"] = max(floors.get("scheme", 0.0), _SCHEME_FLOOR)
            if _WALLPAPER_SYS_RE.search(raw):
                floors["wallpaper"] = max(floors.get("wallpaper", 0.0), _WALLPAPER_FLOOR)
        return floors

    def _cue_kind_delta(self, cues: Dict[str, object], surface: str, raw: str) -> Tuple[float, List[str]]:
        """Cue-kind agreement adjustment for one candidate. Returns the
        score delta (a multiple of w_noun) plus evidence strings."""
        spec = self.spec_by_name.get(surface)
        if spec is None:  # presets/surfaces: no kind, no adjustment
            return 0.0, []
        kind = spec.kind
        delta = 0.0
        evidence: List[str] = []
        has_direction = "direction" in cues
        has_bool = cues.get("bool") in (True, False)
        has_position = "position" in cues
        has_transparency = bool(cues.get("transparency"))
        if has_transparency:
            if _TRANSPARENCY_TOOL_RE.search(spec.path) or any(
                "transparency" in g or "opacity" in g for g in spec.nouns
            ):
                delta += _K_TRANSPARENCY_AGREE
                evidence.append("see-through cue agrees with transparency setting")
            else:
                delta += _K_TRANSPARENCY_OTHER
        if has_direction and kind in ("float", "int"):
            delta += _K_DIRECTION_NUMERIC
            evidence.append("direction cue agrees with numeric setting")
        elif has_direction and kind not in ("float", "int"):
            delta += _K_DIRECTION_OTHER
        if has_bool and kind == "bool":
            delta += _K_BOOL_BOOL
            evidence.append("on/off cue agrees with toggle setting")
        elif has_bool and kind != "bool":
            delta += _K_BOOL_OTHER
        if has_position and kind == "enum":
            delta += _K_POSITION_ENUM
            evidence.append(f"position word agrees with enum setting ({cues['position']})")
        elif has_position and kind != "enum":
            delta += _K_POSITION_OTHER
        if kind == "enum":
            for word in self.enum_words.get(surface, ()):  # literal enum value present
                if re.search(rf"\b{re.escape(word)}\b", raw):
                    delta += _K_ENUM_WORD
                    evidence.append(f"enum value '{word}' present")
                    break
        if ("number" in cues or "percent" in cues) and kind in ("float", "int"):
            delta += _K_NUMBER_NUMERIC
            evidence.append("explicit number agrees with numeric setting")
        return delta, evidence

    # -- the main entry ------------------------------------------------------

    def route(self, text: str, state: RouterState = DEFAULT_STATE, k: int = 5) -> RouteResult:
        if not text or not text.strip():
            return RouteResult(verdict="ABSTAIN", candidates=[], question="say what you want to change")
        raw = text.lower().strip()

        # Query expansion (evidence collected for the candidate cards).
        expanded, evidence = _expand_query(raw)

        # Lexical: WEIGHTED dual BM25+ — the RAW query carries the user's
        # actual words (weight 0.7), the EXPANDED query carries typo fixes
        # and curated synonyms (weight 0.3). Synonyms are hints, never
        # replacements, so synonym flooding cannot drown the original
        # intent ("see-through panels" must not become a bar query just
        # because "panels" expands to bar/taskbar/panel).
        q_raw = tokenize(raw)
        q_tokens = tokenize(expanded)
        bm25_raw = {key: self.index.score(q_raw, key) for key in self.documents}
        bm25_exp = {key: self.index.score(q_tokens, key) for key in self.documents}
        raw_max = max(bm25_raw.values()) if bm25_raw else 0.0
        exp_max = max(bm25_exp.values()) if bm25_exp else 0.0

        # Semantic: PPMI cosine between expanded query and doc vectors.
        q_vec = self.embedder.embed(expanded)

        # Structural: noun hits on the EXPANDED text (the curated synonym
        # lexicon is the moral equivalent of extending the noun grammar —
        # "see-through" hits the transparency nouns once expanded),
        # pattern floors, cues, and atom COVERAGE (all of a compound
        # tool's name atoms present = specific addressing).
        noun_hits = set(_noun_hit(expanded))
        floors = self._pattern_floor(raw)
        cues = extract_cues(raw)
        expanded_stems = frozenset(tokenize(expanded))
        coverage_hits: Dict[str, float] = {}
        for key, atoms in self.name_atom_sets.items():
            if len(atoms) < 2:
                continue
            matched = sum(1 for atom in atoms if stem(atom) in expanded_stems or atom in expanded_stems)
            if matched >= 2:
                coverage_hits[key] = matched / len(atoms)

        w_lex, w_sem, w_fuzz, w_noun, bias = state.weights_vector()

        scored: List[Tuple[float, str]] = []
        features: Dict[str, Dict[str, float]] = {}
        for key, (doc, kind) in self.documents.items():
            lex_raw = (bm25_raw[key] / raw_max) if raw_max > 0 else 0.0
            lex_exp = (bm25_exp[key] / exp_max) if exp_max > 0 else 0.0
            lex = 0.7 * lex_raw + 0.3 * lex_exp
            sem = self.embedder.cosine(q_vec, self.doc_vectors[key])
            fuzz = ngram_similarity(raw, self.name_atoms.get(key, key))
            noun = 1.0 if key in noun_hits else 0.0
            score = w_lex * lex + w_sem * sem + w_fuzz * fuzz + w_noun * noun + bias
            if key in noun_hits:
                # A noun hit is decisive by construction: floor the hybrid
                # at a level vague lexical overlap cannot reach.
                score = max(score, w_lex + w_noun + bias)
            if key in floors:
                score = max(score, floors[key])
            # Atom coverage: 2+ of a compound tool's own name atoms present
            # is SPECIFIC addressing — full coverage is noun-hit-equivalent,
            # partial coverage (>= half) still earns a solid bonus. This is
            # what lets "performance show text" beat a generic "text" noun
            # hit on the font tool.
            coverage = coverage_hits.get(key, 0.0)
            if coverage >= 0.999:
                score = max(score, w_lex + w_noun + bias)
            elif coverage >= 0.5:
                score += 0.5 * w_noun
            cue_delta, cue_evidence = self._cue_kind_delta(cues, key, raw)
            score += cue_delta * w_noun
            scored.append((score, key))
            features[key] = {"lex": round(lex, 4), "sem": round(sem, 4),
                             "fuzz": round(fuzz, 4), "noun": noun,
                             "cue": round(cue_delta, 4),
                             "coverage": round(coverage, 4)}

        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        top_pairs = scored[:k]

        # Softmax with temperature over the top-k (probabilities are the
        # display + calibration surface; ranking is by raw score).
        temps = [s / state.temperature for s, _ in top_pairs]
        m = max(temps) if temps else 0.0
        exps = [pow(2.718281828459045, t - m) for t in temps]
        z = sum(exps) or 1.0

        candidates: List[Candidate] = []
        for (score, key), e in zip(top_pairs, exps):
            cand = Candidate(
                surface=key,
                kind=self.documents[key][1],
                score=round(score, 4),
                p=round(e / z, 4),
                cues=dict(cues),
            )
            cand.evidence.extend(evidence)
            if key in noun_hits:
                cand.evidence.append("exact noun grammar hit")
            if key in floors:
                cand.evidence.append("structural pattern hit")
            coverage = coverage_hits.get(key, 0.0)
            if coverage >= 0.999:
                cand.evidence.append("full name-atom coverage (specific addressing)")
            elif coverage >= 0.5:
                cand.evidence.append(f"name-atom coverage {coverage:.0%}")
            _delta, cue_evidence = self._cue_kind_delta(cues, key, raw)
            cand.evidence.extend(cue_evidence)
            for term in set(q_tokens):
                if term in self.index.doc_tokens.get(key, ()):
                    cand.evidence.append(f"matched '{term}'")
            candidates.append(cand)

        if not candidates:
            return RouteResult(verdict="ABSTAIN", candidates=[], question=_ABSTAIN_QUESTION)
        top_score = candidates[0].score
        margin = top_score - (candidates[1].score if len(candidates) > 1 else 0.0)

        if top_score < state.min_score:
            return RouteResult(
                verdict="ABSTAIN", candidates=candidates, question=_ABSTAIN_QUESTION,
                features=features,
            )
        if margin < state.min_margin and len(candidates) > 1:
            names = ", ".join(f"'{c.surface}'" for c in candidates[:3])
            return RouteResult(
                verdict="AMBIGUOUS", candidates=candidates,
                question=f"several settings could match: {names} — which one?",
                features=features,
            )
        return RouteResult(verdict="ROUTED", candidates=candidates, features=features)


_ABSTAIN_QUESTION = (
    "no setting clearly matches that phrasing; try naming the thing you "
    "want to change (bar, dock, corners, blur, animations, notifications...)"
)


# ---------------------------------------------------------------------------
# Process-wide singleton.
# ---------------------------------------------------------------------------

_ROUTER: Optional[Router] = None


def router() -> Router:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = Router()
    return _ROUTER


def route(text: str, state: RouterState = DEFAULT_STATE, k: int = 5) -> RouteResult:
    """Convenience one-shot routing (module-level, the common case)."""
    return router().route(text, state=state, k=k)
