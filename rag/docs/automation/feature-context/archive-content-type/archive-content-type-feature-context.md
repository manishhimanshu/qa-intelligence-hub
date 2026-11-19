# Archive Content Type Feature Context (Execution-Focused)

## Purpose
This document captures current automation patterns for archive and unarchive behavior of Content Types, including cross-module impact checks.

## Scope
- Focused on Cypress implementation details.
- Includes related specs, page objects, commands, and per-spec data lifecycle.
- Excludes any recommendation to use separate global setup/teardown specs.

## Spec Map
Primary archive suite location:
- `cypress/e2e/parallel/group-1/archival-content-type/`

| Spec | Intent | Notes |
|---|---|---|
| `archiveTheContentType.cy.js` | Archive from Content Type settings and validate filters/state | Core archive list behavior.
| `unArchiveTheContentType.cy.js` | Unarchive and verify dropdown visibility across multiple modules | Broad integration verification.
| `unArchiveTheContentType-1.cy.js` | Unarchive and archive-icon validation variant | Includes activity checks.
| `UnArchiveTheContentType-2.cy.js` | Unarchive variant with archive icon checks in additional areas | Similar scope, different assertions.
| `hideArchiveContentTypeInFilters.cy.js` | Archived content type hidden from create/select dropdowns | Cross-module hiding checks.
| `displayArchiveIcon.cy.js` | Archived icon visibility in ideas-related areas | Icon and tooltip behavior.
| `displayArchiveIcon-1.cy.js` | Archived icon visibility in initiative content tab and related flows | Additional icon coverage.
| `duplicateTheArchiveContentType.cy.js` | Duplicate flow when source type is archived | Warning and fallback content type behavior.
| `LocalizeTheArchiveContentType.cy.js` | Localize flow when source type is archived | Archive warning and localization behavior.
| `archivedContentTypeInContentCatalogue.cy.js` | Bulk duplicate from content catalogue with archived type exclusions | Archived items skipped/disabled.
| `bulkDuplicateTheArchiveContentTypeInInitaitiveCatalogue.cy.js` | Initiative catalogue bulk duplicate excludes archived-type content | Duplicate warning flow.
| `bulkDuplicateTheArchiveContentTypeInInitaitiveDetail.cy.js` | Initiative detail bulk duplicate excludes archived-type content | Similar exclusion in detail view.
| `approveOptionForArchiveContentTypeInIdea.cy.js` | Approve disabled for ideas linked to archived type | Includes bulk mixed warning.
| `approveOptionForArchiveContentTypeInInitiativeIdea.cy.js` | Approve disabled for initiative-idea tab linked to archived type | Initiative-context variant.
| `exportArchiveContentType.cy.js` | Export behavior for archived-type content from catalogue | CSV-related assertions.

## Page Object Map
Primary page objects used repeatedly:
- `cypress/e2e/kapost/pageObjects/settingsPages/contentTypePage.cy.js`
  - Core archive/unarchive actions: `archiveContentTypeByName(...)`, `unarchiveContentType(...)`
  - Filter/state assertions and archived action button assertions
- `cypress/e2e/kapost/pageObjects/contentPages/content.cy.js`
  - Content details checks for archived/unarchived type availability
- `cypress/e2e/kapost/pageObjects/contentPages/contentCatalogue.cy.js`
  - Catalogue selection and duplicate warning/assertions
- `cypress/e2e/kapost/pageObjects/ideasPages/ideaCataloguePage.cy.js`
- `cypress/e2e/kapost/pageObjects/ideasPages/ideaDetailsPage.cy.js`
- `cypress/e2e/kapost/pageObjects/initiative-pages/initiatives.cy.js`
- `cypress/e2e/kapost/pageObjects/initiative-pages/initiativeCatalogue.cy.js`
- `cypress/e2e/kapost/pageObjects/memberActivity/memberActivityPage.cy.js`
- `cypress/e2e/kapost/pageObjects/settingsPages/customFieldPage.cy.js`
- `cypress/e2e/kapost/pageObjects/settingsPages/localizationPage.cy.js`
- `cypress/e2e/kapost/pageObjects/settingsPages/crowdsourcingPage.cy.js`
- `cypress/e2e/kapost/pageObjects/settingsPages/initiativeTypeTemplatePage.cy.js`
- `cypress/e2e/kapost/pageObjects/calenderPageObjects/calenderPage.cy.js`
- `cypress/e2e/kapost/pageObjects/canvas/canvasPage.cy.js`
- `cypress/e2e/kapost/pageObjects/galleryPageObjects/galleryPageObjects.cy.js`
- `cypress/e2e/kapost/pageObjects/taskPages/taskCataloguePage.cy.js`

## Custom Command Usage
Command definitions are in `cypress/support/commands.js`.

Archive-content-type setup/cleanup commands:
- `createContentType(contentBodyType = 'html')`
  - Creates content type with generated name pattern `Cy Content Type | ...`
  - Returns content type response object with `id`, `display_name`, etc.
- `deleteContentType(contentTypeId)`
  - Deletes content type by id via API
- `createContentAPI({ createContentBody = true, contentTypeName = null, contentName = null })`
  - Creates content associated with given content type display name
- `deleteContentItem(contentId)`
  - Deletes created content item by id

Archive-adjacent commands used in idea-based archive scenarios:
- `createIdeaAPI({ createIdeaBody = true, contentTypeName = null })`
- `submitIdeaAPI(ideaId)`
- `deleteIdea(id)`
- `createInitiativeApi(name, options = {})`

## Test Data Lifecycle (Per Spec/Context)
Observed default archive suite lifecycle:
1. `before()`:
   - Login as admin token
   - Create archived and active content types with `createContentType()`
   - Create related content/idea/initiative data as needed per scenario
   - Archive target content type using `contentTypePage.archiveContentTypeByName(...)`
2. `beforeEach()`:
   - Login and navigate to test-specific module page
3. `after()`:
   - Cleanup dependent entities first (ideas/content)
   - Cleanup content types last (`deleteContentType(...)`)

Common cleanup order rule:
- Delete ideas and content items before deleting content types to avoid dependency issues.

Naming patterns observed:
- Content types: generated by `createContentType()` (`Cy Content Type | ...`)
- Content titles: generated by `createContentAPI()` (`Cypress Title | ...` unless overridden)
- Idea titles: generated by `createIdeaAPI()` (`Cypress Generated Title | ...` unless overridden)

## Risks and Gaps
- Role coverage gap: archive tests are predominantly admin-role oriented.
- Selector brittleness: several page object interactions depend on complex CSS and tooltip selectors.
- Timing fragility: some specs use static waits in flows where polling/intercepts would be more robust.
- Duplicate scope overlap: multiple unarchive variants cover similar behavior; maintenance overhead risk.
- Integration blind spots: not all downstream modules are consistently asserted in every archive/unarchive variant.

## Reusable Authoring Pattern
For new archive-content-type tests:
- Build all required entities in same spec/context `before()`.
- Explicitly archive/unarchive via `contentTypePage` methods after setup.
- Assert module-specific behavior using module page objects.
- Cleanup dependencies in `after()` in strict order: ideas/content first, content types last.
- Keep all data lifecycle local to the owning spec or context.

## Source References
- `cypress/e2e/parallel/group-1/archival-content-type/archiveTheContentType.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/unArchiveTheContentType.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/unArchiveTheContentType-1.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/UnArchiveTheContentType-2.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/hideArchiveContentTypeInFilters.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/displayArchiveIcon.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/displayArchiveIcon-1.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/duplicateTheArchiveContentType.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/LocalizeTheArchiveContentType.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/archivedContentTypeInContentCatalogue.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/bulkDuplicateTheArchiveContentTypeInInitaitiveCatalogue.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/bulkDuplicateTheArchiveContentTypeInInitaitiveDetail.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/approveOptionForArchiveContentTypeInIdea.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/approveOptionForArchiveContentTypeInInitiativeIdea.cy.js`
- `cypress/e2e/parallel/group-1/archival-content-type/exportArchiveContentType.cy.js`
- `cypress/e2e/kapost/pageObjects/settingsPages/contentTypePage.cy.js`
- `cypress/support/commands.js`
