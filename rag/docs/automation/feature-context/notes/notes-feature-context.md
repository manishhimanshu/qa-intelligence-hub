# Notes Feature Context (Execution-Focused)

## Purpose
This document captures how the Notes feature is currently automated in this framework so new tests and reviews can follow existing patterns.

## Scope
- Focused on Cypress implementation patterns, not product requirements.
- Focused on specs, page object usage, custom commands, and data lifecycle.
- Uses per-spec or per-context setup and cleanup patterns.

## Spec Map
All primary Notes specs are in `cypress/e2e/parallel/group-9/notes/`.

| Spec | Intent | Notes |
|---|---|---|
| `notesUiTest.cy.js` | Books bar behavior, title truncation, add/rename/delete flows, caret behavior | Largest UI coverage file for Notes.
| `notesDefaultBook_NewUser.cy.js` | New-user default book creation and persistence | Validates default first book behavior.
| `notesBooksDragDrop.cy.js` | Book ordering and drag/drop behavior | Uses API pre-creation (`createNotesBookApi`) and reorder checks.
| `notesHtmlEditorCore_C16848553.cy.js` | HTML editor core interactions | Shadow DOM, toolbar actions, links/images/date insertion.
| `notesModalLayoutAndResizeTest.cy.js` | Modal layout and resize behavior | Positioning, panel resizing, layout assertions.
| `notesSortPagesTest.cy.js` | Sort options and sort correctness | Date Created/Modified/Alphabetical sort checks.
| `notesSearch.cy.js` | Search behavior placeholder | Has setup/teardown but minimal test body; treat as incomplete coverage.

## Page Object Map
Primary page object:
- `cypress/e2e/kapost/pageObjects/notesPage/notesPage.cy.js`
- Export style: singleton (`export default new notes();`)
- Import style in specs: `import notesPage from ".../notesPage.cy"`

Key usage pattern:
- Specs access methods from `notesPage` directly.
- Specs also read element helpers via `const notes = notesPage.notesElements` for direct assertions.

Representative method groups used by specs:
- Modal basics: `openNotes()`, `closeNotes()`
- Book actions: `addBook()`, rename methods, delete methods, caret dropdown handling
- Page actions: page title edits, add/delete page, active page selection
- Sorting: sort dropdown open/select/verify methods
- Layout/resizing: panel width and overflow metrics, resize helpers
- Editor interactions: toolbar and content interactions (especially in HTML editor core spec)

## Custom Command Usage
Command definitions are in `cypress/support/commands.js`.

Notes-specific commands:
- `createNotesBookApi(bookTitle = null)`
  - Creates Notes book using API (`POST /api/v1/notes/books`)
  - Returns created book object
- `getNotesBooksApi()`
  - Fetches all books (`GET /api/v1/notes/books`)
- `reorderNotesBooksApi(booksOrder = [])`
  - Reorders books (`PUT /api/v1/notes/configuration`)
- `deleteNotesBookApi(bookId)`
  - Deletes one book (`DELETE /api/v1/notes/books/{id}`)
- `deleteAllNotesBooksApi()`
  - Fetches all books and deletes each one

User lifecycle commands used by Notes specs:
- `addUser(firstName, lastName, password, { userRole })`
- `removeUserFromKapost(userId)`
- `login(apiToken, destination = '/', counter = 1)`
- `loginAsRole('ADMIN' | 'EDITOR' | 'CONTRIBUTOR' | 'CONSUMER')`

## Test Data Lifecycle (Per Spec/Context)
Observed default Notes lifecycle:
1. `before()` as admin token user:
   - Create temporary user via `addUser(...)`
   - Capture `newUserToken` and `userID`
2. `beforeEach()`:
   - Login as temporary user (`cy.login(newUserToken)`)
   - Navigate to dashboard and open Notes
3. `after()`:
   - Login as temporary user
   - Cleanup books (`deleteAllNotesBooksApi()` or per-book delete loop)
   - Clear sessions
   - Re-login as admin role
   - Delete temporary user (`removeUserFromKapost(userID)`)

Naming conventions seen in Notes data:
- Books often use prefix `CY_Test | ...`
- Faker is used for first/last name and password suffix randomness

Important cleanup ordering:
- Delete Notes books before deleting the temporary user.
- Clear sessions before switching role context back to admin.

## Risks and Gaps
- Role coverage gap: Notes tests are largely admin-only; editor/contributor/consumer behavior is not comprehensively covered.
- Coverage gap: `notesSearch.cy.js` has thin implementation and should be expanded.
- Stability risk: Some specs use short static waits as race-condition bandaids.
- Performance gap: No stress scenario for high numbers of books/pages.

## Reusable Authoring Pattern
Use this pattern for new Notes specs:
- Create and isolate user data in `before()`.
- Keep test setup in `beforeEach()` lightweight (login, navigate, open Notes).
- Use Notes API commands for deterministic setup/cleanup.
- Cleanup in same spec/context `after()` hook.

## Source References
- `cypress/e2e/parallel/group-9/notes/notesUiTest.cy.js`
- `cypress/e2e/parallel/group-9/notes/notesDefaultBook_NewUser.cy.js`
- `cypress/e2e/parallel/group-9/notes/notesBooksDragDrop.cy.js`
- `cypress/e2e/parallel/group-9/notes/notesHtmlEditorCore_C16848553.cy.js`
- `cypress/e2e/parallel/group-9/notes/notesModalLayoutAndResizeTest.cy.js`
- `cypress/e2e/parallel/group-9/notes/notesSortPagesTest.cy.js`
- `cypress/e2e/parallel/group-9/notes/notesSearch.cy.js`
- `cypress/e2e/kapost/pageObjects/notesPage/notesPage.cy.js`
- `cypress/support/commands.js`
