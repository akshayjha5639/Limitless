"""
Limitless — Progress Delta Service
Computes domain-level deltas between current and prior report.
Only called when priorReport is provided in the /analyze request.
"""

from app.models.response import Progress, ProgressDelta


def _as_score(value) -> float | None:
    """Accept either a bare number or a scale object.

    `domains` entries are `{score, sem, ciLow, ciHigh}` objects. A stored
    priorReport from an earlier revision holds bare floats under different
    keys, so both shapes are read here and mismatched keys simply produce
    no delta rather than an error.
    """
    if isinstance(value, dict):
        value = value.get("score")
    return value if isinstance(value, (int, float)) else None


def compute_progress(current_domains: dict, prior_report: dict) -> Progress:
    """
    Args:
        current_domains: dict of scale_name → scale object (camelCase keys)
        prior_report:    previous /analyze JSON response

    Returns:
        Progress object with deltas per scale
    """
    prior_domains: dict = prior_report.get("domains", {})
    if not prior_domains:
        return Progress(available=False)

    deltas = []
    for domain_key, current_raw in current_domains.items():
        current_val = _as_score(current_raw)
        prior_val = _as_score(prior_domains.get(domain_key))
        if current_val is None or prior_val is None:
            continue

        delta = round(current_val - prior_val, 2)
        if delta > 1.5:
            direction = "improved"
        elif delta < -1.5:
            direction = "declined"
        else:
            direction = "stable"

        deltas.append(ProgressDelta(
            domain=domain_key,
            previous=prior_val,
            current=current_val,
            delta=delta,
            direction=direction,
        ))

    return Progress(available=bool(deltas), deltas=deltas)
