"""
Limitless — Progress Delta Service
Computes domain-level deltas between current and prior report.
Only called when priorReport is provided in the /analyze request.
"""

from app.models.response import Progress, ProgressDelta


def compute_progress(current_domains: dict, prior_report: dict) -> Progress:
    """
    Args:
        current_domains: dict of domain_name → score (camelCase keys)
        prior_report:    previous /analyze JSON response

    Returns:
        Progress object with deltas per domain
    """
    prior_domains: dict = prior_report.get("domains", {})
    if not prior_domains:
        return Progress(available=False)

    deltas = []
    for domain_key, current_val in current_domains.items():
        prior_val = prior_domains.get(domain_key)
        if prior_val is None:
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
