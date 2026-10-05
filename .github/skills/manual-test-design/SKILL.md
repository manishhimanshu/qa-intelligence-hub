---
name: manual-test-design
description: Apply manual QA test design techniques such as boundary value analysis, equivalence partitioning, decision tables, state transitions, and UI-control testing when designing cases from Jira requirements.
---

# Manual Test Design

## Evidence rule

Use this skill only after fetching the Jira context with `qa-hub/get_story_context`. Design techniques help derive checks from stated behavior; they do not authorize new product behavior. Every derived scenario must cite a Jira requirement or source excerpt. If the requirement does not define expected behavior, record a QA gap or PO question instead of guessing.

## Select techniques based on the requirement

- **Boundary Value Analysis:** use when a requirement states a numeric, length, date, count, or range boundary. Test the boundary and adjacent valid/invalid values supported by the requirement.
- **Equivalence Partitioning:** group inputs expected to behave the same; test representative valid and invalid values only where input rules are stated.
- **Decision Table:** use when outcomes depend on multiple conditions or combinations of role, state, or input.
- **State Transition:** use when behavior changes between explicit states (for example, active/archived/restored).
- **Use-case/workflow testing:** validate a complete user outcome with related steps; avoid splitting one coherent workflow into control-by-control cases.

## UI controls (apply only when specified by the story)

- **Checkbox/toggle:** check the stated default, changing state, saved state after reload, and dependent behavior if specified.
- **Text/input field:** check stated requiredness, format, length boundaries, validation, and accepted/rejected classes. Do not invent limits or error copy.
- **Dropdown/select:** check stated options, default, selection, dependent values, and empty state where applicable.
- **Search/filter/list:** where the story describes the behavior, consider no results, one result, and maximum/list-boundary states. Cite the behavior that makes each relevant.
- **Destructive action:** test confirmation/cancel/commit only when the story or feature documentation specifies that interaction.

## Case design

Group checks when they share the same workflow, business objective, preconditions, and pass/fail outcome. Keep cases separate when the expected outcome or failure diagnosis would become unclear, or the workflow/preconditions differ. Make each step one observable user action and each expected result objectively verifiable.
