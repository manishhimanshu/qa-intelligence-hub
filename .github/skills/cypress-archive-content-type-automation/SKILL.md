---
name: cypress-archive-content-type-automation
description: Generate or review Cypress automation for archiving content types using the archive-specific specs, page objects, API data setup, cross-module behavior, and cleanup order.
---

# Cypress Archived Content Type Automation

Use together with `cypress-automation-generation` when the resolved feature key is `archive-content-type`.

1. Call `qa-hub/get_automation_context` and use the returned target folder. The current archive suite is `cypress/e2e/parallel/group-1/archival-content-type/`.
2. Treat `rag/docs/automation/feature-context/archive-content-type-feature-context.md` as the feature execution map. Choose the closest matching scenario and inspect its actual code before generating.
3. Reuse `contentTypePage` and other page objects returned by context. Confirm their import/export style and method signatures from source, not from names in documentation alone.
4. Use the documented APIs to create data where appropriate. Clean up dependent ideas and content items before deleting content types.
5. Keep archive/unarchive, filtering, downstream-module visibility, and activity assertions limited to the selected manual cases and their Jira evidence. Do not combine unrelated module workflows into one test merely to reduce case count.
6. Do not create new locators or helpers if existing page-object/common wrappers apply. Propose minimal page-object diffs for review; never modify existing files through the spec creation tool.
