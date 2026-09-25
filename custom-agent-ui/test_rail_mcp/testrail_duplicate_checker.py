"""
TestRail duplicate test-case checker.

Runs the TestRail CLI through the local Node wrapper -- no LLM/agent required
at runtime -- fetches every existing test case in a given TestRail project and compares a list of
proposed new test cases against them using semantic text embeddings + cosine
similarity.


Requires Node available on PATH and the local npm dependencies installed.

Example:
    checker = TestRailDuplicateChecker(
        env={
            "TESTRAIL_URL": "https://upland.testrail.com",
            "TESTRAIL_USERNAME": "you@example.com",
            "TESTRAIL_API_KEY": "xxxx",
        },
        similarity_threshold=70.0,
    )

    new_cases = [
        NewTestCase(
            title="Blind Transfer to Agent using Dial Pad",
            preconditions="Agent A and Agent B are both logged in and available.",
            steps="1. Agent A answers an inbound call.\n2. Agent A dials Agent B's extension and selects Blind Transfer.",
            expected_result="The call is transferred to Agent B and Agent A is disconnected.",
        ),
    ]

    results = asyncio.run(checker.find_duplicates(project_id=37, new_cases=new_cases))
    for title, matches in results.items():
        for m in matches:
            print(f"{title!r} looks like a duplicate of case {m.existing_case_id} "
                  f"({m.existing_case_title!r}) - similarity {m.similarity}%")
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime
import aiohttp
import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

import numpy as np
from dotenv import load_dotenv

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_WRAPPER_PATH = os.path.join(_THIS_DIR, "testrail-cli-wrapper.mjs")
_RAG_ENV_PATH = os.path.join(
    _THIS_DIR,
    "../../rag/.env",
)
load_dotenv(_RAG_ENV_PATH)


@dataclass
class NewTestCase:
    """A candidate test case to be checked for duplicates."""

    title: str
    preconditions: str = ""
    steps: str = ""
    expected_result: str = ""

    def to_text(self) -> str:
        """Concatenates all fields into a single string for embedding."""
        parts = [self.title, self.preconditions, self.steps, self.expected_result]
        return "\n".join(p for p in parts if p)


@dataclass
class DuplicateMatch:
    """A potential duplicate found for a given new test case."""

    new_case: NewTestCase
    existing_case_id: int
    existing_case_title: str
    similarity: float  # 0-100


class TestRailDuplicateChecker:
    """
    Checks proposed TestRail test cases against existing cases in a project
    for potential duplicates, using semantic embeddings for similarity.
    """

    def __init__(
        self,
        similarity_threshold: float = 70.0,
    ):
        """
        Args:
            server_command / server_args: Override how the MCP server is
                launched. Defaults to `node testrail-cli-wrapper.mjs`.
            embed_fn: Optional custom embedding function
                (list[str] -> np.ndarray of L2-normalized vectors). If not
                provided, a local sentence-transformers model is used.
            similarity_threshold: Cosine similarity (0-100) at/above which a
                pair is flagged as a likely duplicate.
            embedding_model_name: sentence-transformers model to use when
                embed_fn is not provided.
        """

        self.base_url = os.getenv("TESTRAIL_URL", "")
        self.username = os.getenv("TESTRAIL_USER", "")
        self.api_token = os.getenv("TESTRAIL_TOKEN", "")
        self.project_id = os.getenv("TESTRAIL_PROJECT_ID", "")
        self.excluded_suites = [int(n) for n in os.getenv("TESTRAIL_EXCLUDED_SUITES", "").split(",") if n.strip().isdigit()]
        self.similarity_threshold = similarity_threshold
        self._embed_fn = None
        self._embedding_model_name = "all-MiniLM-L6-v2"

    @property
    def embed_fn(self) -> Callable[[list[str]], np.ndarray]:
        if self._embed_fn is None:
            self._embed_fn = self._build_default_embed_fn(self._embedding_model_name)
        return self._embed_fn

    @staticmethod
    def _build_default_embed_fn(model_name: str) -> Callable[[list[str]], np.ndarray]:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name)

        def _embed(texts: list[str]) -> np.ndarray:
            return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

        return _embed

    async def _send_get(self, endpoint: str) -> dict:
        auth = aiohttp.BasicAuth(self.username, self.api_token)
        async with aiohttp.ClientSession(auth=auth) as session:
            response = await session.get(f"{self.base_url}/index.php?/api/v2/{endpoint}")
            response.raise_for_status()
            if response.status != 200:
                raise RuntimeError(f"GET {endpoint} failed with status {response.status}")
            return await response.json()

    async def _get_suites(self) -> list[dict]:
        suite_results = await self._send_get(f"get_suites/{self.project_id}")
        return suite_results.get("suites", [])

    async def _get_cases(self, suite_id: int) -> list[dict]:
        """Fetches every test case for a suite, following TestRail's pagination
        (the API caps responses at 250 cases per page)."""
        cases: list[dict] = []
        limit = 250
        offset = 0
        while True:
            case_results = await self._send_get(
                f"get_cases/{self.project_id}&suite_id={suite_id}&limit={limit}&offset={offset}"
            )
            page_cases = case_results.get("cases", [])
            cases.extend(page_cases)
            if len(page_cases) < limit:
                break  # last page reached
            offset += limit
        return cases
          


    async def _fetch_all_project_cases(self) -> list[dict]:
        """Fetches every test case in a project, handling multi-suite projects."""
       
        suites = await self._get_suites()
        cases: list[dict] = []
        for suite in suites:
            if suite["id"] in self.excluded_suites:
                continue
            suite_cases = await self._get_cases(suite["id"])
            cases.extend(suite_cases)
        print(f"DEBUG: Total cases fetched for project {self.project_id}: {len(cases)}")
        return cases

    @staticmethod
    def _case_to_text(case: dict) -> str:
        """Converts a test case dictionary into a plain text representation."""
        steps = case.get("custom_steps_separated", "") or ""
        steps_text = ""
        expected_result_text = ""
        if steps:
            steps_text = "\n".join(f"{i+1}. {s.get('content', '')}" for i, s in enumerate(steps))
            expected_result_text = "\n".join(f"{i+1}. {s.get('expected', '')}" for i, s in enumerate(steps))
        fields = [
            case.get("title", ""),
            case.get("custom_preconds", "") or "",
            steps_text,
            expected_result_text
        ]
        fields2 = [
            case.get("title", ""),
        ]
        fields3 = [
            case.get("title", ""),
            steps_text,
        ]
        return "\n".join(f for f in fields2 if f)

    async def find_duplicates(
        self, project_id: int, new_cases: Iterable[NewTestCase]
    ) -> dict[str, list[DuplicateMatch]]:
        """
        Fetches all existing cases in `project_id` and compares each of
        `new_cases` against them via embedding cosine similarity.

        Returns a dict mapping each new case's title to a list of
        DuplicateMatch (sorted by descending similarity), which is empty
        if no likely duplicate was found.
        """
        new_cases = list(new_cases)
        print("Running find_duplicates for project_id:", project_id)
        start_time = datetime.now()
        existing_cases = await self._fetch_all_project_cases()
        if not existing_cases:
            return {c.title: [] for c in new_cases}

        #Here we need to normalize the content of TR cases because they may have inconsistent formatting.
        #We want to be able to handle both custom_steps as well as test_steps
        existing_texts = [self._case_to_text(c) for c in existing_cases]
        existing_embeddings = self.embed_fn(existing_texts)

        new_texts = [c.to_text() for c in new_cases]
        new_embeddings = self.embed_fn(new_texts)

        # Embeddings are L2-normalized, so dot product == cosine similarity.
        similarity_matrix = new_embeddings @ existing_embeddings.T  # (n_new, n_existing)

        results: dict[str, list[DuplicateMatch]] = {}
        for i, new_case in enumerate(new_cases):
            matches = [
                DuplicateMatch(
                    new_case=new_case,
                    existing_case_id=existing_cases[j]["id"],
                    existing_case_title=existing_cases[j].get("title", ""),
                    similarity=round(float(similarity_matrix[i][j]) * 100, 2),
                )
                for j in range(len(existing_cases))
                if float(similarity_matrix[i][j]) * 100 >= self.similarity_threshold
            ]
            matches.sort(key=lambda m: m.similarity, reverse=True)
            results[new_case.title] = matches

        print("find_duplicates results:")
        for title, matches in results.items():
            print(f"  {title!r}:")
            if not matches:
                print("    (no duplicates)")
            for match in matches:
                print(
                    f"    - Case {match.existing_case_id} "
                    f"({match.existing_case_title!r}) - similarity {match.similarity}%"
                )
        print(f"find_duplicates took {(datetime.now()- start_time).total_seconds():.2f} seconds")
        return results


if __name__ == "__main__":
    checker = TestRailDuplicateChecker(
        similarity_threshold=70.0,
    )

    sample_new_cases = [
        NewTestCase(
            title="Blind Transfer to Agent using Dial Pad",
            preconditions="Agent A and Agent B are both logged in and available.",
            steps="1. Agent A answers an inbound call.\n"
            "2. Agent A dials Agent B's extension and selects Blind Transfer.",
            expected_result="The call is transferred to Agent B and Agent A is disconnected.",
        ),
    ]

    found = asyncio.run(checker.find_duplicates(project_id=37, new_cases=sample_new_cases))
    for case_title, dupes in found.items():
        if not dupes:
            print(f"No likely duplicates found for: {case_title!r}")
            continue
        print(f"Potential duplicates for {case_title!r}:")
        for match in dupes:
            print(
                f"  - Case {match.existing_case_id} "
                f"({match.existing_case_title!r}) - similarity {match.similarity}%"
            )
