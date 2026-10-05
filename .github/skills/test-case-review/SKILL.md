---
name: test-case-review
description: Review generated manual test cases for evidence grounding, completeness, requirement traceability, role scope, realistic steps, verifiable expected results, and duplicate or coverage risks.
---

# Test Case Review

Review the generated requirements brief and cases against the retrieved Jira context before saving.

## Review checklist

- Every requirement statement and derived scenario has a valid verbatim Jira-source citation.
- Every case has a clear scenario, necessary preconditions, numbered one-action steps, and an observable expected result.
- Every coverage reference exists and materially applies; every FR/SC, EC, and NS is covered or clearly called out as missing.
- Role-specific cases appear only when the story makes role/access behavior relevant.
- Cases do not assume unspecified limits, messages, defaults, dependencies, or product behavior.
- Generic infrastructure and non-functional scenarios are absent unless the Jira source explicitly requests them.
- Related checks are grouped only when the workflow and pass/fail intent remain clear.
- The self-critique identifies genuine duplicates, missing coverage, weak expected results, and concrete improvements; do not inflate scores.

Use `critique.missing_coverage`, `duplicate_pairs`, `improvement_suggestions`, and score fields accurately. Fix objective schema/citation/reference errors before saving. Keep uncertain or flagged cases for human review rather than silently deleting them.
