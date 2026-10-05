# <Feature Name> UI Execution Map

<!-- Required ingestion metadata: feature_key=<canonical-feature-key>; doc_domain=ui_execution_map -->

## Metadata
- `feature_key`: `<canonical-feature-key>`
- `doc_domain`: `ui_execution_map`
- `base_route`: `/<feature-route>`

## Navigation
- Open feature: `/<feature-route>`
- Login destination: `/<feature-route>`

## Selector Dictionary

| Logical target | Selector | Notes |
|---|---|---|
| `<target label>` | `[data-cy="<stable-id>"]` | Prefer `data-cy` or `data-testid`; do not use generated classes. |

## Preconditions

### `<precondition name>`
- Required state: `<state that must exist>`
- Preferred setup: `api` or `ui`
- Setup command or endpoint: `<document the safe setup operation>`
- Cleanup command or endpoint: `<document the cleanup operation>`
- Required role: `<admin/editor/contributor/consumer>`
- Required access level: `<owner/edit/view/none>`

## Action Patterns

### `<workflow name>`
1. `goto`: `/<route>`
2. `click`: `<logical target>`
3. `fill`: `<logical target>` with `<safe test value>`
4. `assert_visible`: `<logical target>`
5. `assert_text`: `<logical target>` contains `<expected text>`

## Assertion Rules
- Use observable UI state, URL, text, or element visibility.
- Do not claim success from a click alone.
- Record expected empty, error, permission, and loading states when the feature supports them.

## Missing Information Policy
- Do not guess selectors, routes, credentials, setup payloads, or expected text.
- Mark a test as `blocked` when required execution data is absent.
