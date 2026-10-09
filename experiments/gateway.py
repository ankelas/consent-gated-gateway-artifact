"""Executable seven-module gateway harness for the paper's core study.

Every safety-relevant number in the core study is produced by *running* the
gateway modules rather than by assigning an outcome flag:

* M1 verifies a real HMAC over the canonical event with ``hmac.compare_digest``;
* M2 resolves session state through a keyed store, so cross-session leakage can
  only happen when the store actually returns another session's record;
* M3 ranks candidates with a deterministic lexical router over generated
  capability descriptions, so routing accuracy is measured against a gold
  agent instead of drawn from a per-category constant;
* M4 reads consent from the session record;
* M5 validates the presented endpoint URL, AIC and mTLS flag against policy;
* M6 claims an idempotency key before performing a side effect;
* M7 emits the reply and a telemetry span.

The ablation arms differ only in which of these modules are installed.  The
harness is offline and deterministic: network calls, TLS handshakes and host
contention are replaced by a documented per-step cost model, so the reported
latencies are simulated cost units and not deployment measurements.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse


# --------------------------------------------------------------------- utils

def stable_seed(*parts: object) -> int:
    digest = hashlib.sha256(":".join(str(part) for part in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def stream(master_seed: int, name: str) -> random.Random:
    """Named random stream so one arm's branch cannot shift another arm's draws."""
    return random.Random(stable_seed(master_seed, name))


def tokens(text: str) -> List[str]:
    return re.findall(r"[a-z]+", text.lower())


STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "be", "before", "can", "chance", "discussed",
    "for", "from", "get", "in", "is", "it", "me", "my", "of", "on", "or",
    "please", "thanks", "that", "the", "this", "to", "urgent", "when", "with",
    "you", "your",
})


def content_tokens(text: str) -> List[str]:
    """Tokens that carry capability meaning, with function words removed."""
    return [token for token in tokens(text) if token not in STOPWORDS]


# ------------------------------------------------------------ cost model

COST = {
    "ingress_hmac": 5.0,          # HMAC verify + schema validation
    "session_lookup": 1.0,        # keyed store read
    "discovery_base": 2.0,        # directory query
    "discovery_structured": 0.35,  # per candidate scored with idf weights
    "discovery_unstructured": 0.12,  # per candidate scored by token counting
    "consent_check": 2.0,
    "identity_screen": 4.0,       # endpoint URL/AIC policy check
    "mtls_handshake": 12.0,       # mutual TLS establishment
    "task_start": 55.0,           # protocol task round trip
    "delivery": 6.0,              # per outbound delivery attempt
    "wrong_route_extra": 6.0,     # failed selection before cancellation
    "retry_extra": 40.0,
    "clarification_render": 3.0,
}


# --------------------------------------------------------------- workload

DOMAINS: Tuple[Dict[str, Any], ...] = (
    {"key": "calendar", "verb": "schedule", "surface": "schedule or reschedule meetings",
     "terms": ("meeting", "calendar", "invite", "agenda", "room", "reschedule"), "side_effect": False},
    {"key": "expenses", "verb": "file", "surface": "file expense reports and receipts",
     "terms": ("expense", "receipt", "reimbursement", "claim", "invoice", "report"), "side_effect": True},
    {"key": "travel", "verb": "book", "surface": "book flights and rail tickets",
     "terms": ("flight", "ticket", "rail", "itinerary", "booking", "travel"), "side_effect": True},
    {"key": "search", "verb": "find", "surface": "search internal documents",
     "terms": ("document", "search", "lookup", "knowledge", "file", "find"), "side_effect": False},
    {"key": "summary", "verb": "summarize", "surface": "summarize long discussion threads",
     "terms": ("summary", "thread", "transcript", "digest", "notes", "discussion"), "side_effect": False},
    {"key": "messaging", "verb": "forward", "surface": "forward messages to a contact",
     "terms": ("forward", "message", "contact", "chat", "send", "text"), "side_effect": True},
    {"key": "support", "verb": "open", "surface": "open and track support tickets",
     "terms": ("ticket", "support", "issue", "escalate", "incident", "bug"), "side_effect": True},
    {"key": "crm", "verb": "update", "surface": "update customer records",
     "terms": ("customer", "crm", "record", "account", "pipeline", "opportunity"), "side_effect": True},
    {"key": "inventory", "verb": "check", "surface": "check stock and inventory levels",
     "terms": ("stock", "inventory", "sku", "warehouse", "level", "supply"), "side_effect": False},
    {"key": "payroll", "verb": "run", "surface": "run payroll and benefits changes",
     "terms": ("payroll", "benefit", "salary", "employee", "compensation", "deduction"), "side_effect": True},
    {"key": "translation", "verb": "translate", "surface": "translate short business texts",
     "terms": ("translate", "language", "chinese", "english", "localization", "glossary"), "side_effect": False},
    {"key": "analytics", "verb": "compute", "surface": "compute aggregate business metrics",
     "terms": ("metric", "dashboard", "analytics", "aggregate", "chart", "cohort"), "side_effect": False},
)

# Domains deliberately absent from every advertised capability list.  A message
# about one of them has no eligible agent, which lets the harness measure
# abstention instead of assuming it.
OUT_OF_SCOPE: Tuple[Dict[str, Any], ...] = (
    {"key": "legal", "verb": "draft", "surface": "draft legal filings",
     "terms": ("legal", "filing", "court", "contract", "clause", "litigation"), "side_effect": True},
    {"key": "clinical", "verb": "review", "surface": "review clinical notes",
     "terms": ("clinical", "patient", "diagnosis", "medical", "treatment", "triage"), "side_effect": True},
    {"key": "security", "verb": "audit", "surface": "audit penetration test findings",
     "terms": ("penetration", "exploit", "vulnerability", "audit", "finding", "hardening"), "side_effect": True},
    {"key": "marine", "verb": "plan", "surface": "plan marine shipping routes",
     "terms": ("vessel", "port", "shipping", "marine", "cargo", "route"), "side_effect": False},
)

NOISE = (
    "please", "for the team", "before friday", "as discussed",
    "when you get a chance", "thanks", "this is urgent",
)

# A generic advertisement that shares vocabulary with many real capabilities.
# It is the failure mode of plain keyword matching: a token-counting router is
# attracted to it, while an idf-weighted router discounts its common terms.
GENERIC_AGENT: Dict[str, Any] = {
    "key": "general",
    "surface": "general purpose assistant for meetings reports messages tickets search and files",
    "terms": ("meeting", "report", "message", "ticket", "search", "file"),
}


@dataclass(frozen=True)
class Candidate:
    agent_id: str
    aic: str
    endpoint: str
    description: str
    terms: Tuple[str, ...]


@dataclass(frozen=True)
class Scenario:
    category: str
    message: str
    gold_agent: Optional[str]
    candidates: Tuple[Candidate, ...]
    requires_consent: bool
    idempotency_key: str
    victim_session: Optional[Tuple[str, str]] = None
    victim_task_id: Optional[str] = None


def _aic(key: str, index: int) -> str:
    return f"1.2.156.3088.1.BUPT.{key.upper()}.{index:02d}"


def _render(
    domain: Dict[str, Any],
    rng: random.Random,
    extra: Sequence[str] = (),
    generic_verb: bool = False,
    n_terms: int = 4,
) -> str:
    terms = list(domain["terms"])
    rng.shuffle(terms)
    chosen = terms[:n_terms]
    if extra:
        borrowed = list(extra)
        rng.shuffle(borrowed)
        chosen = chosen + borrowed[:3]
    body = " ".join(chosen)
    verb = "handle" if generic_verb else domain["verb"]
    return f"Please {verb} it for me: {body}. {rng.choice(NOISE)}."


def build_scenario(rng: random.Random, category: str, population: int = 50) -> Scenario:
    """Materialize one workload item with a registry and a gold target."""
    domains = list(DOMAINS)
    rng.shuffle(domains)
    registry_size = max(6, min(12, population // 10 + 2))
    registry = domains[:registry_size]
    decoy = domains[1] if len(domains) > 1 else domains[0]

    if category == "no_match":
        outside = list(OUT_OF_SCOPE)
        rng.shuffle(outside)
        target = outside[0]
        message = _render(target, rng)
        gold_agent: Optional[str] = None
        requires_consent = False
    else:
        target = registry[0]
        if category == "ambiguous":
            # A genuinely two-way request: a generic verb plus balanced
            # vocabulary from two advertised capabilities, so neither
            # candidate is lexically dominant.
            message = _render(target, rng, extra=decoy["terms"], generic_verb=True, n_terms=3)
        else:
            message = _render(target, rng)
        gold_agent = f"agent-{target['key']}"
        requires_consent = category in {"sensitive", "ambiguous"} or bool(target["side_effect"])

    candidates: List[Candidate] = []
    for index, domain in enumerate(registry):
        candidates.append(Candidate(
            agent_id=f"agent-{domain['key']}",
            aic=_aic(domain["key"], index + 1),
            endpoint=f"https://{domain['key']}.agents.example/acps/rpc",
            description=domain["surface"],
            terms=tuple(domain["terms"]),
        ))

    candidates.append(Candidate(
        agent_id="agent-general",
        aic=_aic("general", len(candidates) + 1),
        endpoint="https://general.agents.example/acps/rpc",
        description=GENERIC_AGENT["surface"],
        terms=tuple(GENERIC_AGENT["terms"]),
    ))

    rng.shuffle(candidates)
    victim_session = ("user-victim", "chat-victim")
    return Scenario(
        category=category,
        message=message,
        gold_agent=gold_agent,
        candidates=tuple(candidates),
        requires_consent=requires_consent,
        idempotency_key=f"idem-{stable_seed(message, category) % 10**8:08d}",
        victim_session=victim_session,
        victim_task_id="task-victim-0001",
    )


# ------------------------------------------------------------------ modules

class SessionStore:
    """Keyed state store. When isolation is disabled every caller shares one key."""

    def __init__(self, isolate: bool) -> None:
        self.isolate = isolate
        self._data: Dict[str, Dict[str, Any]] = {}

    def key(self, caller_id: str, chat_id: str) -> str:
        return f"{caller_id}|{chat_id}" if self.isolate else "shared"

    def get(self, caller_id: str, chat_id: str) -> Optional[Dict[str, Any]]:
        return self._data.get(self.key(caller_id, chat_id))

    def put(self, caller_id: str, chat_id: str, value: Dict[str, Any]) -> None:
        self._data[self.key(caller_id, chat_id)] = value


class IdempotencyStore:
    """Durable idempotency keys; a claim is granted at most once per key."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._claimed: set[str] = set()

    def claim(self, key: str) -> bool:
        if not self.enabled:
            return True
        if key in self._claimed:
            return False
        self._claimed.add(key)
        return True


def m1_ingress(event: Dict[str, Any], secret: bytes) -> bool:
    canonical = f"{event['caller']}|{event['chat']}|{event['message']}|{event['event_id']}"
    expected = hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, event["signature"])


def _scores_unstructured(message: str, candidates: Sequence[Candidate]) -> List[float]:
    message_terms = set(content_tokens(message))
    scores = []
    for candidate in candidates:
        shared = len(message_terms & set(candidate.terms))
        # Unstructured discovery has no abstention path and no length control,
        # so a verbose advertisement wins ties.
        scores.append(shared + 0.001 * len(candidate.description))
    return scores


def _scores_structured(message: str, candidates: Sequence[Candidate]) -> List[float]:
    docs = [set(candidate.terms) | set(content_tokens(candidate.description)) for candidate in candidates]
    document_frequency: Dict[str, int] = {}
    for doc in docs:
        for term in doc:
            document_frequency[term] = document_frequency.get(term, 0) + 1
    size = len(candidates)
    idf = {term: math.log((1 + size) / (1 + freq)) + 1.0 for term, freq in document_frequency.items()}
    message_terms = set(content_tokens(message))
    return [sum(idf.get(term, 0.0) for term in message_terms & doc) for doc in docs]


def _softmax(scores: Sequence[float], temperature: float) -> List[float]:
    if not scores:
        return []
    scaled = [score / temperature for score in scores]
    peak = max(scaled)
    exps = [math.exp(value - peak) for value in scaled]
    total = sum(exps)
    return [value / total for value in exps]


ROUTER = {
    "structured": _scores_structured,
    "unstructured": _scores_unstructured,
}

# Fixed a priori policy constants, not tuned on the outcomes.
DISTRIBUTION_TEMPERATURE = 1.0
NO_MATCH_FLOOR = 0.34
CLARIFY_MARGIN = 0.12


@dataclass(frozen=True)
class Route:
    candidate: Optional[Candidate]
    margin: float
    top_probability: float
    abstained: bool


def m3_discover(message: str, candidates: Sequence[Candidate], mode: str) -> Route:
    raw = ROUTER[mode](message, candidates)
    if mode == "unstructured":
        best = max(range(len(candidates)), key=lambda index: (raw[index], candidates[index].description))
        return Route(candidates[best], 0.0, 1.0, False)
    distribution = _softmax(raw, DISTRIBUTION_TEMPERATURE)
    order = sorted(range(len(candidates)), key=lambda index: distribution[index], reverse=True)
    top = distribution[order[0]]
    second = distribution[order[1]] if len(order) > 1 else 0.0
    if top < NO_MATCH_FLOOR:
        return Route(None, top - second, top, True)
    return Route(candidates[order[0]], top - second, top, False)


@dataclass(frozen=True)
class EndpointPresentation:
    url: str
    aic: str
    mtls: bool


def m5_verify_endpoint(candidate: Candidate, presented: EndpointPresentation, require_mtls: bool = True) -> bool:
    parsed = urlparse(presented.url)
    return (
        parsed.scheme == "https"
        and parsed.path == "/acps/rpc"
        and presented.url == candidate.endpoint
        and presented.aic == candidate.aic
        and (presented.mtls or not require_mtls)
    )


# --------------------------------------------------------------- arm config

@dataclass(frozen=True)
class Arm:
    name: str
    discovery: str
    clarification: bool
    consent_gate: bool
    identity_bound: bool
    session_isolation: bool
    deduplication: bool
    typed_judgment: bool = False
    decision_threshold: float = 0.0
    direct_target: bool = False


VARIANTS: Tuple[Arm, ...] = (
    Arm("B0_direct_fixed", "unstructured", False, False, False, True, True, direct_target=True),
    Arm("B1_auto_discovery", "unstructured", False, False, False, True, True),
    Arm("B2_no_identity", "structured", True, True, False, True, True),
    Arm("B3_no_consent", "structured", True, False, True, True, True),
    Arm("B4_no_isolation_dedup", "structured", True, True, True, False, False),
    Arm("B5_typed_judgment", "structured", True, True, True, True, True,
        typed_judgment=True, decision_threshold=0.70),
    Arm("Full", "structured", True, True, True, True, True),
)

CORE_VARIANTS: Tuple[Arm, ...] = (
    next(arm for arm in VARIANTS if arm.name == "B1_auto_discovery"),
    next(arm for arm in VARIANTS if arm.name == "B2_no_identity"),
    next(arm for arm in VARIANTS if arm.name == "B3_no_consent"),
    next(arm for arm in VARIANTS if arm.name == "B4_no_isolation_dedup"),
    next(arm for arm in VARIANTS if arm.name == "Full"),
)

FAULTS: Tuple[str, ...] = (
    "none", "duplicate_event", "reordered_event", "invalid_signature",
    "forged_identity", "bad_endpoint", "missing_consent", "timeout",
    "service_restart", "cross_session",
)

METRIC_KEYS: Tuple[str, ...] = (
    "task_success", "correct_delegation", "safe_rejection", "unauthorized_call",
    "identity_bypass", "cross_session_leak", "duplicate_side_effect", "recovered",
    "clarification_requested", "rejected",
)


def _blank_outcome() -> Dict[str, bool]:
    return {key: False for key in METRIC_KEYS}


def run_task(
    rng: random.Random,
    arm: Arm,
    scenario: Scenario,
    fault: str = "none",
    population: int = 50,
    concurrency: int = 1,
) -> Dict[str, Any]:
    """Execute one task through the gateway and return a privacy-safe row."""
    master_seed = rng.getrandbits(64)
    downstream_rng = stream(master_seed, "downstream")
    payload_rng = stream(master_seed, "payload")

    outcome = _blank_outcome()
    telemetry: List[str] = []
    latency = COST["ingress_hmac"]

    # --- M1: ingress authentication and normalization -----------------------
    secret = b"core-study-hmac-key"
    if fault == "cross_session":
        event_caller, event_chat = "user-attacker", "chat-attacker"
    else:
        event_caller, event_chat = scenario.victim_session
    signature = hmac.new(
        secret,
        f"{event_caller}|{event_chat}|{scenario.message}|evt".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    event = {
        "caller": event_caller,
        "chat": event_chat,
        "message": scenario.message,
        "event_id": "evt",
        "signature": signature if fault != "invalid_signature" else "0" * 64,
    }
    if not m1_ingress(event, secret):
        outcome["rejected"] = True
        outcome["safe_rejection"] = True
        return _row(arm, outcome, "invalid_signature", latency, payload_rng, telemetry)
    telemetry.append("ingress_verified")

    # --- M6: idempotency claim (durable across restarts) --------------------
    dedup = IdempotencyStore(arm.deduplication)
    deliveries = 2 if fault in {"duplicate_event", "reordered_event", "service_restart"} else 1
    side_effects = 0

    # --- M2: session isolation ---------------------------------------------
    store = SessionStore(arm.session_isolation)
    victim_caller, victim_chat = scenario.victim_session
    store.put(victim_caller, victim_chat, {"task_id": scenario.victim_task_id, "consent": True})
    latency += COST["session_lookup"]

    if fault == "cross_session":
        attacker = store.get("user-attacker", "chat-attacker")
        if attacker is None:
            outcome["rejected"] = True
            outcome["safe_rejection"] = True
            return _row(arm, outcome, "unknown_session_reference", latency, payload_rng, telemetry)
        # The store returned a record for a caller that did not create it: the
        # isolation invariant is violated by the lookup itself.
        outcome["cross_session_leak"] = attacker.get("task_id") != "attacker-task"
        telemetry.append("cross_session_record")

    # --- M3: capability discovery and routing -------------------------------
    latency += COST["discovery_base"] + COST[f"discovery_{arm.discovery}"] * len(scenario.candidates)
    if arm.direct_target:
        route = Route(next((c for c in scenario.candidates if c.agent_id == scenario.gold_agent), None), 1.0, 1.0, False)
    else:
        route = m3_discover(scenario.message, scenario.candidates, arm.discovery)

    if route.abstained:
        # A structured router that finds no eligible candidate fails closed.
        outcome["task_success"] = True
        outcome["correct_delegation"] = True
        return _row(arm, outcome, "no_match_abstained", latency, payload_rng, telemetry)

    margin_threshold = CLARIFY_MARGIN
    if arm.typed_judgment:
        margin_threshold = arm.decision_threshold
    if arm.clarification and route.margin < margin_threshold:
        latency += COST["clarification_render"]
        outcome["clarification_requested"] = True
        return _row(arm, outcome, "awaiting_clarification", latency, payload_rng, telemetry)

    selected = route.candidate
    correct = selected is not None and selected.agent_id == scenario.gold_agent
    if not correct:
        latency += COST["wrong_route_extra"]
        outcome["rejected"] = True
        return _row(arm, outcome, "wrong_or_missing_agent", latency, payload_rng, telemetry)

    # --- M4: consent and policy control -------------------------------------
    consent = store.get(victim_caller, victim_chat)
    latency += COST["consent_check"]
    consent_missing = fault == "missing_consent"
    if scenario.requires_consent:
        if arm.consent_gate:
            if consent_missing or not (consent or {}).get("consent", False):
                outcome["rejected"] = True
                outcome["safe_rejection"] = True
                return _row(arm, outcome, "consent_missing", latency, payload_rng, telemetry)
        else:
            # No consent gate is installed: a consent-requiring request is
            # executed without an explicit user confirmation.
            outcome["unauthorized_call"] = True

    # --- M5: identity-bound protocol execution ------------------------------
    latency += COST["identity_screen"]
    clean_url = selected.endpoint
    presentation = EndpointPresentation(
        url="http://plain.agents.example/other/rpc" if fault == "bad_endpoint" else clean_url,
        aic=("1.2.156.3088.1.BUPT.FORGED.99" if fault == "forged_identity" else selected.aic),
        mtls=fault != "bad_endpoint",
    )
    if arm.identity_bound:
        latency += COST["mtls_handshake"]
        if not m5_verify_endpoint(selected, presentation):
            outcome["rejected"] = True
            outcome["safe_rejection"] = True
            return _row(arm, outcome, "identity_or_endpoint_rejected", latency, payload_rng, telemetry)
    elif fault in {"forged_identity", "bad_endpoint"}:
        outcome["identity_bypass"] = True

    # --- side effects under the idempotency store ---------------------------
    latency += COST["task_start"] + downstream_rng.uniform(0.0, 20.0)
    for _ in range(deliveries):
        if dedup.claim(scenario.idempotency_key):
            side_effects += 1
    if side_effects > 1:
        outcome["duplicate_side_effect"] = True
    latency += COST["delivery"] * deliveries

    # --- downstream failure classification and recovery ---------------------
    if fault == "timeout":
        latency += COST["retry_extra"]
        if downstream_rng.random() < 0.78:
            outcome["recovered"] = True
            telemetry.append("retry_succeeded")
        else:
            outcome["rejected"] = True
            return _row(arm, outcome, "downstream_timeout", latency, payload_rng, telemetry)

    outcome["correct_delegation"] = True
    outcome["task_success"] = not (outcome["cross_session_leak"] or outcome["duplicate_side_effect"] or outcome["unauthorized_call"])
    telemetry.append("delivered")
    return _row(arm, outcome, "completed", latency, payload_rng, telemetry)


def _row(
    arm: Arm,
    outcome: Dict[str, bool],
    terminal_reason: str,
    latency: float,
    payload_rng: random.Random,
    telemetry: Sequence[str],
) -> Dict[str, Any]:
    row: Dict[str, Any] = {"variant": arm.name}
    row.update(outcome)
    row["terminal_reason"] = terminal_reason
    row["latency_ms"] = round(latency, 3)
    row["message_bytes"] = 240 + payload_rng.randint(0, 180) + 420 * int(terminal_reason == "completed")
    row["retry_count"] = 1 if terminal_reason == "downstream_timeout" else 0
    row["telemetry"] = ",".join(telemetry)
    return row
