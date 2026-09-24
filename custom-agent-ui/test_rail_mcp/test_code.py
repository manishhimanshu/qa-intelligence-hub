from testrail_duplicate_checker import TestRailDuplicateChecker, NewTestCase, DuplicateMatch
import asyncio

checker = TestRailDuplicateChecker()

# checker.find_duplicates(project_id=37, new_cases=[])
cases = asyncio.run(checker._fetch_all_project_cases())

print("SAMPLE:\n", checker._case_to_text(cases[150]))