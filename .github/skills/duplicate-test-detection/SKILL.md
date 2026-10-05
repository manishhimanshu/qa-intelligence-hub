---
name: duplicate-test-detection
description: Find exact and semantic duplicates between proposed Jira test cases and existing TestRail cases; identify matching case IDs and recommend review without silently deleting tests.
---

# Duplicate Test Case Detection

## Inputs

Use `existing_testrail_cases` from `qa-hub/get_story_context`. These are retrieved from the last-ingested FAISS snapshot, not live TestRail. Consider Jira-linked cases first, but also inspect semantically similar candidates.

## Compare intent, not only wording

For each generated case, compare the business scenario, actor/role, preconditions, actions, and expected outcome against existing cases. Different titles can still describe the same behavior; similar titles can describe different behavior. Do not treat a shared UI control alone as a duplicate.

Classify each comparison as:

- **Exact/near duplicate:** same scenario and materially same outcome; identify the generated ID and existing TestRail case ID.
- **Related but distinct:** overlapping feature/steps but a different state, role, boundary, or outcome; explain the distinction.
- **No likely duplicate:** no existing case has materially equivalent intent.

Put duplicate pairs in the self-critique and mention TestRail IDs and evidence. Exact normalized title matches returned by the MCP saver are candidates, not proof. Do not remove or merge cases automatically; leave the decision to the QA reviewer.
