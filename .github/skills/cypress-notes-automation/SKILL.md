---
name: cypress-notes-automation
description: Generate or review Cypress automation for the Kapost Notes feature using its Notes-specific specs, Notes page object, data commands, and cleanup ordering.
---

# Cypress Notes Automation

Use together with `cypress-automation-generation` when the resolved feature key is `notes`.

1. Call `qa-hub/get_automation_context` and use the returned target folder. The current Notes spec area is `cypress/e2e/parallel/group-9/notes/`.
2. Treat `rag/docs/automation/feature-context/notes-feature-context.md` as the Notes automation map. Use its existing Notes specs, especially the matching workflow, as the style and lifecycle source.
3. Reuse the singleton `notesPage` from `cypress/e2e/kapost/pageObjects/notesPage/notesPage.cy.js`; inspect the retrieved implementation for exact method names and locator helpers. Also reuse the common object utility and existing Notes API commands where relevant.
4. Keep each test's Notes data isolated. Prefer documented API setup helpers; clean up Notes books before deleting a temporary user, and follow the retrieved lifecycle for role/session switching.
5. Do not add generic role cases, static waits, selectors, API endpoints, or methods that the selected test cases and repository context do not support. Never copy implementation from an incomplete spec without checking another working Notes example.
6. Propose any Notes page-object changes as a diff only. The general workflow asks the user before creating a new spec; this skill does not authorize modifying an existing Notes spec.
