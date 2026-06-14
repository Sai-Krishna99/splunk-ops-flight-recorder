"""AI reasoning layer for Ops Flight Recorder.

Turns Splunk-normalized incident evidence into AI-generated root-cause
hypotheses, recommended actions, and a postmortem draft.

Provider-agnostic and dependency-free (uses the standard library, matching the
Splunk REST client style):

- ``OPS_FLIGHT_RECORDER_AI=openai`` -> any OpenAI-compatible Chat Completions
  endpoint. This is also the seam for **Splunk hosted models**: point
  ``OPENAI_BASE_URL`` at the Splunk hosted-model gateway and set the token.
- ``OPS_FLIGHT_RECORDER_AI=anthropic`` -> Anthropic Claude Messages API.

Disabled by default (``OPS_FLIGHT_RECORDER_AI`` unset/``off``) so the
deterministic engine stays the demo-safe fallback. The model may only cite
evidence IDs that were given to it, so it cannot fabricate Splunk evidence.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from backend.app.models import (
    Evidence,
    IncidentEvent,
    IncidentSummary,
    PostmortemDraft,
    RecommendedAction,
    RootCauseHypothesis,
)


class AIUnavailable(RuntimeError):
    """Raised when AI reasoning cannot be produced; callers should fall back."""


@dataclass(frozen=True)
class AIReasoning:
    hypotheses: list[RootCauseHypothesis]
    actions: list[RecommendedAction]
    postmortem: PostmortemDraft
    model: str


class ModelClient(Protocol):
    model: str

    def complete(self, system: str, user: str) -> str:
        ...


# --------------------------------------------------------------------------- #
# Model clients (standard-library HTTP, no third-party SDK required)
# --------------------------------------------------------------------------- #


class OpenAICompatibleClient:
    """OpenAI Chat Completions, incl. Splunk hosted models and other gateways."""

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def complete(self, system: str, user: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0.2,
                "max_tokens": 4096,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, method="POST"
        )
        request.add_header("content-type", "application/json")
        request.add_header("authorization", f"Bearer {self.api_key}")
        payload = _post(request)
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIUnavailable(f"Unexpected model response: {payload}") from exc


class AnthropicClient:
    """Anthropic Claude Messages API."""

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def complete(self, system: str, user: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": 4096,
                "temperature": 0.2,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body, method="POST"
        )
        request.add_header("content-type", "application/json")
        request.add_header("x-api-key", self.api_key)
        request.add_header("anthropic-version", "2023-06-01")
        payload = _post(request)
        try:
            blocks = payload["content"]
            return "".join(
                block.get("text", "") for block in blocks if block.get("type") == "text"
            )
        except (KeyError, TypeError) as exc:
            raise AIUnavailable(f"Unexpected Anthropic response: {payload}") from exc


def _post(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise AIUnavailable(f"Model HTTP {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise AIUnavailable(f"Model request failed: {exc}") from exc


def build_model_client() -> ModelClient | None:
    """Build a model client from the environment, or ``None`` when AI is off."""
    provider = os.getenv("OPS_FLIGHT_RECORDER_AI", "off").lower()
    model = os.getenv("OPS_FLIGHT_RECORDER_AI_MODEL", "")
    if provider in {"openai", "splunk", "splunk_hosted"}:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("SPLUNK_AI_API_KEY")
        if not api_key:
            return None
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return OpenAICompatibleClient(api_key, model or "gpt-4o-mini", base_url)
    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        return AnthropicClient(api_key, model or "claude-sonnet-4-6")
    return None


# --------------------------------------------------------------------------- #
# Analyst
# --------------------------------------------------------------------------- #

_SYSTEM_PROMPT = (
    "You are an expert SRE incident analyst. You reconstruct production "
    "incidents strictly from the Splunk evidence provided to you.\n"
    "Rules:\n"
    "1. Cite evidence ONLY using the exact evidence_id values given. Never "
    "invent evidence or IDs.\n"
    "2. Rank root-cause hypotheses by a confidence score between 0 and 1.\n"
    "3. Be specific: reference services, versions, metrics, and timing.\n"
    "4. Respond with ONLY a single valid JSON object, no markdown fences and no "
    "commentary, matching this schema:\n"
    "{\n"
    '  "hypotheses": [{"title": str, "confidence": number, "reasoning": str, '
    '"scoring_signals": [str], "supporting_evidence_ids": [str]}],\n'
    '  "recommended_actions": [{"priority": "p0"|"p1"|"p2", "title": str, '
    '"owner": str, "rationale": str, "evidence_ids": [str]}],\n'
    '  "postmortem": {"summary": str, "root_cause": str, "impact": str, '
    '"resolution": str, "prevention_tasks": [str], "evidence_refs": [str]}\n'
    "}\n"
    "Order hypotheses strongest-first. Return at most 4 hypotheses and at most "
    "4 recommended actions, keep each reasoning to 1-2 sentences, and make sure "
    "the JSON object is complete and valid."
)


class AIAnalyst:
    def __init__(self, client: ModelClient | None = None) -> None:
        self.client = client if client is not None else build_model_client()

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def reason(
        self, incident: IncidentSummary, events: list[IncidentEvent]
    ) -> AIReasoning:
        if self.client is None:
            raise AIUnavailable("AI analyst is not configured.")
        evidence_by_id = {event.evidence.id: event.evidence for event in events}
        raw = self.client.complete(_SYSTEM_PROMPT, _build_user_prompt(incident, events))
        data = _parse_json(raw)

        hypotheses = _build_hypotheses(data, evidence_by_id)
        if not hypotheses:
            raise AIUnavailable("AI returned no usable hypotheses.")
        actions = _build_actions(data, evidence_by_id)
        postmortem = _build_postmortem(data, hypotheses[0], actions, events, evidence_by_id)
        return AIReasoning(
            hypotheses=hypotheses,
            actions=actions,
            postmortem=postmortem,
            model=self.client.model,
        )


# --------------------------------------------------------------------------- #
# Prompt + parsing helpers
# --------------------------------------------------------------------------- #


def _build_user_prompt(
    incident: IncidentSummary, events: list[IncidentEvent]
) -> str:
    ordered = sorted(events, key=lambda event: event.timestamp)
    payload = {
        "incident": {
            "id": incident.id,
            "title": incident.title,
            "service": incident.service,
            "severity": incident.severity,
            "started_at": incident.started_at.isoformat(),
            "ended_at": incident.ended_at.isoformat() if incident.ended_at else None,
        },
        "events": [
            {
                "evidence_id": event.evidence.id,
                "time": event.timestamp.isoformat(),
                "service": event.service,
                "event_type": event.event_type,
                "severity": event.severity,
                "title": event.title,
                "description": event.description,
                "region": event.region,
                "fields": event.evidence.fields,
            }
            for event in ordered
        ],
    }
    return (
        "Reconstruct this incident from the Splunk evidence below and return the "
        "JSON object described in the system prompt.\n\n"
        + json.dumps(payload, indent=2)
    )


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise AIUnavailable(f"Model did not return JSON: {raw[:200]}")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIUnavailable(f"Model returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AIUnavailable("Model JSON was not an object.")
    return parsed


def _build_hypotheses(
    data: dict, evidence_by_id: dict[str, Evidence]
) -> list[RootCauseHypothesis]:
    hypotheses: list[RootCauseHypothesis] = []
    for index, item in enumerate(_as_list(data.get("hypotheses"))):
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        hypotheses.append(
            RootCauseHypothesis(
                id=str(item.get("id") or f"hyp-ai-{index + 1}-{_slug(title)}"),
                title=title,
                confidence=_clamp(item.get("confidence", 0.5)),
                reasoning=str(item.get("reasoning", "")).strip() or title,
                scoring_signals=[
                    str(signal) for signal in _as_list(item.get("scoring_signals"))
                ][:8],
                supporting_evidence=_resolve_evidence(
                    item.get("supporting_evidence_ids"), evidence_by_id
                ),
            )
        )
    hypotheses.sort(key=lambda hypothesis: hypothesis.confidence, reverse=True)
    return hypotheses


def _build_actions(
    data: dict, evidence_by_id: dict[str, Evidence]
) -> list[RecommendedAction]:
    actions: list[RecommendedAction] = []
    for item in _as_list(data.get("recommended_actions")):
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        priority = str(item.get("priority", "p1")).lower()
        if priority not in {"p0", "p1", "p2"}:
            priority = "p1"
        actions.append(
            RecommendedAction(
                priority=priority,  # type: ignore[arg-type]
                title=title,
                owner=str(item.get("owner", "")).strip() or "incident-commander",
                rationale=str(item.get("rationale", "")).strip() or title,
                evidence=_resolve_evidence(item.get("evidence_ids"), evidence_by_id),
            )
        )
    return actions


def _build_postmortem(
    data: dict,
    top_hypothesis: RootCauseHypothesis,
    actions: list[RecommendedAction],
    events: list[IncidentEvent],
    evidence_by_id: dict[str, Evidence],
) -> PostmortemDraft:
    postmortem = data.get("postmortem")
    if not isinstance(postmortem, dict):
        postmortem = {}
    ordered = sorted(events, key=lambda event: event.timestamp)
    timeline = [f"{event.timestamp.isoformat()} - {event.title}" for event in ordered]
    refs = [
        evidence_id
        for evidence_id in _as_list(postmortem.get("evidence_refs"))
        if evidence_id in evidence_by_id
    ] or [evidence.id for evidence in top_hypothesis.supporting_evidence]
    prevention = [
        str(task) for task in _as_list(postmortem.get("prevention_tasks"))
    ][:8] or [action.title for action in actions]
    return PostmortemDraft(
        summary=str(postmortem.get("summary", "")).strip()
        or f"Incident reconstructed: {top_hypothesis.title}.",
        root_cause=str(postmortem.get("root_cause", "")).strip()
        or top_hypothesis.title,
        impact=str(postmortem.get("impact", "")).strip()
        or "Customer-facing impact was observed in Splunk business metrics.",
        resolution=str(postmortem.get("resolution", "")).strip()
        or "Mitigation and recovery should be confirmed by the incident commander.",
        timeline=timeline,
        prevention_tasks=prevention,
        evidence_refs=refs,
    )


def _resolve_evidence(
    evidence_ids: object, evidence_by_id: dict[str, Evidence]
) -> list[Evidence]:
    resolved: list[Evidence] = []
    seen: set[str] = set()
    for evidence_id in _as_list(evidence_ids):
        key = str(evidence_id)
        if key in evidence_by_id and key not in seen:
            seen.add(key)
            resolved.append(evidence_by_id[key])
    return resolved


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    return []


def _clamp(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, number))


def _slug(value: str) -> str:
    return value.lower().replace("_", "-").replace(" ", "-")[:48].strip("-")
