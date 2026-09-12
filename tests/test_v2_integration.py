from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.agent import RestructuringAgent
from app.ingestion import load_event_log_v2, load_taxonomy, write_observed_ticket_summary


ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


class V2IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.events = load_event_log_v2(RAW / "event_log_v2.jsonl", RAW / "org_chart_declared_v2.json")
        cls.taxonomy = load_taxonomy(RAW / "business_taxonomy_v2.json")

    def test_v2_loader_normalizes_event_log_without_private_labels(self) -> None:
        self.assertEqual(len({event.ticket_id for event in self.events}), 6000)
        self.assertTrue(all(event.ts.tzinfo is not None for event in self.events))
        self.assertTrue(any(event.event_type == "approval_decided" for event in self.events))
        self.assertTrue(any(event.event_type == "handoff" for event in self.events))
        self.assertTrue(any(event.event_type == "reassignment" for event in self.events))
        forbidden = {"hero_involved", "hero_absence_hit", "is_hidden_operational_debt"}
        self.assertFalse(any(forbidden & set(event.payload) for event in self.events))

    def test_v2_analysis_detects_the_seven_observed_patterns(self) -> None:
        report = RestructuringAgent(self.events, taxonomy=self.taxonomy).investigate()["report"]
        findings = {
            finding["id"]
            for group in report["recommendations_by_severity"].values()
            for finding in group
        }
        self.assertEqual(findings, {
            "hero_spof", "useless_approval", "misaligned_silo", "invisible_operational_debt",
            "triage_ping_pong", "strategic_misalignment", "value_stream_fragmentation",
        })
        declared = {row["team"]: row for row in report["effort_value_matrix"]["declared_team_demand"]}
        self.assertGreaterEqual(declared["team_alpha"]["low_value_share"], 0.50)
        self.assertGreaterEqual(declared["team_growth"]["core_share"], 0.70)

    def test_observed_summary_excludes_evaluation_columns(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "tickets.csv"
            self.assertEqual(write_observed_ticket_summary(self.events, output), 6000)
            columns = output.read_text(encoding="utf-8").splitlines()[0].split(",")
            self.assertNotIn("hero_involved", columns)
            self.assertNotIn("is_hidden_operational_debt", columns)


if __name__ == "__main__":
    unittest.main()
