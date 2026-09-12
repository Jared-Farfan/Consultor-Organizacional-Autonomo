from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.config import Settings


def _fallback_answer(question: str, report: dict[str, Any]) -> dict[str, Any]:
    findings = [
        finding
        for group in report["recommendations_by_severity"].values()
        for finding in group
    ]
    matching = [
        finding for finding in findings
        if any(word in (finding["title"] + " " + finding["recommendation"]).lower() for word in question.lower().split())
    ]
    evidence = matching or findings[:3]
    if not evidence:
        answer = "No hay evidencia suficiente en la investigacion para responder esta pregunta."
    else:
        answer = "La respuesta se basa en hallazgos calculados: " + "; ".join(
            f"{finding['title']} ({finding['severity']})" for finding in evidence[:3]
        ) + ". Revise las metricas y la traza asociada antes de ejecutar cambios."
    return {
        "mode": "deterministic",
        "answer": answer,
        "evidence": [{"finding_id": finding["id"], "metrics": finding["metrics"]} for finding in evidence[:3]],
        "confidence": "limited",
    }


def answer_question(question: str, report: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Narrates precomputed evidence. The LLM is never asked to calculate values."""
    if not settings.llm_enabled:
        return _fallback_answer(question, report)
    if not settings.llm_api_key or not settings.llm_model:
        raise ValueError("LLM is enabled but LLM_API_KEY or LLM_MODEL is missing")

    findings = [
        finding
        for group in report["recommendations_by_severity"].values()
        for finding in group
    ]
    evidence = {
        "executive_summary": report["executive_summary"],
        "flow_metrics": report["flow_metrics"],
        "findings": findings,
        "horizon_cascade": report["horizon_cascade"],
    }
    system = (
        "Eres un consultor de reestructuracion organizacional. Responde exclusivamente en espanol y usa "
        "solo la evidencia proporcionada. Nunca calcules ni estimes numeros nuevos, expongas datos privados "
        "de evaluacion, ni recomiendes cambio macro si el hallazgo no tiene severidad organizacional o estrategica. "
        "Responde de forma ejecutiva y directa: maximo 350 palabras, un titulo breve, hasta tres secciones con "
        "listas cortas y una recomendacion final. No uses tablas Markdown, no repitas todos los hallazgos y no "
        "inventes nombres de equipos, porcentajes o causas."
    )
    user = json.dumps({"question": question, "evidence": evidence}, ensure_ascii=False)
    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if settings.llm_structured_outputs:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "evidence_answer",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "evidence_finding_ids": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "string", "enum": ["high", "medium", "limited"]},
                    },
                    "required": ["answer", "evidence_finding_ids", "confidence"],
                    "additionalProperties": False,
                },
            },
        }
    request = urllib.request.Request(
        f"{settings.llm_base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.llm_timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"LLM request failed with HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"LLM request failed: {error.reason}") from error
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content) if settings.llm_structured_outputs else {"answer": content, "confidence": "limited"}
    allowed = {finding["id"] for finding in findings}
    ids = [item for item in parsed.get("evidence_finding_ids", []) if item in allowed]
    return {
        "mode": "llm",
        "model": settings.llm_model,
        "answer": parsed["answer"],
        "evidence": [{"finding_id": item} for item in ids],
        "confidence": parsed.get("confidence", "limited"),
    }
