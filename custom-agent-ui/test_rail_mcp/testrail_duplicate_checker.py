"""
TestRail duplicate test-case checker.

Runs the TestRail CLI through the local Node wrapper -- no LLM/agent required
at runtime -- fetches every existing test case in a given TestRail project
(handling both single-suite and multi-suite projects), and compares a list of
proposed new test cases against them using semantic text embeddings + cosine
similarity.

Install dependencies:
    pip install mcp sentence-transformers numpy

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
import json
import os
import subprocess
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
        server_command: str = "node",
        server_args: Optional[list[str]] = None,
        embed_fn: Optional[Callable[[list[str]], np.ndarray]] = None,
        similarity_threshold: float = 70.0,
        embedding_model_name: str = "all-MiniLM-L6-v2",
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
        self.server_command = server_command
        self.server_args = server_args or [_WRAPPER_PATH]
        self.server_env = os.environ.copy()
        self.server_env.update({
            "TESTRAIL_INSTANCE_URL": os.getenv("TESTRAIL_URL", ""),
            "TESTRAIL_USERNAME": os.getenv("TESTRAIL_USER", ""),
            "TESTRAIL_API_KEY": os.getenv("TESTRAIL_TOKEN", ""),
        })
        self.similarity_threshold = similarity_threshold
        self._embed_fn = embed_fn
        self._embedding_model_name = embedding_model_name

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

    async def _run_cli(self, command: str, arguments: dict) -> Any:
        args = [self.server_command, *self.server_args, command]
        for key, value in arguments.items():
            if value is None:
                continue
            args.append(f"--{key}")
            if isinstance(value, (dict, list)):
                args.append(json.dumps(value))
            else:
                args.append(str(value).lower() if isinstance(value, bool) else str(value))

        process = await asyncio.create_subprocess_exec(
            *args,
            env=self.server_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode("utf-8", errors="replace").strip()
        error = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode != 0:
            detail = error or output or f"exit code {process.returncode}"
            raise RuntimeError(f"TestRail CLI command {command!r} failed: {detail}")

        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"TestRail CLI command {command!r} returned invalid JSON: {output[:500]}"
            ) from exc

    @staticmethod
    def _extract_list(payload: Any, key: str) -> list[dict]:
        """MCP tool results may return a bare list or a {key: [...]} envelope."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return payload.get(key, [])
        return []

    async def _fetch_all_project_cases(self, project_id: int) -> list[dict]:
        """Fetches every test case in a project, handling multi-suite projects."""
        try:
            result = await self._run_cli("get_cases", {"project_id": project_id})
            return self._extract_list(result, "cases")
        except Exception:
            # Multi-suite project (suite_mode=3): must enumerate suites first.
            suites_result = await self._run_cli(
                "query_suite",
                {"payload": {"action": "many", "project_id": project_id}},
            )
            suites = self._extract_list(suites_result, "suites")

            cases: list[dict] = []
            for suite in suites:
                suite_cases_result = await self._run_cli(
                    "get_cases", {"project_id": project_id, "suite_id": suite["id"]}
                )
                cases.extend(self._extract_list(suite_cases_result, "cases"))
            return cases

    @staticmethod
    def _case_to_text(case: dict) -> str:
        fields = (
            case.get("title", ""),
            case.get("custom_preconds", "") or "",
            case.get("custom_steps", "") or "",
            case.get("custom_expected", "") or "",
        )
        return "\n".join(f for f in fields if f)

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
        existing_cases = await self._fetch_all_project_cases(project_id)

        if not existing_cases:
            return {c.title: [] for c in new_cases}

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
