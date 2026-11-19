import sys
import unittest
from pathlib import Path
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rag"))

import ingest_all
from ingest import testrail_ingest


class TestRailIngestionFailureTests(unittest.TestCase):
    def test_api_failures_propagate_instead_of_returning_partial_cases(self):
        for failed_endpoint in ("get_suites", "get_sections", "get_cases"):
            with self.subTest(endpoint=failed_endpoint):
                def get_all(endpoint, list_key):
                    if endpoint.startswith(failed_endpoint):
                        raise requests.exceptions.SSLError("certificate verification failed")
                    if list_key == "suites":
                        return [{"id": 7, "name": "Notes"}]
                    return []

                with (
                    mock.patch.dict("os.environ", {
                        "TESTRAIL_URL": "https://example.test",
                        "TESTRAIL_USER": "test",
                        "TESTRAIL_TOKEN": "test",
                        "TESTRAIL_PROJECT_ID": "34",
                    }),
                    mock.patch.object(testrail_ingest._TestRailClient, "get_all", side_effect=get_all),
                ):
                    with self.assertRaises(requests.exceptions.SSLError):
                        testrail_ingest.ingest_testrail_cases()

    def test_rebuild_does_not_replace_index_when_testrail_fails(self):
        with (
            mock.patch.object(ingest_all, "fetch_jira_issues", return_value=[{"id": "jira_1"}]),
            mock.patch.object(
                ingest_all, "ingest_testrail_cases",
                side_effect=requests.exceptions.SSLError("certificate verification failed"),
            ),
            mock.patch.object(ingest_all, "ingest_pdfs", return_value=[]),
            mock.patch.object(ingest_all, "ingest_markdown_dir", return_value=[]),
            mock.patch.dict("os.environ", {"AUTOMATION_REPO_ROOT": ""}),
            mock.patch.object(ingest_all, "build_vectorstore") as build,
            mock.patch("builtins.print"),
        ):
            self.assertFalse(ingest_all.run_ingestion())
            build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
