"""Auto-merge decision layer.

The pipeline can already scan -> plan -> fix -> run the 19 gates. This module
decides whether a passing change is safe to merge automatically, or must be
routed to a human. The safety philosophy is escalate-when-unsure: anything that
is not plainly low-risk goes to a human.

Task 2 lives here: risk_level(). Later tasks add the full eligibility decision
(gate results + tier + risk -> AUTO / HUMAN) on top of this.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AutoMergePolicy:
    """The rules that decide whether a change may auto-merge.

    Frozen so the safety rails cannot be loosened by a stray assignment. The
    default is deliberately the safest possible: auto-merge OFF, and even when a
    client turns it on it stays limited to T1 copy edits that pass every gate.

    - enabled: opt-in per client. Never auto-merges until explicitly switched on.
    - allowed_tiers: only these tiers may auto-merge (T1 = plain copy edits).
    - require_all_gates_pass: every gate must be green; one failure => human.
    """

    enabled: bool = False
    allowed_tiers: frozenset[str] = field(default_factory=lambda: frozenset({"T1"}))
    require_all_gates_pass: bool = True


# The fleet-wide default. A client repo opts in by constructing its own policy
# with enabled=True; nothing auto-merges under this default.
DEFAULT_POLICY = AutoMergePolicy()

# YMYL ("Your Money or Your Life") terms. A change whose text touches medical or
# legal claims must never auto-merge, regardless of tier — the cost of a wrong
# automated edit here is far higher than the cost of a human glance. The list is
# deliberately broad; a false "high" only means an extra human review, which is
# the safe direction.
YMYL_TERMS: frozenset[str] = frozenset(
    {
        # medical
        "diagnosis", "diagnose", "treatment", "treat", "cure", "cures",
        "prescription", "dosage", "symptom", "disease", "medication",
        "surgery", "medical", "clinical", "patient", "therapy", "vaccine",
        # legal / financial (YMYL)
        "legal advice", "attorney", "lawsuit", "guarantee", "refund",
        "investment", "loan", "insurance",
    }
)


@dataclass(frozen=True)
class Decision:
    """The outcome of the eligibility check."""

    action: str  # "AUTO" or "HUMAN"
    reason: str


def decide(
    gate_results: dict[str, bool],
    tier: str,
    creates: list[str],
    text: str,
    policy: AutoMergePolicy = DEFAULT_POLICY,
) -> Decision:
    """Return AUTO (merge without a human) or HUMAN (route to review), + reason.

    Escalate-when-unsure order: an off switch, a failing/absent gate, a
    disallowed tier, or a high-risk change each force HUMAN. Only an
    all-green, low-risk, allowed-tier change reaches AUTO.
    """
    if not policy.enabled:
        return Decision("HUMAN", "auto-merge disabled for this client")

    if policy.require_all_gates_pass:
        if not gate_results:
            return Decision("HUMAN", "no gate results — nothing was verified")
        failed = sorted(name for name, passed in gate_results.items() if not passed)
        if failed:
            return Decision("HUMAN", f"gate(s) failed: {', '.join(failed)}")

    if tier not in policy.allowed_tiers:
        return Decision("HUMAN", f"tier {tier or '(none)'} not eligible for auto-merge")

    if risk_level(tier, creates, text) == "high":
        return Decision("HUMAN", "high-risk change (new page or medical/legal claim)")

    return Decision("AUTO", "all gates green, low-risk T1 change")


def risk_level(tier: str, creates: list[str], text: str) -> str:
    """Return "high" (escalate to a human) or "low" (eligible for auto-merge).

    high when ANY of:
      - no tier declared, or tier is T2/T3 (only T1 copy edits may automate),
      - the change creates a file (a new page/route),
      - the changed text touches a medical/legal (YMYL) claim.
    low otherwise.
    """
    normalized_tier = (tier or "").strip().upper()
    if normalized_tier != "T1":
        return "high"
    if creates:
        return "high"
    lowered = text.lower()
    if any(term in lowered for term in YMYL_TERMS):
        return "high"
    return "low"
