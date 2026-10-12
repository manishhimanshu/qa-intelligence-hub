# Gallery Natural Language Search (NLS) — QA Feature Documentation

RAG tags: gallery, gallery natural language search, natural language search, NLS, NLS search, search filters, semantic search

> **Evidence labels:** “Compiler contract” describes intended query interpretation, not proof of end-to-end runtime behavior. “QA observation” records behavior seen in the supplied test workbook. “Known issue” and “Product question” are not expected behavior. Confirm runtime-sensitive behavior in the Gallery UI before treating it as verified.

## 1. Purpose

Gallery Natural Language Search (NLS) allows users to search content in a Gallery collection using natural-language queries instead of manually selecting filters.

The search experience can interpret a user's query into:

- **Hard/structured filters** — attributes that can be resolved to known content metadata.
- **Semantic/topic search text** — the remaining natural-language intent used to find relevant content.
- **Ranking/sorting intent** — when the query asks for relevance, latest/oldest content, or when multiple filter conditions are combined.
- **A user-facing search summary** — explains how the query was interpreted and what filters/search criteria were applied.

The primary QA focus is the **Gallery UI search experience**, not direct API payload validation.

---

## 2. Search Processing Model

Conceptually, NLS follows this flow:

**User query → Query interpretation → Structured filters + semantic search text → Search results → Ranking/sorting → Search summary**

The compiler asks Claude for high-level filter intents, residual semantic text, optional sort intents, and a summary. The server resolves names and builds Elasticsearch clauses; the model does not generate Elasticsearch DSL or system IDs. The compiled query is cached per query, newsroom, current user, model, and date for five minutes. Search results themselves are not described as cached by this compiler.

### 2.1 Query interpretation

The query interpreter identifies known entities and conditions in the user's natural-language request.

Examples:

- `content with content type as blog post`
  - Structured filter: `Content Type = Blog Post`
  - No topic search.

- `content added to initiative marketing optimization`
  - Structured filter: `Initiative = marketing optimization`
  - No topic search.

- `blog posts about veeva`
  - Structured filter: `Content Type = Blog Post`
  - Semantic/topic search: `veeva`.

- `show me this quarter's Q4 email campaign assets for enterprise accounts`
  - Date filter + content type filter.
  - Remaining intent is used as semantic/topic search.

### 2.2 Filter-only searches

When the query can be fully represented using structured filters, the search summary normally states:

> No topic search — results determined by filters.

Examples include:

- published content
- content with tasks
- content with no initiatives
- content created by a specific author
- content of a specific content type
- content associated with a specific initiative
- downloadable content

### 2.3 Hybrid searches

A hybrid query contains both structured filters and semantic/topic intent.

Example:

`white papers by Jane Smith about AI`

Expected interpretation:

- Content Type = White Paper
- Author = Jane Smith
- Semantic/topic search = AI

The structured filters narrow the candidate set and semantic search/ranking determines relevance within that set.

---

# 3. Searchable Content Dimensions

## 3.1 Topic / Semantic Search

Topic-only queries search the content corpus semantically.

Examples:

- `oncology launch plan`
- `digital marketing`
- `patient education`
- `veeva integration`
- `B2B campaign examples targeting CFOs`
- `content addressing budget objections`

Semantic search should not require an exact keyword match. Conceptually related content may be returned.
The compiler sends residual topic text to BM25 and vector search. Semantic similarity is bounded by indexed content and ranking quality; it does not guarantee that every conceptually related item will appear.

Example:

`Find B2B campaign examples targeting CFOs`

The QA sheet notes that semantic search can surface content conceptually related to terms such as C-suite financial decision makers even when the exact words are not present.

### QA expectation

For topic-only searches:

- Results should be relevant to the user's intent.
- The most relevant results should appear first.
- The search should not unexpectedly apply unrelated structured filters.
- Pagination should preserve the same search intent.

---

## 3.2 Compiler filter inventory

The compiler schema includes these filter dimensions. A dimension may still depend on newsroom data and backend resolution; this inventory describes available intents, not verified runtime coverage:

- **Named content metadata:** content type, author, creator, task assignee, task name, persona, initiative, custom field, workflow stage, progress stage, content state, stage, category, channel, collection, and title.
- **Ranges:** built-in date fields and word count.
- **Presence/absence:** relationships and fields such as author, creator, tasks, initiatives, attachments, content file, published URLs, collections, and custom fields.
- **Gallery and file attributes:** pinned, favorited, downloadable/shareable/bundleable flags, file type, and body type.

Only use a named-value filter when the query clearly signals that dimension. The compiler keeps unclear terms as topic text rather than guessing a filter.

---

# 4. Author / Creator Search

NLS can filter content using author information.

Examples:

- `content by Jane Smith`
- `created by Jane Smith`
- `Jane Smith's content`
- `content authored by either Steve Rogers or Manish Himanshu`
- `content with an author`
- `content with no author`

Supported concepts observed in testing:

- Has author
- No author
- Specific author
- Multiple authors
- OR between authors
- Unknown/non-existent author
- Author changes/removal
- Multiple users with similar names
- Creator vs author distinction

### Important QA distinction

An author query should resolve the author filter when the person can be identified. An unknown author should not silently become a valid structured author filter.

**Compiler contract:** author and creator filters use people in newsroom context. Unknown names remain search text rather than being resolved to a person. The search summary should make a clear near-miss visible when a query strongly signals an author filter but no matching member exists.

---

# 5. Content Type (CT)

NLS can resolve content type names and some variations/partial natural-language references.

Examples:

- `content with content type as blog post`
- `content with blog content type`
- `content with content type as blogging post`

Observed behavior:

**Compiler contract and QA observations:**

- Content type filters should use a content type name present in newsroom context.
- QA cases report that some partial or misspelled names resolve to a known type; validate these aliases rather than assuming arbitrary semantic matching.
- If a type cannot be resolved, the unmatched term should remain searchable as topic text rather than becoming a fabricated filter.

Example:

`content with content type as mechanical`

If `mechanical` is not a known content type, the query may be treated as a search for the term rather than a Content Type filter.

### QA expectation

Do not assume every noun in a query is a content type. Verify the query interpretation and applied filter.

---

# 6. Initiative Search
NLS supports initiative-based filtering.

Examples:

- `content added to initiative marketing optimization`
- `content added to initiatives`
- `content which are not added to initiatives`
- `content added to initiative marketing optimization and campaign May to July product launch`

Supported concepts observed:

- Has initiatives
- No initiatives
- Specific initiative
- Partial initiative title
- Multiple initiatives
- OR between initiatives
- AND/multiple-condition relevance
- Unknown initiative fallback

### Partial initiative matching
### Partial initiative matching

**Compiler contract:** the backend fuzzy-matches the queried phrase against configured initiative names and may match more than one initiative.

Example:

`content added to initiative marketing`

may resolve to an existing initiative such as:

`marketing optimization`

### Unknown initiatives

**Compiler contract:** pass the initiative name or keyword through as written. The backend fuzzy-matches it against configured initiative names and may apply the filter to more than one match. If the backend cannot resolve the value, the compiler returns the unresolved term to semantic search instead of silently dropping it. The summary should distinguish keyword fallback from a resolved initiative filter.

**QA observation:** workbook cases include partial initiative matching and inconsistent results for unknown or near-match names. Verify the actual applied filters and result set; do not assume fuzzy matching always selects one specific initiative.

### Multiple initiatives

When a query references multiple initiatives, the intended result set can include:

- Content matching both initiatives
- Content matching only the first initiative
- Content matching only the second initiative

When the search interpretation says that content matching both should be ranked first, the result ordering must reflect that interpretation.

---

# 7. Persona Search

Persona can be used as a structured filter.

Examples:

- `content for development persona`
- `content for development and testing persona`
- `developer persona content`
- `content for Marketing Manager`

For multiple personas, the search may describe the expected ordering as:

1. Content matching both personas
2. Content matching only one persona

The exact ranking behavior should be validated against the search summary.

---

# 8. Custom Field (CF) Search

NLS supports custom-field-based filtering.

Examples:

- `show me content having custom field internet url as https://csa.com`
- `show me content with persona manager or executives`
- `content tagged Technology`
- `content labelled Healthcare`
- `Industry Technology`

## 8.1 Text custom fields

**QA observation:**
For a text-type custom field, the workbook reports reliable filtering when the query includes the field label and value. Treat this as a tested query pattern, not a universal rule for every field type.

Example:

`show me content having custom field Internet URL as https://csa.com`

resolves to:

`Internet URL = https://csa.com`

Other custom-field types (multiselect, dropdown) continue to work as before.

### Important limitation

Searching only the text custom-field label may not be interpreted as an exact custom-field filter. It may become topic/semantic search.

**Observed versus intended:** the workbook reports some incorrect-value cases falling back to topic search. The compiler excerpt says the backend should resolve the requested value and fall back to a field-exists filter if it cannot be resolved. Verify the applied filter and results at runtime.

---

## 8.2 Has Custom Fields / No Custom Fields

Supported concepts include:

- `content that have custom fields`
- `content that have no custom fields`
- `content that has custom field but value is empty`

**Documented query meaning:** generic “no custom fields” includes both content with no applicable custom fields and content whose custom-field values are all empty. For a named custom field, “empty” includes both a missing field and a present field with no value.

Examples:
- `show me contents with no custom fields`
- `show me contents where Personas is empty`
---

# 9. Status

NLS has distinct status dimensions; do not collapse them into one “status” concept:

- **Progress stage:** planned, in progress, or completed.
- **Workflow stage:** a named workflow stage and/or its state, such as review or completed review.
- **Content state:** published, unpublished, or archived (see Section 10).

Examples:

- planned
- completed
- in progress

Multiple values in one dimension are alternatives, not a requirement that one item simultaneously have every value. Documents matching more of the requested values may rank higher. Separate filter dimensions are combined with AND unless the query expresses a grouped OR.

Example:

`show contents which are planned and completed and in progress`

The interpretation can resolve to:

`Status = planned, completed, in progress`

QA should verify that the returned content belongs to the requested status set.

---

# 10. Published / Unpublished State

NLS supports published-state filtering.

Examples:

- `published content`
- `draft content`
- content published on a specific date
- content published today
- content published within the last week

Observed date interpretation examples:

- `show me content which was published on 21 august`
  - Published
  - Published date = 21 Aug 2026

- `show me content which was published today`
  - Published
  - Published date = current date

- `show me content published within last week`
  - Published
  - Published date range covering the previous week

### Important distinction

**Published state** and **content status** are separate concepts and should not be assumed to be interchangeable.

---

# 11. Date Searches


Examples from the compiler guidance and QA workbook include:

- today
- last week
- specific date
- this quarter
- last quarter
- next quarter
- date ranges

## Date custom fields

Date-type custom-field search is a specific area requiring product-scope confirmation.

Example custom field:

`Release Date`

Potential query types under discussion:

- `contents where the release date is in the year 2026`
- `contents where release date is in November 2026`
- `contents where the release date is in January`
- `contents where release date was last quarter`
- `contents where release date was last year`
- `contents where release date was last month`
- `contents where next release date falls in next quarter`
- `contents where release date is between January and December`

### Current QA observation

The workbook reports that some date-custom-field queries resolve only to field presence (`Has Release Date`) rather than the requested date condition. Date-type custom fields are not among the compiler's documented built-in date fields. Keep date-custom-field filtering as a product/runtime question; do not infer date comparisons from ordinary date filters. Relative dates on supported built-in fields are part of the compiler contract but still require end-to-end validation.

---

# 12. Content Body and File-Type Search

Keep these concepts separate:

- **File type:** extension/category of the primary content file, such as PDF, Excel, CSV, PPTX, or DOCX.
- **Attachment file type:** file type of a supporting attachment. The query must identify an attachment to scope the filter to attachments.
- **Body type:** content-type body format, such as HTML or no body. This is not the primary file extension.
- **File text search:** topical search over indexed text; it is not equivalent to a file-type filter.

Tested/considered file types include:

- PDF
- Excel
- CSV
- PPTX
- DOCX
- HTML
- Video and other supported file types

Examples:

- `content with pdf file added to body`
- `content with excel file`
- `content with csv file`
- `content with pptx file`
- `content with docx file`
- `content with HTML body`
- content with no body

### File content search

The workbook reports inconsistent results for some file formats and attachment cases; treat those as validation coverage, not a complete supported-format guarantee.

### Attachments

Attachments are separate from the primary content file. **Compiler contract:** use a file-type filter scoped to attachments when the query clearly refers to a supporting attachment; otherwise the file-type filter targets the primary content file. The compiler also distinguishes “no body” from “no content file.” Validate indexing and supported formats against the live Gallery implementation.

Examples:

- `content with pdf file attachment`
- `content having excel file attachment`
- `content with csv file attachment`
- `content with attachment added as a pptx file`
- `docx file attachment`
- content with no attachment

---

# 13. Content Body Revision / Content Type Changes

Revision and content-type changes are important for search-index correctness.

### Expected principle

Only the **current content represented on the Content Details page** should contribute to search.

If a file or HTML body is replaced or removed, content from the previous version should not remain searchable.

Example lifecycle:

`File-based content → File indexed → content type/body changes → old file no longer applicable`

After the change:

- Old file-specific keywords should no longer return the content.
- Current content should remain searchable.
- Old HTML body text should no longer be searchable after it is replaced/removed.

### QA regression coverage

The workbook marks stale file/body search after a content-type change as fixed. Keep this as regression coverage, not an open known issue: after indexing completes, old file/body text should no longer match and current content should remain searchable.

---

# 14. Tasks

NLS supports task-related filtering.

Examples:

- content with tasks
- content with no tasks
- content with a specific task name
- content with a task assigned to a specific user
- content with an upcoming/up-next task
- tasks due within a date range
- task deadline tomorrow

### Important task concepts

#### Has tasks

`content that has at least one task`

→ structured filter: Has Tasks

#### No tasks

`content which has no tasks`

→ structured filter: No Tasks

#### Exact task name
**Compiler contract:** a named task uses the task-name filter; “has tasks” is only for the existence of any task. Filtering by an exact task count (for example, exactly two tasks) is not a structured filter in the supplied compiler contract.

A query such as:

`list contents with task skills development`

should identify the specified task rather than simply returning all content that has any task.

#### Task assignee

Queries can identify task assignees.

Example:

`task tech talk assigned to Raj Roshan`

#### Up-next task

Example:

`content where up next task is kick off`

The expected behavior is to filter based on the task identified as the next/up-next task.

#### Task deadline

Date expressions can be applied to task deadlines.

Example:

`task deadline tomorrow`

---

# 15. Category and Stage

NLS can be used with category/stage-style metadata.

Examples:

- category Cardiology
- stage Awareness
- content in review stage
- content in approval stage
- content in editing stage

These should be interpreted as structured metadata filters when the referenced value exists.
Use a structured filter only when the referenced category or workflow-stage value is available and resolves. Progress stage, workflow stage, and content state are separate dimensions.

---

# 16. Presence / Absence Searches

NLS supports presence/absence concepts.

Examples:

- has initiatives
- no initiatives
- has tasks
- no tasks
- has custom fields
- no custom fields
- has author
- no author
- downloadable
- shareable

The important QA distinction is between **existence of a field/entity** and **the value of that field/entity**.

For example:

`has custom fields`

is not necessarily equivalent to:

`a particular custom field exists and is empty`.

For a specifically named custom field, check that field's label and value/existence; a generic custom-fields presence filter does not identify which field was requested.

---

# 17. Gallery Actions / Flags

NLS can filter based on Gallery-related attributes.

Supported/observed examples:

- downloadable content
- shareable content
- bundleable content
- favourite content
- pinned content

Examples:

`downloadable content`

→ Downloadable filter

`shareable content`

→ Shareable filter

`bundleable content`

→ Gallery can bundle

`show favourite contents`

→ Favorited

### Pinned vs favourite
Favorited searches may be scoped to the current user (“my favorites”), other users, or any user. Pinned and favorited are separate dimensions.

The terms should not automatically be treated as interchangeable.

The QA sheet observed that:

`pinned content`

was interpreted as a Pinned filter, while:

`show favourite contents`

was interpreted as Favorited.

---

# 18. Boolean / OR / AND Logic

**Compiler contract:** separate top-level filter dimensions are combined with AND. A grouped filter expresses OR or mixed logic. Multiple values in the same dimension form a value set (alternatives); results matching more of those values should rank higher. The word “and” between values of the same dimension does not require one document to match every value. Negation can exclude a leaf or an entire group.

Examples:

- `blog posts or white papers`
- `by Jane Smith or tagged Technology`
- `published content not by Jane Smith`
- `published and (blog posts or white papers)`
- `content added to initiative marketing optimization or content title is q4`

The query interpretation should make the logical relationship clear.

### OR

For:

`content added to initiative marketing optimization or content title is q4`

the expected result set is the union of:

- content in Marketing Optimization
- content with title matching Q4

If a content item matches both conditions, it should be ranked higher when the interpretation explicitly says so.

### AND

For multiple filters, all required conditions should be respected.
For different filter dimensions, all top-level conditions must be respected unless the query explicitly groups them with OR.

Example:

`Steve's or Manish's in-progress content about testing tools having task tech talk assigned to Raj Roshan with deadline tomorrow and initiative marketing optimization and Personas director or manager and published today`

This is a hybrid query containing:

- Author OR
- Content status
- Semantic topic
- Task name
- Task assignee
- Task deadline
- Initiative
- Custom field/persona OR
- Published state/date

---

# 19. Ranking and Sorting

Ranking is an important part of NLS behavior and must be distinguished from simple sorting.

## Relevance ranking

When the search summary says:

> matching both conditions ranked above those matching just one

the results should reflect that ordering.

Example:

Query:

`content which are added to initiative marketing optimization and campaign May to July product launch`

If:

- 7 contents belong to Marketing Optimization
- 3 contents belong to Campaign May to July Product Launch
- 1 content belongs to both

then there are **9 unique contents**.

Expected relevance ordering:

1. Content matching both initiatives
2. Remaining content matching one initiative

## Known ranking issue

Some multi-filter queries currently return results ordered by **Last Updated**, even when the search summary says content matching both conditions should appear first.
The compiler suppresses its default updated-date sort when a filter tree itself ranks matches. A mismatch between the summary and actual order is a result/query execution defect to validate, not the intended ranking rule.

This has been observed for combinations such as:

- Initiative + Initiative
- Initiative + Custom Field

Example:

`content which are added to initiative marketing optimization or personas in executive`

The filters may be correctly extracted:

- Marketing Optimization
- Personas: Executive

but the actual result ordering may still be Last Updated rather than condition-match relevance.

### QA rule

Use the summary as evidence of compiler interpretation, then compare applied filters, results, and ordering. The summary alone does not prove that the search executor applied the same logic.

---

# 20. Sorting Queries

Explicit sorting queries are different from relevance ranking. The compiler defines a default updated-date sort for ordinary filter-only searches, but omits that default when multi-value/group filters rank matches. An explicit user-requested sort may still determine the order.

Example:

`latest published content`

Expected interpretation:

- Published filter
- Sort by most recent publish date first

This is the workbook's expected interpretation. The compiler guidance maps generic “newest/latest” to updated-date sorting and “by publish date” to published-date sorting, so verify the interpreted date field for ambiguous queries.

Other possible sorting intents:

- most recent
- oldest
- latest published
- most recent oncology content

When the user explicitly requests a sort order, verify that the results follow that sort order.

---

# 21. Search Summary

The NLS UI presents an AI-generated interpretation/search summary.

The summary is useful for validating whether the query compiler understood the request.

Typical patterns:

### Filter-only

> Showing content associated with the 'marketing optimization' initiative. No topic search — results determined by filters.

### Hybrid

> Showing Email content created in Q3 2026. Ranked by relevance to 'campaign assets enterprise accounts'.

### Multi-condition

> Showing content that is either associated with the 'marketing optimization' initiative or has the Personas custom field set to 'executive', matching both criteria ranked above those matching just one.

QA should compare:

1. User query
2. Search summary
3. Applied filters
4. Actual results
5. Result ordering

A defect can occur at any one of these levels.

---

# 22. Query Compiler QA Model

For manual test design, evaluate a query through these layers:

### Layer 1 — Intent recognition

Did NLS understand what the user is asking?

### Layer 2 — Entity resolution

Did NLS correctly resolve:

- author
- content type
- initiative
- persona
- custom field
- task
- task assignee
- status
- date
- Gallery flag

### Layer 3 — Filter extraction

Were the correct hard filters applied?

### Layer 4 — Semantic text

If part of the query is topical/semantic, was the remaining intent preserved?

### Layer 5 — Result filtering

Do returned contents satisfy the structured conditions?

### Layer 6 — Ranking

Are results ordered according to the stated relevance/sort intent?

### Layer 7 — Pagination

Does pagination continue to respect the same query/filter/ranking logic?

### Layer 8 — UI interpretation

Does the search summary accurately describe what NLS actually searched?

---

# 23. Pagination and Result Consistency

For any NLS query that returns enough results for multiple pages:

- Page 1 should contain the most relevant results according to the query.
- Moving to subsequent pages should not introduce results that violate the filters.
- The ordering should remain consistent across pages.
- Result count and displayed results should remain consistent after pagination.
- Changing page should not reset the NLS interpretation.

---

# 24. Permissions and Visibility

Search results should respect the content the current user is allowed to view.

Security, newsroom scope, and access-control filters are applied outside the query compiler. Validate access boundaries in the end-to-end Gallery experience; do not expect Claude/compiler filter intents to implement authorization.

NLS should not expose content that is outside the user's accessible Gallery/content scope simply because it matches the natural-language query.

When testing search filters, validate both:

- correctness of the query
- visibility/permission boundaries

---

# 25. Search Index Freshness

NLS depends on indexed content. Changes to content can therefore expose stale-index behavior.

Important regression scenarios:

- add a new file revision
- remove a file
- replace a file
- change content type
- remove an HTML body
- change custom-field values
- remove a custom field by changing content type
- update initiative
- update persona
- change author
- change task
- delete an attachment
- publish/unpublish content

### Expected principle

After indexing is complete, search should represent the **current state** of the content and should not retain obsolete data.

---

# 26. AI Summary and File Revisions

The AI-generated content summary is separate from NLS query interpretation but is relevant to current Gallery content behavior.

A known behavior is that the AI summary is cached for approximately **15 minutes**.

When a new file revision is added:

- the existing cached summary may continue to be returned until the cache expires;
- therefore, the summary may temporarily represent the previous revision.

### Expected product behavior under discussion

Ideally, adding a new file revision should invalidate or refresh the existing AI-summary cache so the summary represents the latest revision.

Reducing the cache TTL is a possible implementation approach, but cache invalidation on content/revision change is the stronger behavioral expectation.

---

# 27. Gallery NLS Content Preview

NLS search results include a content preview.

The preview should:

- show the relevant content information clearly;
- remain readable for long content type names;
- avoid overlap between content type and other metadata;
- preserve the current Gallery visual layout.

### Known UI issue

Long content type names can appear in full and overlap other preview details.

Expected behavior:

- long content type names should be truncated or wrapped appropriately;
- they should not overlap other UI elements;
- the complete name should remain discoverable where appropriate, such as through a tooltip.

---

# 28. Known Issues / Important QA Findings

The workbook records the following findings. Its status labels may be stale; recheck them before reporting a current defect. These are not expected product behaviors.

### Search and ranking findings
- Some multi-condition or OR queries have returned incomplete results or Last Updated ordering even when the interpretation indicates match-strength ranking.
- Validate filters, result membership, and ordering independently; compiler summaries do not prove executor behavior.

### Custom-field findings
- The workbook reports reliable text-field filtering with the field label and value, but also contains cases where values fall back to topic search. Validate against the current implementation.
- Some date-custom-field queries returned only field presence (`Has <date CF>`); date comparisons on custom fields remain a scope/runtime question.
- The documented query meaning intentionally treats generic “no custom fields” as including no applicable fields and all-empty values. For a named field, “empty” includes missing and present-but-empty.
- Stale custom-field values after content-type changes are marked fixed in the supplied QA notes; retain as regression coverage.

### File and index findings
- File-type and attachment results vary across workbook cases; verify supported formats and current indexed behavior.
- Stale file/body text after a content-type or body change is marked fixed in the supplied QA notes; retain as regression coverage.
- After indexing completes, results should represent current content rather than obsolete revisions.

### Adjacent Gallery findings
- The workbook notes possible AI-summary cache delay and long content-type-name overlap in previews. These concern adjacent Gallery features, not NLS query compilation.

### Product scope questions
- Exact task-count and initiative-count queries are not structured filter dimensions in the supplied compiler contract.
- Analytics such as “high-performing,” conversion rates, and CRM sharing events are not represented by the documented search fields.
- Product confirmation is still needed for date comparisons on custom fields and any unsupported filter semantics.

---

# 29. Test Data Requirements

A useful NLS test environment should contain content covering:

## Content
- Multiple content types
- File-based content types
- HTML content
- Content with no body
- Multiple file revisions
- Deleted/replaced files
- Published and unpublished content

## Authors
- Multiple authors
- Multiple users with similar names
- Content with no author
- Content where creator and author differ

## Initiatives
- At least 3 initiatives
- Similar/partial initiative names
- Content belonging to one initiative
- Content belonging to multiple initiatives
- Content with no initiative

Example dataset:

- Marketing Optimization
- Marketing Refinement
- Campaign May to July Product Launch

## Personas
- Development
- Testing
- Executive
- Director
- Manager

Include content matching:
- one persona
- multiple personas
- no persona

## Custom fields
Include:
- Text
- URL
- Date
- Other supported CF types

For each CF type include:
- populated value
- empty value
- missing/not applicable value

## Tasks
Include:
- no tasks
- one task
- multiple tasks
- exact task names
- similar task names
- different assignees
- upcoming/up-next tasks
- different deadlines

## Gallery flags
Include:
- downloadable
- shareable
- bundleable
- favourited
- pinned
- not marked with each flag

---

# 30. Recommended Manual Test Case Structure

For NLS test cases, use the following structure:

### Test Scenario
Describe the behavior being validated.

### Query
Use the exact natural-language query.

### Test Data / Preconditions
Describe the minimum data required.

### Expected Query Interpretation
What should NLS understand from the query?

### Expected Filters
Which structured filters should be applied?

### Expected Semantic Intent
What should remain as topic/semantic search text, if applicable?

### Expected Results
What content should appear?

### Expected Ranking
How should matching results be ordered?

### Expected Search Summary
What should the user-facing summary communicate?

### Negative Validation
Verify that content that does not satisfy the query is not returned.

This structure is preferable to creating a separate test case for every small wording variation unless the variation tests a distinct compiler behavior.

---

# 31. High-Value NLS Test Categories

For comprehensive manual coverage, prioritize:

1. Pure semantic/topic search
2. Single hard filter
3. Unknown entity/value fallback
4. Partial entity resolution
5. Exact custom-field label + value
6. Date and relative-date interpretation
7. File type/body search
8. Attachment search
9. Task name and task assignee
10. Up-next task
11. Initiative filtering
12. Persona filtering
13. Author filtering
14. Status filtering
15. Published-state filtering
16. Presence/absence filters
17. Gallery flags
18. AND combinations
19. OR combinations
20. AND + OR combinations
21. Hybrid filter + semantic search
22. Relevance ranking
23. Explicit sorting
24. Pagination
25. Index freshness after content changes
26. Permission/visibility behavior
27. UI preview behavior
28. Zero-result behavior
29. Complex multi-filter queries

---

# 32. Representative Queries

## Semantic

- `oncology launch plan`
- `digital marketing`
- `patient education`
- `B2B campaign examples targeting CFOs`

## Content Type

- `blog posts`
- `white papers about AI`
- `content with content type as blog post`

## Author

- `content by Jane Smith`
- `Jane Smith's content`
- `Steve's or Manish's content about testing tools`

## Initiative

- `content added to initiative marketing optimization`
- `content added to initiative marketing`
- `content added to initiative marketing optimization or campaign May to July product launch`

## Persona

- `content for development persona`
- `content for development and testing persona`

## Custom Field

- `show me content having custom field Internet URL as https://csa.com`
- `show me content with persona manager or executives`

## Status

- `show contents which are in progress`
- `show contents which are planned or completed`

## Published

- `published content`
- `content published today`
- `content published within last week`

## Tasks

- `content with tasks`
- `content with no tasks`
- `content with task skills development`
- `content where up next task is kick off`
- `content with tasks due this week`

## Gallery

- `downloadable content`
- `shareable content`
- `bundleable content`
- `show favourite contents`

## Hybrid

- `white papers by Jane Smith about AI`
- `published blog posts about oncology`
- `Q4 email campaign assets for enterprise accounts`

## Boolean

- `blog posts or white papers`
- `published content not by Jane Smith`
- `published and blog posts or white papers`

---

# 33. QA Principle

For every NLS query, validate the complete chain:

**What the user asked → what NLS understood → what filters were applied → what semantic intent remained → which results were returned → how results were ranked → what the UI summary says.**

A search should not be considered correct only because the filter extraction looks correct. The final result set and ordering must also match the interpreted intent.

---

# 34. Important Terminology

- **NLS** — Natural Language Search
- **CT** — Content Type
- **CF** — Custom Field
- **Hard filter / structured filter** — A filter applied against a known structured content attribute.
- **Semantic search / topic search** — Search based on the meaning or topical intent of the query.
- **Hybrid search** — A query using both structured filters and semantic search.
- **Query interpretation** — NLS's explanation of how it understood the user's query.
- **Search summary** — User-facing explanation of the interpreted search.
- **Revision** — A new version of a content file/body.
- **Gallery Preview** — The content representation selected for preview in Gallery.
- **Ranking** — Ordering results according to relevance or match strength.
- **Sorting** — Explicit ordering such as newest/oldest/latest published.

---

# 35. RAG Usage Guidance

This file is product/QA reference context, not a substitute for the requirements of a specific Jira story. When retrieved for QA work:

1. For Jira test generation, call `qa-hub/get_story_context` first and surface source warnings. Follow source precedence: Acceptance Criteria; otherwise Steps to Reproduce; otherwise description; otherwise summary. This document is supporting feature context and must not expand story scope.
2. Use feature/product knowledge and role-permission context to interpret requirements. Call `qa-hub/get_more_story_context` only for a specific unresolved source that could change interpretation or test design; do not fetch every source by default.
3. Use `qa-hub/get_testrail_automation_context` for duplicate detection or examples of coverage for story-supported behavior, never as a source of new requirements.
4. Use `qa-hub/get_automation_context` only for Cypress automation work. Fetch additional pages/chunks only when the relevant excerpt is incomplete.
5. Cite exact Jira source text for requirements in generated manual cases. Use this document as supporting context, not as a substitute for requirement evidence.
6. Treat the **Compiler contract** as intended query interpretation; verify runtime behavior through the Gallery UI before calling it confirmed.
7. Treat **QA observations**, **Known issues**, and **Product questions** as evidence/status notes, not expected behavior. A “fixed” note means regression coverage unless current evidence says otherwise.
8. Generate tests around distinct search behaviors, not wording variations. For complex queries, validate intent, applied filters, result membership, ordering, summary, and pagination.
9. Prefer end-to-end Gallery UI validation over assertions on internal compiler payloads unless the story explicitly requires compiler-level coverage.
10. Do not assume a defect, stale observation, or test interpretation is intended behavior merely because it appears in an existing case.

---

## Source and Scope Notes

This documentation was consolidated from:

1. The supplied `NLS - gallery search test case document.xlsx`, including its author, status, body, attachments, tasks, custom fields, publish/unpublish, additional fields, miscellaneous, and multiple-filter test areas.
2. The supplied `NlQueryCompilerService` implementation excerpt, used to describe compiler intent, filter dimensions, grouping, fallback, and sorting rules.
3. The NLS QA behavior and defect observations established during the current QA discussion.

Where sources disagree, the compiler excerpt describes intended query compilation, the workbook describes observed QA behavior, and neither alone proves end-to-end behavior. Validate discrepancies in the Gallery UI and retain unresolved questions as questions rather than asserting an answer.
