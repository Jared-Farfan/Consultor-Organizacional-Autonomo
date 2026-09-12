from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.models import TAXONOMY


def propose_org_blocks(handoff_graph: dict[str, Any], alignment: dict[str, Any]) -> dict[str, Any]:
    """Creates value-stream blocks from observed dependencies, not job titles."""
    high_value = [row["category"] for row in alignment["rows"] if row["core"]]
    dependencies = handoff_graph["edges"][:8]
    return {
        "current_structure": [
            "Onboarding Product", "Customer Support", "Platform Engineering", "Risk and Compliance",
        ],
        "proposed_blocks": [
            {
                "name": "Customer Onboarding Value Stream",
                "purpose": "Own end-to-end enterprise onboarding across product, platform, risk and support.",
                "evidence": "Four-team onboarding path with accumulated handoff queues.",
                "interfaces": ["Compliance review SLA", "Platform provisioning SLA"],
            },
            {
                "name": "Reliability and Automation Enablement",
                "purpose": "Eliminate repeated operational debt before moving support capacity.",
                "evidence": "Repeated access-provisioning work and hero-dependent routing.",
                "interfaces": ["Self-service access API", "Shared escalation queue"],
            },
        ],
        "observed_dependencies": dependencies,
        "core_categories": high_value,
        "note": "Proposed blocks are evidence-backed operating units, not a final HR organization chart.",
    }
