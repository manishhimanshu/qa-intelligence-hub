# Combined RAG Context: Copilot + Cypress Script Instructions

## Source 1: .github/copilot-instructions.md

# QA AI Instructions — Kapost Automation Suite

## Role
You are assisting a senior QA Automation Engineer on the Kapost content marketing platform.
The stack is Cypress 10+, JavaScript (ES modules), Jenkins CI, TestRail, and Jira (Atlassian).

## Product Domain Knowledge
- **Kapost** is a content marketing platform
- Core features: Content Catalog, Initiatives (Campaigns), Ideas, Gallery, Members, Settings, Calendar, Global Search, Notifications, Dashboard, NAPA
- **User roles**: admin, editor, contributor, consumer — each has different permissions
- **Environments**: GROUP1–GROUP9, SMOKE, LOCAL, PRODTEST, NEWTEST, TEST — environment-aware data and content counts are derived from `contentRegistry.js` and helpers in `globalTestData.js`
- **CI setup**: Jenkins parallel groups (group-1 through group-9) — specs are split across `cypress/e2e/parallel/`
- **Spec placement**:
	- `cypress/e2e/smoke/` for critical smoke coverage
	- `cypress/e2e/parallel/group-N/` for grouped regression coverage
	- `cypress/e2e/kapost/` for feature-organized specs and supporting verification work

## Authentication Patterns
Always use the correct login method:
- API token login (preferred for speed): `cy.login(Cypress.env('KAPOST_ADMIN_API_TOKEN'))`
- UI login by role: `cy.loginUI('admin' | 'editor' | 'contributor' | 'consumer')`
- Role-based shorthand: `cy.loginAsRole('ADMIN')`
- Logout: `cy.visit('/users/sign_out?recall=${Cypress.env("baseUrl")}')`

Recommended login usage by scenario:
- Standard setup and fast-path auth: `cy.login(...)`
- Role switching inside a test: `Cypress.session.clearAllSavedSessions(); cy.loginAsRole('EDITOR')`
- UI auth screen validation only: `cy.loginUI(...)`

## Environment Variables (never hardcode)
- `Cypress.env('KAPOST_ADMIN_API_TOKEN')`
- `Cypress.env('KAPOST_ADMIN')` / `Cypress.env('KAPOST_ADMIN_PASSWORD')`
- `Cypress.env('KAPOST_EDITOR')` / `Cypress.env('KAPOST_EDITOR_PASSWORD')`
- `Cypress.env('KAPOST_CONTRIBUTOR')` / `Cypress.env('KAPOST_CONTRIBUTOR_PASSWORD')`
- `Cypress.env('KAPOST_CONSUMER')` / `Cypress.env('KAPOST_CONSUMER_PASSWORD')`
- `Cypress.env('baseUrl')`

## Test Data
- Use `Faker` for dynamic data: `Faker.hacker.phrase()`, `Faker.lorem.words()`, `Faker.fake("{{name.firstName}}")`
- Environment-specific fixture data may live in `cypress/fixtures/globalTestData*.json`
- Content type IDs and reusable environment-aware data should come from `globalTestData.js` helpers, never hardcode IDs
- `contentRegistry.js` maps base URLs like `NEWTEST`, `TEST`, `PRODTEST`, and `SMOKETEST` to logical groups and content requirements
- Always prefix generated test data names with `CY_Test |` for easy identification and cleanup
- Default to creating and cleaning up test data in the same spec file or context hooks; do not assume separate setup or teardown specs

## Key Custom Commands (always prefer these over raw Cypress)
- Auth/session and role helpers:
	- `cy.login(apiToken, destination = '/', counter = 1)`
	- `cy.loginAsRole('ADMIN' | 'EDITOR' | 'CONTRIBUTOR' | 'CONSUMER')`
	- `cy.loginUI('admin' | 'editor' | 'contributor' | 'consumer')` (only for UI auth tests)
	- `cy.logout()` / `cy.requestLogout()` / `cy.preserveCookies()`
- Content lifecycle and workflow APIs:
	- `cy.createContentAPI({ contentTypeName, contentName })`
	- `cy.createContentItem({ contentTypeName, initiativeIds })`
	- `cy.createContentItemManageAccess({ contentTypeName, initiativeId })`
	- `cy.getContentApi(requestBody)`
	- `cy.updateContentItem(...)` / `cy.visitContentItem(...)` / `cy.deleteContentItem(...)`
	- `cy.changeContentProgress(...)` / `cy.changeContentStatus(...)`
	- `cy.createInitiativeApi(name, options)`
	- `cy.createInitiativeTypeApi(options)`
	- `cy.createContentTypeWithKapostCloud(type)`
	- `cy.createContentType(...)` / `cy.updateContentType(...)` / `cy.deleteContentType(...)`
	- `cy.addCustomFieldsToContentType(...)` / `cy.addEmptyCustomField(...)` / `cy.deleteCustomField(...)`
	- `cy.createContentTypeWithTasks(numStageTasks, numTasks, options)`
	- `cy.addTaskToContent(contentId, options)`
	- `cy.addStagesToContent(contentId, stageTemplateId, count)`
- User and membership helpers:
	- `cy.addUser(firstName, lastName, password, { userRole })`
	- `cy.addUserToKapost(firstName, lastName, password, { userRole })` (legacy flow)
	- `cy.removeUserFromKapost(userId)`
	- `cy.addMembersGroup(options)`
	- `cy.addMembersToGroup(groupId, memberIds)`
	- `cy.deleteMembersGroup(groupId)`
- Ideas, navigation, and editor helpers:
	- `cy.createIdea(title, description)` / `cy.createIdeaAPI(...)` / `cy.submitIdeaAPI(...)`
	- `cy.clearFilter()` / `cy.navigateByText(linkText)` / `cy.setMceContent(text)`
	- `cy.deleteAllCollections()`
- Cleanup and bulk helpers:
	- `cy.deleteAllIdeas()` / `cy.deleteAllInitiatives()` / `cy.deleteAllCollections()`
	- `cy.deleteAllBundles()` / `cy.deleteAllMemberGroups()` / `cy.deleteAllSavedViews()`
	- `cy.contentTypeSettingsCleanup()` / `cy.customFieldsCleanup()` / `cy.settingsStagesCleanup()`
- Utility and file/email helpers:
	- `cy.waitForSuccessfulMutation(alias, operationName)`
	- `cy.readExcelData(...)` / `cy.readDocx(...)` / `cy.DeleteFile(filePath)`
	- `cy.getEmails(emailId)` / `cy.getDomains()` / `cy.waitForMailTmEmail(...)`
	- `cy.task('getPdfContent', pdfPath)` / `cy.task('fileExists', filePath)` / `cy.task('extractZip', { zipPath, destPath })`
	- `cy.task('deleteAny', path)` / `cy.task('log', message)`

## GraphQL
- Global intercept is set up in `cypress/support/global-graphql-hook.js`
- `interceptGQLGlobal()` already runs in `before()` and `beforeEach()` globally via `e2e.js`
- Alias GQL calls by operation name: `cy.wait('@OperationName')`
- Do not duplicate the global GraphQL intercept in every spec unless a test has a special local need

## API Intercept Pattern
Always alias intercepts BEFORE triggering the UI action that fires them:
```js
cy.intercept('POST', '**/content*').as('createContent')
cy.intercept('GET', 'api/v1/content*').as('contentCatalog')
// trigger UI action here
cy.wait('@createContent')
```
- Prefer request-specific assertions in the wait chain instead of static waits

## Page Object Structure
Page objects live in `cypress/e2e/kapost/pageObjects/`:
- `contentPages/` — Content Catalog, content detail
- `initiative-pages/` — Initiatives / Campaigns
- `ideasPages/` — Ideas module
- `galleryPageObjects/` — Gallery
- `settingsPages/` — Admin settings
- `calenderPageObjects/` — Calendar
- `dashboardPage/` — Dashboard
- `memberActivity/` — Members
- `notesPage/` — Notes panel, editor toolbar, books/pages panel
- `notificationPage/` — Notification center
- `taskPages/` — Task catalogue/workflows
- `canvas/` — Canvas-related flows
- `uplandAssistPage/` — Upland Assist module
- `commonObjectsAndUtilities/` — Shared utilities and common elements

Frequently imported page object classes (use these names when generating imports):
- `contentPage` from `contentPages/content.cy`
- `contentCataloguePage` from `contentPages/contentCatalogue.cy`
- `contentTypePage` from `settingsPages/contentTypePage.cy`
- `initiativesPage` from `initiative-pages/initiatives.cy`
- `initiativeCatalogue` from `initiative-pages/initiativeCatalogue.cy`
- `ideaCataloguePage` / `ideaDetailsPage` from `ideasPages/`
- `galleryPage` / `galleryCollectionPage` from `galleryPageObjects/`
- `notes` from `notesPage/notesPage.cy`
- `memberActivityPage` from `memberActivity/memberActivityPage.cy`
- `calenderPage` from `calenderPageObjects/calenderPage.cy`

Important usage rule:
- Match the neighboring spec's import and instantiation style for that page object. This framework has mixed exports: some page objects are instantiated with `new`, while others are exported as singleton instances.
- Never use naked selectors (for example `cy.get(...)`) directly inside spec `it(...)` blocks.
- Always route locators through page object methods/functions or page-object variables.
- Before adding a new locator wrapper, first check and reuse existing locator abstractions from:
  1) `commonPageObjectsAndUtils.cy.js`
  2) the current feature page object file (for example `contentTypePage.cy.js`)

## Reporting
- Reporter: Mochawesome — reports land in `cypress/report/mochawesome-report/`
- Videos are enabled (`video: true`); screenshots go to `cypress/screenshots/`
- Timeout defaults: `pageLoadTimeout: 60000`, `defaultCommandTimeout: 15000`

## Authoring Expectations
- Keep setup and cleanup local to the spec or context that owns the data.
- Prefer API creation and API cleanup over UI setup when a custom command already exists.
- Reuse environment-aware helpers before inventing new fixture IDs or hardcoding content types.
- For multi-role tests, clear sessions between roles and make the acting role explicit in the test body.
- When adding assertions around downloads or generated files, prefer existing Cypress tasks over ad-hoc Node scripts inside tests.

## Security
- Never log, expose, or hardcode API tokens, passwords, or email credentials in new code
- Always use `Cypress.env()` for credentials — no exceptions
- Do not generate or suggest production URLs

---

## Source 2: .github/instructions/cypress-scripts.instructions.md

---
applyTo: "cypress/e2e/**/*.cy.js"
---

# Cypress Script Generation Rules — Kapost/Pilyr

## File Structure
Every spec file must follow this structure:
```js
/// <reference types="cypress" />
import SomePageObject from '../../kapost/pageObjects/somePages/page.cy'
import Faker from 'faker'

const page_obj = /* mirror the neighboring spec: either instantiate or use the imported singleton */

describe('Feature Name — Scenario Summary', () => {
  before(() => {
    // One-time setup: API login, create test data via API commands only
    cy.login(Cypress.env('KAPOST_ADMIN_API_TOKEN'))
  })

  after(() => {
    // Cleanup: delete created data, logout
    cy.logout()
  })

  beforeEach(() => {
    // Intercepts and navigation only
    cy.intercept('GET', 'api/v1/content*').as('contentCatalog')
    cy.visit('/studio/content')
  })

  context('Sub-feature or workflow group', () => {
    it('should [expected behavior] when [condition]', () => {
      // test steps
    })
  })
})
```

Use the template as a lifecycle pattern, not a literal import pattern. This framework mixes page object export styles, so always copy the import and instantiation style from the nearest existing spec that uses the same page object.

## Page Object Usage
- Page objects live in `cypress/e2e/kapost/pageObjects/`
  - `contentPages/` — Content Catalog, content detail
  - `initiative-pages/` — Initiatives / Campaigns
  - `ideasPages/` — Ideas
  - `galleryPageObjects/` — Gallery
  - `settingsPages/` — Admin settings
  - `calenderPageObjects/` — Calendar
  - `dashboardPage/` — Dashboard
  - `memberActivity/` — Members
  - `notesPage/` — Notes editor, books/pages, resize and toolbar flows
  - `notificationPage/` — Notification center
  - `taskPages/` — Task catalog workflows
  - `canvas/` — Canvas workflows
  - `uplandAssistPage/` — Upland Assist workflows
  - `commonObjectsAndUtilities/` — Shared utilities
- Import as: `import contentPage from '../../kapost/pageObjects/contentPages/content.cy'`
- Instantiate only if the neighboring spec does so. Some page objects are exported as classes and used with `new`; others are exported as ready-to-use singleton instances.
- Always use page object methods for UI interactions on established features
- Do not place raw `cy.get(...)` selectors in spec tests.
- If needed, add a minimal locator wrapper in the page object (method/function or variable) following neighboring page-object style, then use that abstraction from the spec.
- Reuse existing locator wrappers from `commonPageObjectsAndUtils.cy.js` and the current feature page object before creating new ones.

Frequently used page object imports:
- `import contentPage from '../../kapost/pageObjects/contentPages/content.cy'`
- `import contentCataloguePage from '../../kapost/pageObjects/contentPages/contentCatalogue.cy'`
- `import contentTypePage from '../../kapost/pageObjects/settingsPages/contentTypePage.cy'`
- `import initiativesPage from '../../kapost/pageObjects/initiative-pages/initiatives.cy'`
- `import initiativeCatalogue from '../../kapost/pageObjects/initiative-pages/initiativeCatalogue.cy'`
- `import ideaCataloguePage from '../../kapost/pageObjects/ideasPages/ideaCataloguePage.cy'`
- `import ideaDetailsPage from '../../kapost/pageObjects/ideasPages/ideaDetailsPage.cy'`
- `import galleryPage from '../../kapost/pageObjects/galleryPageObjects/galleryPageObjects.cy'`
- `import notesPage from '../../kapost/pageObjects/notesPage/notesPage.cy'`
- `import memberActivityPage from '../../kapost/pageObjects/memberActivity/memberActivityPage.cy'`

## Locator Priority (when using Playwright MCP captured locators)
Use in this order:
1. `data-cy` attribute: `cy.get('[data-cy="side-nav-Content"]')`
2. ARIA role / accessible name: `cy.contains('button', 'Create')`
3. Semantic selectors: `cy.get('input[id="user_email"]')`
4. Class-based only if no better option exists

**Never use** `:nth-child()` selectors in new code — they are brittle.
**Never use** `cy.wait(ms)` with values over 3000ms for app state; use `cy.intercept` aliases instead.

Allowed exception:
- If the current area has a known race and the existing suite already uses a very short bandaid wait, keep it minimal and document it with a comment. Do not introduce long opaque waits for normal synchronization.

## Setup Data — Always Use API Commands in before()
```js
before(() => {
  cy.login(Cypress.env('KAPOST_ADMIN_API_TOKEN'))
  cy.createContentTypeWithKapostCloud('html').then((contentType) => {
    cy.createContentAPI({ contentTypeName: contentType.display_name }).then((content) => {
      testContentId = content.body.response.id
      testContentName = content.body.response.title
    })
  })
})
```

Per-spec data lifecycle rules:
- Create and clean up test data in the same spec file or the same `context()` owner.
- Use `before()` for one-time setup that multiple tests share.
- Use `beforeEach()` only for intercepts, navigation, and lightweight setup unless the test truly needs fresh data per run.
- Use `after()` or context-scoped cleanup hooks for API cleanup commands such as `cy.deleteAllIdeas()`, `cy.deleteInitiative(id)`, or `cy.deleteContentItem(id)`.
- If the suite reuses environment-aware shared data, retrieve it through helpers in `globalTestData.js` rather than hardcoding fixture IDs.

## Custom Command Selection (Framework-Preferred)
Use these command patterns before writing raw API calls:
- Authentication/session:
  - `cy.login(Cypress.env('KAPOST_ADMIN_API_TOKEN'))` for primary setup
  - `cy.loginAsRole('ADMIN' | 'EDITOR' | 'CONTRIBUTOR' | 'CONSUMER')` for role switches
  - `cy.logout()` or `cy.requestLogout()` for cleanup
- Content and initiatives:
  - `cy.createContentAPI({ contentTypeName, contentName })`
  - `cy.createContentItem({ contentTypeName, initiativeIds })`
  - `cy.updateContentItem(...)`
  - `cy.deleteContentItem(...)`
  - `cy.createInitiativeApi(name, options)`
  - `cy.createInitiativeTypeApi(options)`
  - `cy.deleteInitiative(id)` / `cy.deleteAllInitiatives()`
  - `cy.getContentApi(requestBody)`
- Content type, custom field, and access helpers:
  - `cy.createContentType(...)` / `cy.updateContentType(...)` / `cy.deleteContentType(...)`
  - `cy.createContentTypeWithKapostCloud(type)`
  - `cy.createContentTypeWithTasks(numStageTasks, numTasks, options)`
  - `cy.addCustomFieldsToContentType(...)` / `cy.addEmptyCustomField()` / `cy.deleteCustomField(...)`
  - `cy.addManageAccess(resourceId, userIDs, userPermissions, options)`
- Workflow/tasks:
  - `cy.addTaskToContent(contentId, options)`
  - `cy.addStagesToContent(contentId, stageTemplateId, count)`
  - `cy.addTaskToContentWithRules(...)`
  - `cy.addTasksToStage(...)`
- Users and permissions:
  - `cy.addUser(firstName, lastName, password, { userRole })`
  - `cy.addUserToKapost(...)` (legacy path)
  - `cy.removeUserFromKapost(userId)`
- Ideas, gallery, and cleanup:
  - `cy.createIdea(title, description)` / `cy.createIdeaAPI(...)` / `cy.submitIdeaAPI(...)`
  - `cy.deleteAllIdeas()` / `cy.deleteAllCollections()` / `cy.deleteAllBundles()` / `cy.deleteAllSavedViews()`
  - `cy.contentTypeSettingsCleanup()` / `cy.customFieldsCleanup()` / `cy.settingsStagesCleanup()`
- Mutation/async stability:
  - `cy.waitForSuccessfulMutation(alias, operationName)`
  - `cy.wait('@OperationName')` for GraphQL aliases
- File and plugin tasks:
  - `cy.readExcelData(...)` / `cy.readDocx(...)` / `cy.task('getPdfContent', pdfPath)`
  - `cy.task('fileExists', filePath)` / `cy.task('extractZip', { zipPath, destPath })`
  - `cy.DeleteFile(filePath)` / `cy.task('deleteAny', path)` / `cy.task('log', message)`

## Test Data Generation
```js
import Faker from 'faker'
const title = `CY_Test | ${Faker.hacker.phrase()}`   // always prefix with CY_Test |
const body  = Faker.lorem.paragraph()
const firstName = Faker.fake('{{name.firstName}}')
const lastName  = Faker.fake('{{name.firstName}}')
```
Always prefix generated names with `CY_Test |` for easy identification and cleanup.

When a nearby suite already uses a different cleanup-friendly prefix such as `CY_`, `CY-`, or `Cypress -`, prefer matching that local convention instead of mixing multiple new prefixes inside the same area.

## Intercepts for Response Validation
```js
cy.intercept('GET', 'api/v1/content*').as('contentCatalog')
cy.wait('@contentCatalog').then((xhr) => {
  expect(xhr.response.statusCode).to.eq(200)
  expect(xhr.response.body.response).to.be.an('array')
})
```

Pattern rules:
- Define the intercept before the UI action that triggers it.
- Prefer wildcards that match existing suite usage, for example `**/ideas*` or `**/content*`, instead of overconstraining URLs.
- Assert the response in the wait chain when the request outcome matters to the test.

## GraphQL Intercepts
`interceptGQLGlobal()` already runs globally — alias by operation name:
```js
cy.wait('@OperationName').then((xhr) => {
  expect(xhr.response.body.data).to.exist
})
```

Do not add duplicate `cy.intercept('POST', '/graphql')` blocks unless the test needs custom local behavior.

## Multi-Role Testing Pattern
```js
// Setup as admin, verify behavior as a lower-privileged role
before(() => {
  cy.login(Cypress.env('KAPOST_ADMIN_API_TOKEN'))
  // create data as admin
})

it('editor cannot access admin settings', () => {
  Cypress.session.clearAllSavedSessions()
  cy.loginUI('editor')
  cy.visit('/studio/settings')
  cy.get('[data-cy="forbidden-message"]').should('be.visible')
})
```

Role rules:
- `cy.loginAsRole()` expects uppercase role names.
- Use API-token login for setup unless the test explicitly validates the login UI.
- Clear saved sessions before switching roles in the same spec.

## Smoke vs Parallel Placement
- **Smoke** (`cypress/e2e/smoke/`): critical happy paths only, < 2 min per spec
- **Parallel** (`cypress/e2e/parallel/group-N/`): full regression, assigned to a specific Jenkins group
- **Kapost feature folders** (`cypress/e2e/kapost/`): feature-organized specs, page object support, and verification work
- Decide placement before writing — do not put regression-heavy specs in smoke/
- Match the nearest folder's existing organization and naming before creating a new spec

## Environment-Aware Authoring
- Do not hardcode content type IDs, saved fixture IDs, or environment-specific URLs inside tests.
- Use helpers from `globalTestData.js` when reusing shared environment-aware data.
- Use `contentRegistry.js` as the source of truth for environment-group mappings and content expectations.
- Be aware that logical groups can be mapped from base URLs like `NEWTEST`, `TEST`, `PRODTEST`, and `SMOKETEST`.

## Common Mistakes to Avoid
- Do NOT use hardcoded `cy.wait(ms)` > 3000ms — use `cy.intercept` aliases
- Do NOT access `Cypress.env()` at `describe()` block level — only inside `it()`, `before()`, `beforeEach()`
- Do NOT leave git conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) in spec files
- Do NOT use `describe.skip()` for permanent exclusions — fix or delete the test
- Always call `cy.logout()` or `Cypress.session.clearAllSavedSessions()` between multi-user role tests
- Do NOT use `cy.loginUI(...)` for normal setup speed paths; use API token login unless the test explicitly validates UI sign-in
- Do NOT hardcode content type IDs — always derive them from `globalTestData.js` or `contentRegistry.js`
- Do NOT assume every page object is a singleton or every page object is a class — mirror the neighboring usage for that file
- Do NOT reimplement plugin tasks with inline Node workarounds inside specs when a Cypress task already exists
- Do NOT normalize credentials, tokens, or email secrets from config files into new test code
