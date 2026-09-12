from pathlib import Path
from dataclasses import replace
import unittest

from fastapi.testclient import TestClient

from app.agent import RestructuringAgent
from app.api import app
from app.config import PROJECT_ROOT, settings
from app.llm import answer_question
from app.synthetic import generate_events


class ConfigurationTests(unittest.TestCase):
    def test_template_contains_no_llm_secret(self) -> None:
        template = (PROJECT_ROOT / ".env.template").read_text(encoding="utf-8")
        self.assertIn("LLM_API_KEY=", template)
        self.assertNotIn("sk-", template)

    def test_safe_local_defaults_use_read_only_database_access(self) -> None:
        self.assertTrue(settings.llm_enabled)
        self.assertTrue(settings.llm_model)
        self.assertTrue(settings.db_read_only)
        self.assertIn(settings.data_source, {"jsonl", "duckdb", "postgres"})

    def test_frontend_and_safe_configuration_status_are_available(self) -> None:
        client = TestClient(app)
        self.assertEqual(client.get("/").status_code, 200)
        status = client.get("/config/status")
        self.assertEqual(status.status_code, 200)
        self.assertNotIn("DATABASE_URL", status.text)
        self.assertNotIn("restructure_local_dev_only", status.text)

    def test_questions_use_deterministic_evidence_without_llm(self) -> None:
        report = RestructuringAgent(generate_events()).investigate()["report"]
        answer = answer_question("Why is onboarding fragmented?", report, replace(settings, llm_enabled=False))
        self.assertEqual(answer["mode"], "deterministic")
        self.assertTrue(answer["evidence"])


if __name__ == "__main__":
    unittest.main()
