import unittest

from app.agent import RestructuringAgent
from app.ingestion import normalize_jira_ticket
from app.synthetic import generate_events


class AgentTests(unittest.TestCase):
    @staticmethod
    def _findings() -> dict:
        result = RestructuringAgent(generate_events()).investigate()
        return {
            finding["id"]: finding
            for group in result["report"]["recommendations_by_severity"].values()
            for finding in group
        }

    def test_synthetic_dataset_detects_all_seeded_pathologies(self) -> None:
        findings = self._findings()
        self.assertEqual(set(findings), {
            "hero_spof", "useless_approval", "misaligned_silo", "invisible_operational_debt",
            "triage_ping_pong", "strategic_misalignment", "value_stream_fragmentation",
        })
        self.assertEqual(findings["useless_approval"]["severity"], "tactical")
        self.assertEqual(findings["value_stream_fragmentation"]["severity"], "organizational")
        self.assertEqual(findings["strategic_misalignment"]["severity"], "strategic")

    def test_macro_change_requires_two_of_three_criteria(self) -> None:
        tactical = self._findings()["invisible_operational_debt"]
        self.assertEqual(tactical["metrics"]["severity_criteria_met"], 1.0)
        self.assertEqual(tactical["severity"], "tactical")

    def test_report_exposes_trace_and_synthetic_notice(self) -> None:
        result = RestructuringAgent(generate_events()).investigate()
        tools = [step["tool"] for step in result["trace"]]
        self.assertIn("classify_change_severity", tools)
        self.assertIn("simulate_horizon_cascade", tools)
        self.assertIn("synthetic", result["report"]["data_notice"].lower())
        self.assertEqual(len(result["report"]["horizon_cascade"]), 4)

    def test_jira_adapter_hashes_reporter_data(self) -> None:
        events = normalize_jira_ticket({
            "key": "OPS-9",
            "fields": {"created": "2026-01-01T10:00:00Z", "summary": "Reset access",
                       "team": "Support", "reporter": {"emailAddress": "person@example.com"}},
            "changelog": [],
        })
        self.assertEqual(len(events), 1)
        self.assertNotIn("person@example.com", events[0].actor_hash)


if __name__ == "__main__":
    unittest.main()
