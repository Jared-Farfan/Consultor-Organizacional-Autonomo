from __future__ import annotations

from app.models import Finding, Severity


def classify_change_severity(finding: Finding) -> Finding:
    """Applies the explicit two-of-three escalation rule.

    Scope, persistence and core impact are evidence fields populated by
    deterministic detectors. A macro recommendation is impossible with fewer
    than two criteria.
    """
    criteria = sum((finding.structural_scope, finding.persistent, finding.core_impact))
    if criteria <= 1:
        finding.severity = Severity.TACTICAL
        finding.horizon = "Horizon 0"
    elif finding.id == "strategic_misalignment":
        finding.severity = Severity.STRATEGIC
        finding.horizon = "Horizon 3"
    elif criteria == 3:
        finding.severity = Severity.ORGANIZATIONAL
        finding.horizon = "Horizon 2"
    else:
        finding.severity = Severity.STRUCTURAL
        finding.horizon = "Horizon 1"
    finding.metrics["severity_criteria_met"] = float(criteria)
    return finding


def classify_all(findings: list[dict]) -> list[dict]:
    output = []
    for data in findings:
        finding = Finding(
            id=data["id"], title=data["title"], evidence=data["evidence"], metrics=data["metrics"],
            structural_scope=data["structural_scope"], persistent=data["persistent"],
            core_impact=data["core_impact"], annual_cost=data["annual_cost"],
            recommendation=data["recommendation"],
        )
        output.append(classify_change_severity(finding).to_dict())
    return output
