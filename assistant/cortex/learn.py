"""The self-learning loop: routing weights fitted from user decisions.

This is the module that makes the cortex IMPROVE with use, with three
classical mechanisms and zero neural networks:

1. ONLINE LOGISTIC REGRESSION (AdaGrad) — every routed request whose
   outcome is observed (applied/approved = positive; rejected =
   negative; clarified = weak negative) becomes one training example
   over the router's own per-candidate features (lex/sem/fuzz/noun/cue
   agreement). AdaGrad (Duchi et al. 2011) per-coordinate adaptive
   learning rates suit the sparse, differently-scaled features. The
   fitted weights map back onto ``RouterState`` (normalized so the
   router's score scale stays comparable), which means the NEXT route
   is literally scored by what this user accepted and rejected before.

2. CALIBRATION — Beta-Binomial posterior over the router's softmax
   confidence vs. actual acceptance (the brain's calibrate.py idea,
   applied to routing). ``calibrated_confidence`` reports the posterior
   mean; the pipeline surfaces it as the honest probability instead of
   the raw softmax p.

3. STRATEGY BANDIT — a Thompson-sampling bandit (brain/preset_bandit's
   NamedBandit, reused verbatim) over three fixed RouterState profiles
   (lexical-heavy / semantic-heavy / balanced). Each query is routed
   with the sampled profile's weights; the outcome rewards the arm.
   The router learns not just how much to trust each signal overall,
   but which SIGNAL MIX this user's phrasing style responds to.

Drift: acceptance-rate changes across time buckets reuse the brain's
MinHash-free set-diff idea — here a plain rate comparison with a
threshold, reported (not acted on silently) so the user can decide to
reset learning.

Persistence: plain dict inside the brain state (same atomic-write
path); this module does no file I/O. Deterministic: seeded RNG only.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from ..brain.preset_bandit import NamedBandit
from .router import RouterState

LEARN_VERSION = 1
MAX_EXAMPLES = 500

# Feature order (must match the router's feature dict keys).
_FEATURES = ("lex", "sem", "fuzz", "noun", "cue")

# Fixed routing-strategy profiles for the bandit.
STRATEGY_PROFILES: Dict[str, RouterState] = {
    "lexical": RouterState(w_lex=0.55, w_sem=0.12, w_fuzz=0.10, w_noun=0.21, bias=0.02),
    "semantic": RouterState(w_lex=0.26, w_sem=0.42, w_fuzz=0.18, w_noun=0.12, bias=0.02),
    "balanced": RouterState(),  # the hand-set prior
}


# ---------------------------------------------------------------------------
# Online logistic regression (AdaGrad).
# ---------------------------------------------------------------------------


@dataclass
class OnlineLogistic:
    """5-feature logistic model with AdaGrad updates. Weights start at
    the identity prior (all 1.0 on the raw feature scale, bias 0) —
    i.e. "trust every signal equally until the user teaches otherwise"."""

    weights: Tuple[float, ...] = (1.0, 1.0, 1.0, 1.0, 1.0)
    bias: float = 0.0
    acc_sq: Tuple[float, ...] = (1e-6, 1e-6, 1e-6, 1e-6, 1e-6)
    bias_acc_sq: float = 1e-6
    lr: float = 0.15
    examples: int = 0

    def predict(self, features: Dict[str, float]) -> float:
        z = self.bias
        for i, name in enumerate(_FEATURES):
            z += self.weights[i] * float(features.get(name, 0.0))
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))

    def update(self, features: Dict[str, float], label: int) -> None:
        """One AdaGrad SGD step: per-coordinate adaptive step size
        ``lr / sqrt(accumulated_squared_gradients)``."""
        p = self.predict(features)
        error = (label - p)  # d/dz of log loss
        weights = list(self.weights)
        acc = list(self.acc_sq)
        for i, name in enumerate(_FEATURES):
            x = float(features.get(name, 0.0))
            grad = -error * x
            acc[i] += grad * grad
            weights[i] -= self.lr * grad / math.sqrt(acc[i])
        self.bias_acc_sq += (error * error)
        self.bias += self.lr * error / math.sqrt(self.bias_acc_sq)
        self.weights = tuple(weights)
        self.acc_sq = tuple(acc)
        self.examples += 1

    def to_dict(self) -> Dict[str, object]:
        return {"weights": list(self.weights), "bias": self.bias,
                "acc_sq": list(self.acc_sq), "bias_acc_sq": self.bias_acc_sq,
                "lr": self.lr, "examples": self.examples}

    @staticmethod
    def from_dict(data: Optional[Dict[str, object]]) -> "OnlineLogistic":
        model = OnlineLogistic()
        if not isinstance(data, dict):
            return model
        try:
            model.weights = tuple(float(w) for w in data.get("weights", model.weights))
            model.bias = float(data.get("bias", 0.0))
            model.acc_sq = tuple(float(a) for a in data.get("acc_sq", model.acc_sq))
            model.bias_acc_sq = float(data.get("bias_acc_sq", 1e-6))
            model.lr = float(data.get("lr", 0.15))
            model.examples = int(data.get("examples", 0))
        except (TypeError, ValueError):
            return OnlineLogistic()
        return model


# ---------------------------------------------------------------------------
# Calibration (Beta-Binomial over confidence buckets).
# ---------------------------------------------------------------------------


@dataclass
class Calibration:
    """Beta(a, b) posterior over P(accept | router said ROUTED). A flat
    prior (1, 1) plus observed outcomes; ``mean`` is the posterior mean
    a + b / (alpha + beta) — the honest confidence after evidence."""

    alpha: float = 1.0
    beta: float = 1.0
    buckets: Dict[str, Dict[str, float]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.buckets is None:
            self.buckets = {}

    def observe(self, accepted: bool, bucket: str = "all") -> None:
        self.alpha += 1.0 if accepted else 0.0
        self.beta += 0.0 if accepted else 1.0
        row = self.buckets.setdefault(bucket, {"alpha": 1.0, "beta": 1.0})
        row["alpha"] += 1.0 if accepted else 0.0
        row["beta"] += 0.0 if accepted else 1.0

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def bucket_mean(self, bucket: str) -> float:
        row = self.buckets.get(bucket) or {"alpha": 1.0, "beta": 1.0}
        return row["alpha"] / (row["alpha"] + row["beta"])

    def to_dict(self) -> Dict[str, object]:
        return {"alpha": self.alpha, "beta": self.beta, "buckets": self.buckets}

    @staticmethod
    def from_dict(data: Optional[Dict[str, object]]) -> "Calibration":
        cal = Calibration()
        if not isinstance(data, dict):
            return cal
        try:
            cal.alpha = float(data.get("alpha", 1.0))
            cal.beta = float(data.get("beta", 1.0))
            cal.buckets = {str(k): {kk: float(vv) for kk, vv in v.items()}
                           for k, v in (data.get("buckets") or {}).items()}
        except (TypeError, ValueError):
            return Calibration()
        return cal


def confidence_bucket(p: float) -> str:
    """Softmax-probability bucket used as the calibration key."""
    if p >= 0.75:
        return "p75+"
    if p >= 0.5:
        return "p50-75"
    if p >= 0.3:
        return "p30-50"
    return "p30-"


# ---------------------------------------------------------------------------
# The learner (facade over model + calibration + bandit + example log).
# ---------------------------------------------------------------------------


class CortexLearner:
    """Stateful learner, persisted as ONE plain dict by the caller:

    ``{"version": 1, "model": {...}, "calibration": {...},
       "bandit": {...}, "examples": [...], "drift": {...}}``

    ``examples`` is a bounded append-log of (features, label, surface)
    rows — kept so learning is auditable and replayable, the same
    honesty rule as the brain ledger."""

    def __init__(self, data: Optional[Dict[str, object]] = None) -> None:
        data = data if isinstance(data, dict) else {}
        self.model = OnlineLogistic.from_dict(data.get("model"))  # type: ignore[arg-type]
        self.calibration = Calibration.from_dict(data.get("calibration"))  # type: ignore[arg-type]
        self.bandit = NamedBandit.from_dict(data.get("bandit"))  # type: ignore[arg-type]
        raw_examples = data.get("examples") or []
        self.examples: List[Dict[str, object]] = [
            dict(row) for row in raw_examples if isinstance(row, dict)
        ][:MAX_EXAMPLES]
        self.accepts = int(data.get("accepts", 0)) or sum(  # type: ignore[arg-type]
            1 for row in self.examples if row.get("label") == 1
        )
        self.rejects = int(data.get("rejects", 0)) or sum(
            1 for row in self.examples if row.get("label") == 0
        )
        self._rng = random.Random(0xC0E7E)  # seeded: strategy choice is reproducible

    # -- learning ----------------------------------------------------------

    def choose_strategy(self) -> Tuple[str, RouterState]:
        """Thompson-sample a routing strategy. Returns (name, state)."""
        ranked = self.bandit.rank(list(STRATEGY_PROFILES), rng=self._rng)
        name = ranked[0][0] if ranked else "balanced"
        return name, STRATEGY_PROFILES.get(name, RouterState())

    def observe(self, text: str, surface: str, features: Dict[str, float],
                p: float, outcome: str) -> None:
        """Record one routed outcome and learn from it. Outcome mapping:
        applied/approved -> label 1; rejected -> label 0; clarified and
        abstain -> weak negative 0 (with weight reflected only in the
        calibration, not the model — ambiguous phrasings are not the
        model's fault)."""
        if outcome in ("applied", "approved"):
            label = 1
        elif outcome == "rejected":
            label = 0
        elif outcome in ("clarified", "abstain"):
            label = 0
        elif outcome == "ambiguous":
            self.calibration.observe(False, confidence_bucket(p))
            return
        else:
            return
        self.model.update(features, label)
        self.calibration.observe(label == 1, confidence_bucket(p))
        if label == 1:
            self.accepts += 1
        else:
            self.rejects += 1
        self.examples.append({"text": text[:120], "surface": surface,
                              "features": {k: round(float(v), 4) for k, v in features.items()},
                              "p": round(float(p), 4), "label": label,
                              "outcome": outcome})
        if len(self.examples) > MAX_EXAMPLES:
            self.examples = self.examples[-MAX_EXAMPLES:]

    def reward_strategy(self, name: str, accepted: bool) -> None:
        self.bandit.reward(name, accepted)

    def calibrated_confidence(self, p: float) -> float:
        """Posterior-mean acceptance probability for this softmax band —
        the honest confidence the pipeline reports."""
        return round(self.calibration.bucket_mean(confidence_bucket(p)), 3)

    # -- router-state adaptation -------------------------------------------

    def router_state(self) -> RouterState:
        """The learned RouterState: the sampled strategy profile's
        weights rescaled by the fitted logistic weights (normalized to
        keep the score scale stable). Falls back to the strategy profile
        alone until the model has seen enough evidence to mean anything
        (>= 12 examples)."""
        _name, base = self.choose_strategy()
        if self.model.examples < 12:
            return base
        fitted = [max(0.0, w) for w in self.model.weights]  # negative weights are uninterpretable here
        total = sum(fitted)
        if total <= 0:
            return base
        fitted = [w / total for w in fitted]
        # map [lex, sem, fuzz, noun, cue-kind handled via w_noun] onto the
        # RouterState weight slots; 'cue' folds into w_noun (both are the
        # structural/agreement signals).
        w_lex = fitted[0]
        w_sem = fitted[1]
        w_fuzz = fitted[2]
        w_noun = fitted[3] + fitted[4]
        # renormalize the four slots to the strategy profile's total mass
        mass = base.w_lex + base.w_sem + base.w_fuzz + base.w_noun
        slot_total = w_lex + w_sem + w_fuzz + w_noun
        if slot_total <= 0:
            return base
        scale = mass / slot_total
        return RouterState(
            w_lex=round(w_lex * scale, 4), w_sem=round(w_sem * scale, 4),
            w_fuzz=round(w_fuzz * scale, 4), w_noun=round(w_noun * scale, 4),
            bias=base.bias, min_score=base.min_score,
            min_margin=base.min_margin, temperature=base.temperature,
        )

    # -- drift ---------------------------------------------------------------

    def drift_check(self) -> Dict[str, object]:
        """Acceptance-rate drift across example halves (old vs new). A
        report, not an action: the CLI surfaces it; only the user resets."""
        if len(self.examples) < 10:
            return {"status": "insufficient-data", "examples": len(self.examples)}
        half = len(self.examples) // 2
        old = self.examples[:half]
        new = self.examples[half:]
        rate_old = sum(1 for r in old if r.get("label") == 1) / len(old)
        rate_new = sum(1 for r in new if r.get("label") == 1) / len(new)
        delta = rate_new - rate_old
        status = "stable"
        if abs(delta) >= 0.25:
            status = "drift-detected"
        return {"status": status, "old_rate": round(rate_old, 3),
                "new_rate": round(rate_new, 3), "delta": round(delta, 3),
                "examples": len(self.examples)}

    # -- persistence ----------------------------------------------------------

    def to_dict(self) -> Dict[str, object]:
        return {
            "version": LEARN_VERSION,
            "model": self.model.to_dict(),
            "calibration": self.calibration.to_dict(),
            "bandit": self.bandit.to_dict(),
            "examples": self.examples,
            "accepts": self.accepts,
            "rejects": self.rejects,
        }

    # -- reporting ----------------------------------------------------------

    def report(self) -> Dict[str, object]:
        return {
            "examples": len(self.examples),
            "accepts": self.accepts,
            "rejects": self.rejects,
            "acceptance_rate": round(self.accepts / max(1, self.accepts + self.rejects), 3),
            "calibration": {
                "overall": round(self.calibration.mean, 3),
                "buckets": {b: round(self.calibration.bucket_mean(b), 3)
                            for b in ("p75+", "p50-75", "p30-50", "p30-")},
            },
            "strategy_arms": {
                name: {
                    "mean": round(alpha / (alpha + beta), 3),
                    "draws": int(alpha + beta - 2),  # observations beyond the flat prior
                }
                for name, (alpha, beta) in sorted(self.bandit.arms.items())
            },
            "drift": self.drift_check(),
            "fitted_weights": {
                name: round(w, 4) for name, w in zip(_FEATURES, self.model.weights)
            },
        }


# ---------------------------------------------------------------------------
# Batch-curated active learning (issue #120 Phase 4.3): near-threshold
# phrases are LOGGED for batch review instead of being learned silently.
#
# The router's own cutoffs live in RouterState (router.py): min_score
# (default 0.30) gates ABSTAIN and min_margin (default 0.06) gates
# AMBIGUOUS. A phrase that falls below either is exactly the evidence an
# active learner wants — but learning from it online would silently bend
# the router toward phrases nobody confirmed. So the candidate is parked
# in the state dict (key "cortex_review", bounded), and `cortex review`
# surfaces the batch for the user to label (teaching outcome "applied"
# for the named surface) or dismiss. Nothing here routes, writes, or
# learns by itself: pure list/dict transforms over caller-owned state.
# ---------------------------------------------------------------------------

REVIEW_KEY = "cortex_review"
MAX_CANDIDATES = 50


def log_review_candidate(bucket: List[Dict[str, object]], text: str,
                         verdict: str, candidates: List[Dict[str, object]],
                         at: str) -> List[Dict[str, object]]:
    """Append one near-threshold phrase to the review bucket (pure).

    ``bucket`` is the caller's list (state[REVIEW_KEY]); identical texts
    are deduplicated (the newest occurrence wins). Bounded at
    MAX_CANDIDATES, oldest evicted.
    """
    if verdict not in ("ABSTAIN", "AMBIGUOUS"):
        return bucket
    top = candidates[0] if candidates else None
    entry: Dict[str, object] = {
        "text": text[:120],
        "verdict": verdict,
        "surface": top.get("surface") if top else None,
        "p": top.get("p") if top else None,
        "at": at,
    }
    kept = [c for c in bucket if c.get("text") != entry["text"]]
    kept.insert(0, entry)
    return kept[:MAX_CANDIDATES]


def is_near_threshold(verdict: str) -> bool:
    """The verdicts that mark a near-threshold phrase (router.py's own
    ABSTAIN/AMBIGUOUS gates: below min_score or below min_margin)."""
    return verdict in ("ABSTAIN", "AMBIGUOUS")


def label_candidate(state: Dict[str, object], index: int, surface: str,
                    learner: "CortexLearner") -> Dict[str, object]:
    """Teach the router one reviewed phrase: text -> surface.

    The features come from a fresh route of the text (deterministic); if
    the router currently maps the phrase to a different surface, the
    labeled surface gets an empty feature vector — the update still moves
    the bias honestly instead of inventing agreement. The labeled
    candidate is REMOVED from the bucket (it is no longer outstanding).
    """
    from .router import route as _route

    bucket = list(state.get(REVIEW_KEY, []))
    if index < 0 or index >= len(bucket):
        raise ValueError(f"no review candidate {index} (0..{len(bucket) - 1})")
    entry = bucket.pop(index)
    text = str(entry["text"])
    fresh = _route(text)
    top = fresh.top
    if top is not None and top.surface == surface and top.p is not None:
        p = float(top.p)
    else:
        p = float(entry.get("p") or 0.0)
    features = fresh.features.get(surface, {})
    learner.observe(text, surface, features, p, "applied")
    state[REVIEW_KEY] = bucket
    return {"labeled": True, "text": text, "surface": surface,
            "remaining": len(bucket)}


def dismiss_candidate(state: Dict[str, object], index: int) -> Dict[str, object]:
    """Drop one candidate from the bucket without teaching anything."""
    bucket = list(state.get(REVIEW_KEY, []))
    if index < 0 or index >= len(bucket):
        raise ValueError(f"no review candidate {index} (0..{len(bucket) - 1})")
    removed = bucket.pop(index)
    state[REVIEW_KEY] = bucket
    return {"dismissed": True, "text": str(removed["text"]),
            "remaining": len(bucket)}
