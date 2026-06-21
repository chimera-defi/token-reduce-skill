"""Track G — closed-loop escalation.

Watches recent helper events for ignored companion recommendations.
When a session ignores a recommendation more than ``IGNORE_THRESHOLD``
times, ``escalate()`` returns a stronger nudge that points at
``headroom_compress`` (or the relevant companion's primary action).

The baseline behavior is to recommend gently; escalation only kicks in
when the gentler nudge is observably failing. Threshold deliberately
errs on the side of patience — three ignores, not one.
"""
from __future__ import annotations

from dataclasses import dataclass


IGNORE_THRESHOLD = 3


@dataclass(frozen=True)
class EscalationDecision:
    level: str  # "baseline" or "strong"
    ignored_count: int
    threshold: int
    auto_compress_suggested: bool
    message: str


def _meta(event: dict) -> dict:
    raw = event.get("meta") or {}
    return raw if isinstance(raw, dict) else {}


def count_ignored_recommendations(events: list[dict], *, companion: str) -> int:
    """Count events where ``{companion}_recommended`` is True but
    ``{companion}_used`` is not True. Missing ``_used`` counts as
    ignored — same UX outcome.
    """
    rec_key = f"{companion}_recommended"
    used_key = f"{companion}_used"
    ignored = 0
    for ev in events:
        meta = _meta(ev)
        if meta.get(rec_key) is True and meta.get(used_key) is not True:
            ignored += 1
    return ignored


def escalate(events: list[dict], *, companion: str) -> EscalationDecision:
    """Decide whether to escalate the nudge for ``companion`` based on
    ignored count in ``events``.
    """
    ignored = count_ignored_recommendations(events, companion=companion)
    if ignored >= IGNORE_THRESHOLD:
        if companion == "headroom":
            msg = (
                f"{companion} recommendation ignored {ignored} times — "
                "run `headroom_compress` to compact the largest tool result, "
                "or `headroom install status` to verify the proxy is healthy."
            )
        else:
            msg = (
                f"{companion} recommendation ignored {ignored} times — "
                "consider invoking it explicitly or disable the recommendation "
                "via routing settings if it does not apply here."
            )
        return EscalationDecision(
            level="strong",
            ignored_count=ignored,
            threshold=IGNORE_THRESHOLD,
            auto_compress_suggested=(companion == "headroom"),
            message=msg,
        )
    return EscalationDecision(
        level="baseline",
        ignored_count=ignored,
        threshold=IGNORE_THRESHOLD,
        auto_compress_suggested=False,
        message="",
    )
