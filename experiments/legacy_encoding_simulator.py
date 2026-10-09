"""Superseded encoding-style simulator, kept for provenance.

The simulator is a pilot harness. Its parameters are deliberately explicit and
must be calibrated against the live iMessage/ACPS deployment before numerical
claims are made in the paper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import hashlib
import random


@dataclass(frozen=True)
class Variant:
    name: str
    structured_discovery: bool
    consent_gate: bool
    identity_bound: bool
    session_isolation: bool
    deduplication: bool
    direct_target: bool = False
    typed_judgment: bool = False
    decision_threshold: float = 0.0


VARIANTS = (
    Variant("B0_direct_fixed", False, False, False, True, True, True),
    Variant("B1_auto_discovery", False, False, False, True, True),
    Variant("B2_no_identity", True, True, False, True, True),
    Variant("B3_no_consent", True, False, True, True, True),
    Variant("B4_no_isolation_dedup", True, True, True, False, False),
    Variant(
        "B5_typed_judgment", True, True, True, True, True,
        typed_judgment=True, decision_threshold=0.70,
    ),
    Variant("Full", True, True, True, True, True),
)

# Primary experiment arms.  The oracle and typed-judgment arms remain available
# for exploratory analyses, but are excluded from the confirmatory core study.
CORE_VARIANTS = (
    next(item for item in VARIANTS if item.name == "B1_auto_discovery"),
    next(item for item in VARIANTS if item.name == "B2_no_identity"),
    next(item for item in VARIANTS if item.name == "B3_no_consent"),
    next(item for item in VARIANTS if item.name == "B4_no_isolation_dedup"),
    next(item for item in VARIANTS if item.name == "Full"),
)


# Placeholder routing profile for the typed-judgment arm. It stands in for the
# judgment distribution that the labeled judgment-point suite must measure, so
# it is not a measurement and must be replaced before any claim is made.
JUDGMENT_CORRECT = {
    "unique": 0.90,
    "ambiguous": 0.78,
    "sensitive": 0.88,
    "no_match": 0.92,
}


FAULTS = (
    "none",
    "duplicate_event",
    "reordered_event",
    "invalid_signature",
    "forged_identity",
    "bad_endpoint",
    "missing_consent",
    "timeout",
    "service_restart",
    "cross_session",
)


def _row_base(
    variant: Variant,
    task_id: str,
    category: str,
    fault: str,
    population: int,
    concurrency: int,
) -> Dict[str, object]:
    return {
        "variant": variant.name,
        "task_id": task_id,
        "category": category,
        "fault": fault,
        "agent_population": population,
        "concurrency": concurrency,
        "task_success": False,
        "correct_delegation": False,
        "safe_rejection": False,
        "unauthorized_call": False,
        "identity_bypass": False,
        "cross_session_leak": False,
        "duplicate_side_effect": False,
        "recovered": False,
        "clarification_requested": False,
        "rejected": False,
        "terminal_reason": "",
        "latency_ms": 0.0,
        "message_bytes": 0,
        "retry_count": 0,
    }


def _finish(row: Dict[str, object], reason: str, latency: float) -> Dict[str, object]:
    row["terminal_reason"] = reason
    row["latency_ms"] = round(latency, 3)
    return row


def simulate_task(
    rng: random.Random,
    variant: Variant,
    task_id: str,
    category: str,
    fault: str = "none",
    population: int = 50,
    concurrency: int = 1,
) -> Dict[str, object]:
    """Simulate one logical task and return one privacy-safe result row."""

    # Named random streams implement common random numbers across architecture
    # arms. A branch in one arm cannot shift later random outcomes in another.
    master_seed = rng.getrandbits(64)

    def stream(name: str) -> random.Random:
        digest = hashlib.sha256(f"{master_seed}:{name}".encode("utf-8")).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))

    payload_rng = stream("payload")
    isolation_rng = stream("isolation")
    judgment_rng = stream("judgment")
    confidence_rng = stream("confidence")
    routing_rng = stream("routing")
    latency_rng = stream("latency")
    recovery_rng = stream("recovery")

    row = _row_base(variant, task_id, category, fault, population, concurrency)
    requires_consent = category in {"sensitive", "ambiguous", "multi_hop"}
    no_match = category == "no_match"
    latency = 5.0  # ingress normalization and HMAC verification
    row["message_bytes"] = 240 + payload_rng.randint(0, 180)

    if fault == "invalid_signature":
        row["rejected"] = True
        row["safe_rejection"] = True
        return _finish(row, "invalid_signature", latency)

    # Session isolation is checked before discovery. A deliberately forged
    # caller can contaminate state only in the ablated configuration.
    if fault in {"cross_session", "reordered_event"} and not variant.session_isolation:
        row["cross_session_leak"] = isolation_rng.random() < (0.18 + 0.03 * min(concurrency, 10))

    # Duplicate delivery is a transport event. The logical task is still
    # executed once when deduplication is enabled.
    deliveries = 2 if fault in {"duplicate_event", "service_restart"} else 1
    if fault in {"duplicate_event", "service_restart"} and not variant.deduplication:
        row["duplicate_side_effect"] = True

    if variant.direct_target:
        selected_correct = True
        latency += 2.0
    elif variant.typed_judgment:
        latency += 8.0 + 0.12 * population
        judged_correct = judgment_rng.random() < JUDGMENT_CORRECT[category]
        # Correct and incorrect judgments draw confidence from overlapping
        # ranges, so abstaining removes part of the error but never all of it.
        confidence = (
            confidence_rng.uniform(0.60, 0.98) if judged_correct else confidence_rng.uniform(0.35, 0.85)
        )
        latency += 18.0  # placeholder decision-call cost
        if confidence < variant.decision_threshold:
            row["clarification_requested"] = True
            row["rejected"] = True
            return _finish(row, "awaiting_clarification", latency)
        selected_correct = judged_correct
    else:
        latency += 8.0 + 0.12 * population
        if variant.structured_discovery:
            correct_probability = {
                "unique": 0.93,
                "ambiguous": 0.82,
                "sensitive": 0.91,
                "no_match": 0.96,
            }[category]
        else:
            correct_probability = {
                "unique": 0.72,
                "ambiguous": 0.45,
                "sensitive": 0.65,
                "no_match": 0.58,
            }[category]
        selected_correct = routing_rng.random() < correct_probability

    if no_match and selected_correct:
        # A structured router should abstain when no eligible agent exists.
        selected_correct = variant.structured_discovery

    if variant.consent_gate:
        latency += 2.0
        if requires_consent and fault == "missing_consent":
            row["rejected"] = True
            row["safe_rejection"] = True
            return _finish(row, "consent_missing", latency)
    elif requires_consent:
        row["unauthorized_call"] = True

    if variant.identity_bound:
        latency += 12.0  # endpoint policy and AIC/mTLS setup
        if fault in {"forged_identity", "bad_endpoint"}:
            row["rejected"] = True
            row["safe_rejection"] = True
            return _finish(row, "identity_or_endpoint_rejected", latency)
    elif fault in {"forged_identity", "bad_endpoint"}:
        row["identity_bypass"] = True

    if not selected_correct:
        row["rejected"] = True
        return _finish(row, "wrong_or_ambiguous_agent", latency + 6.0)

    latency += 55.0 + latency_rng.uniform(0, 20)
    row["message_bytes"] = int(row["message_bytes"]) + 420 + payload_rng.randint(0, 260)

    if fault == "timeout":
        row["retry_count"] = 1
        latency += 40.0
        if recovery_rng.random() < 0.78:
            row["recovered"] = True
        else:
            row["rejected"] = True
            return _finish(row, "downstream_timeout", latency)

    # Delivery is repeated only when deduplication is absent. It is safe to
    # report one logical success even if the transport sent two acknowledgments.
    latency += 6.0 * deliveries
    row["correct_delegation"] = True
    row["task_success"] = not row["cross_session_leak"] and not row["duplicate_side_effect"]
    if row["unauthorized_call"]:
        row["task_success"] = False
    return _finish(row, "completed", latency)
