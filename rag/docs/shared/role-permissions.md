# Kapost Role Permissions

## Universal Role Rules

These rules apply across ALL features and modules. Every test case involving roles must be consistent with these baseline permissions.

### Role Hierarchy (highest to lowest)
Admin > Editor > Contributor > Consumer

### Object-Level Access (Manage Access)

In addition to role-based permissions, every content item and initiative has **object-level access** that is granted per-user by the item owner or an Admin. This is independent of role and creates a 2D permission model: **Role × Access Level**.

There are three access levels:
- **Owner access** — the user who created the item, or who has been explicitly made an owner. Owners have full control over the item.
- **Edit access** — explicitly granted by owner or user having edit access. User can read and modify the item but cannot delete it or transfer ownership but can provide edit or view access to other users.
- **View access** — explicitly granted by owner or user having edit access. User can read the item only. Cannot modify anything.

#### How Role × Access Level interact (used only for interaction with contents and initiatives)

| Role | Owner access | Edit access | View access | No access |
|---|---|---|---|---|
| **Admin** | Full control (edit + delete + manage access) | Can edit this item — CANNOT delete | Read only — cannot edit | Cannot see the item at all |
| **Editor** | Full control (edit + delete + manage access) | Can edit this item — CANNOT delete | Read only — cannot edit | Cannot see the item at all |
| **Contributor** | Can edit and delete own item | Can edit this item — CANNOT delete | Read only — cannot edit | Cannot see the item at all |
| **Consumer** | N/A — Consumer can only access Gallery (no content or initiative access) | N/A | N/A — Consumer cannot access content or initiatives | N/A — Consumer cannot access content or initiatives |

#### Critical rules for test case generation (used for interaction with contents and initiatives)
- **Admin does NOT bypass object-level access** — Admin behaves like Editor: access level (Owner/Edit/View) restricts what Admin can do on a specific item, just as it does for Editor
- **Admin + Owner access** = full control (edit + delete + manage access on that item)
- **Admin + Edit access** = can edit the item but CANNOT delete it
- **Admin + View access** = read only — Admin cannot edit or delete the item
- **Admin + No access** = cannot see the item at all — it does not appear in lists, search, or direct URL
- **Editor + Owner access** = full control (edit + delete + manage access on that item)
- **Editor + Edit access** = can edit the item but CANNOT delete it
- **Editor + View access** = read only — edit controls are hidden in the UI
- **Editor + No access** = cannot see the item at all — it does not appear in lists, search, or direct URL
- **Contributor + Owner access** = can edit AND delete the item (this is the only case a Contributor can delete)
- **Contributor + Edit access** = can edit but CANNOT delete
- **Contributor + View access** = read only — edit controls are hidden in the UI
- **Contributor + No access** = cannot see the item at all — it does not appear in lists, search, or direct URL
- **Consumer** = can ONLY access Gallery — has no access to content items or initiatives regardless of access level

#### Precondition patterns for test cases involving access levels (used mainly for interaction with contents and initiatives)
Always specify BOTH the role AND the access level in test preconditions:
- "Logged in as Admin who is the OWNER of the content item"
- "Logged in as Admin with EDIT access (not owner) on the content item"
- "Logged in as Admin with VIEW access only on the content item"
- "Logged in as Editor who is the OWNER of the content item"
- "Logged in as Editor with EDIT access (not owner) on the content item"
- "Logged in as Editor with VIEW access only on the content item"
- "Logged in as Contributor who is the OWNER of the content item"
- "Logged in as Contributor with EDIT access (not owner) on the content item"
- "Logged in as Contributor with VIEW access only on the content item"
- "Logged in as Consumer with VIEW access on the published content item"

#### Access level test scenarios that MUST be covered for any content/initiative feature
1. Owner (any role — Admin/Editor/Contributor) performs edit → should succeed
2. Owner (any role) performs delete → should succeed
3. User with edit access (Admin/Editor/Contributor) edits the item → should succeed
4. User with edit access (Admin/Editor/Contributor) attempts delete → should fail (403 or control hidden)
5. User with view access (Admin/Editor/Contributor) attempts edit → should fail (edit controls hidden or 403)
6. User with view access (Admin/Editor/Contributor) attempts delete → should fail
7. User with no access attempts to view the item → item must not appear in lists, search, OR direct URL access (for any role)
8. Owner transfers ownership to another user → original owner loses owner privileges
9. Owner grants/revokes edit or view access → affected user's permissions update immediately
10. User with edit access grants/revokes edit or view access → affected user's permissions update immediately

### Universal capabilities by role

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| View any published content | ✅ | ✅ | ✅ | ❌ (Consumer cannot access content — Gallery only) |
| Create new content | ✅ | ✅ | ✅ | ❌ |
| Edit own content (owner) | ✅ | ✅ | ✅ | ❌ |
| Edit others' content (edit access granted) | ✅ | ✅ | ✅ | ❌ |
| Edit others' content (view access or no access) | ❌ | ❌ | ❌ | ❌ |
| Delete own content (owner) | ✅ | ✅ | ✅ | ❌ |
| Delete others' content (edit access, not owner) | ❌ | ❌ | ❌ | ❌ |
| Manage access (grant/revoke) on own item | ✅ | ✅ | ✅ | ❌ |
| Manage access on others' items | ✅(if already having edit access) | ✅(if already having edit access) | ✅(if already having edit access)| ❌ |
| Publish content | ✅ | ✅ | ✅ | ❌ |
| Manage user accounts | ✅ | ❌ | ❌ | ❌ |
| Change workspace settings | ✅ | ❌ | ❌ | ❌ |
| Manage integrations | ✅ | ❌ | ❌ | ❌ |
| Access all reporting/analytics | ✅(which are in kapost->settings) | ❌ | ❌ | ❌ |
| Export data | ✅(eg, export content/initiative/idea catalogues) | ✅(eg, export content/initiative/idea catalogues) | ✅(eg, export content/initiative/idea catalogues) | ❌ |

### Expected error behaviour for unauthorised actions
- Consumer or Contributor attempting a restricted action: UI element is hidden OR a 403 error is shown
- No role can perform actions outside their tier without an explicit privilege escalation by Admin
- API requests from restricted roles must return HTTP 403 with a meaningful error message
- When access level restricts an action, the UI must hide the control (not just disable it) to avoid confusing the user

---

## Application Module Overview

Kapost has four main application modules. Role access and Consumer availability differ per module.

| Module | Description | Consumer can access? |
|---|---|---|
| **Studio** | Content catalogue (all content items), Initiative catalogue (all initiatives) and Idea catalogue (all ideas). The editorial workflow hub where content is created, managed, and published. | ❌ No |
| **Canvas** | Strategic planning — Plans, Views, and Charts to visualise content alignment with business objectives. Content created in Studio is automatically linked. | ❌ No |
| **Gallery** | Consumer-facing content browsing — Collections, Collection Groups, and Bundles. **The ONLY module Consumer can access.** | ✅ Yes |
| **Insights** | Analytics and reporting — content performance, reach metrics, board presentations. | ❌ No |

**Key rule for test case generation**: Consumer = Gallery access ONLY. Admin, Editor, and Contributor can access all four modules (subject to role permissions within each module).

---

## Studio — Content — Role Permissions

Feature area: Content creation, editing, workflow, and lifecycle management in Studio (content catalogue).  
RAG tags: content, story, article, initiative, idea, studio

> **Note:** All write/edit actions in this table apply only when the user has owner or edit access on the content item. See Universal Role Rules → Object-Level Access for the full permission matrix.

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| Create content item | ✅ | ✅ | ✅ | ❌ |
| Edit content metadata (title, tags, content type) | ✅ | ✅ | ✅ | ❌ |
| Add/edit content workflow (tasks, stages and associated tasks) | ✅ | ✅ | ✅ | ❌ |
| Assign content to another user | ✅ | ✅ | ✅ | ❌ |
| Assign content to campaign | ✅ | ✅ | ✅ | ❌ |
| Bulk assign / bulk move | ✅ | ✅ | ✅ | ❌ |
| Archive content | ✅ | ✅ | ❌ | ❌ |
| Unarchive content | ✅ | ✅ | ❌ | ❌ |
| Add/remove content attachments | ✅ | ✅ | ✅ | ❌ |
| Comment on content | ✅ | ✅ | ✅ | ❌ |
| View content comments | ✅ | ✅ | ✅ | ❌ |
| Submit content | ✅ | ✅ | ✅ | ❌ |
| Publish content | ✅ | ✅ | ✅ | ❌ |

**Key role-specific notes:**
- Admin and Editor have the same content access model; Contributor has nearly the same but cannot perform archive/unarchive, lock/unlock, or export content as RTF/PDF
- Consumer cannot access Studio at all — they can only access the Gallery module

---

## Studio — Ideas — Role Permissions

Feature area: Ideas catalogue in Studio — internal idea submission, crowdsourced idea intake, and approval workflow.  
RAG tags: idea, ideas, idea catalogue, crowdsource, submit idea, approve idea, TC-IDEAS, studio

### What Ideas Are
Ideas are a pre-content/pre-initiative stage. They live in the Ideas catalogue inside Studio. An idea can originate from:
- **Internal submission** — any licensed user (Admin/Editor/Contributor) creates an idea directly in Studio
- **Crowdsourced submission** — an external (non-licensed) user submits via a crowdsourcing form (email or URL)

Once approved, a content idea becomes a **Content item**; an initiative idea becomes an **Initiative**.

### Idea Submission Rules
- **Content ideas** can be submitted via a content-type-specific email OR a direct content-type-specific URL
- **Initiative ideas** can only be submitted via an initiative-type-specific email — there is NO public URL for initiative idea submission
- Crowdsourcing forms can be configured only by Admins in Settings > Crowdsourcing

### Idea Approval / Rejection
- Default approver is Admin; can be reconfigured per crowdsourcing form to another user
- **On approval**: idea is converted — content idea → Content item in Studio; initiative idea → Initiative in Studio
- **On rejection**: idea status changes to rejected but stays in the idea catalogue

| Action | Admin | Editor | Contributor | Consumer | External (Source) User |
|---|---|---|---|---|---|
| View Ideas catalogue | ✅ | ✅ | ✅ | ❌ | ❌ |
| Create idea directly in Studio | ✅ | ✅ | ✅ | ❌ | ❌ |
| Submit content idea via crowdsource form (email or URL) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Submit initiative idea via crowdsource form (email only) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Submit initiative idea via crowdsource URL | ❌ | ❌ | ❌ | ❌ | ❌ (email only) |
| Approve or reject an idea | ✅ (default) | configurable per form | ❌ | ❌ | ❌ |
| Edit an idea before approval | ✅ | ✅ (own ideas) | ✅ (own ideas) | ❌ | ❌ |
| Fill in custom fields on an idea | ✅ | ✅ | ✅ | ❌ | ❌ |
| Configure crowdsourcing forms | ✅ | ❌ | ❌ | ❌ | ❌ |

**Key role-specific notes:**
- Consumer cannot access the Ideas catalogue; they can only submit crowdsourced ideas via Gallery's Idea Submission feature
- Initiative ideas have NO URL-based submission channel — email only; submitting via URL must be blocked
- When "Prevent Idea Submit when required fields are empty" is enabled in Content Settings, idea submission is blocked if mandatory fields are blank
- Approved ideas inherit the content type or initiative type configured in the crowdsourcing form
- Ideas submitted through Gallery flow into the Studio Ideas catalogue, not directly into content

**Test case implications:**
- External user submits content idea via URL → appears in Ideas catalogue awaiting approval
- External user attempts to submit initiative idea via URL → should fail (no URL exists / 404 or form not rendered)
- Admin approves content idea → a new Content item is created in Studio with fields pre-populated from the idea
- Admin approves initiative idea → a new Initiative is created in Studio
- Admin rejects idea → idea status changes to Rejected; idea remains visible in the catalogue
- Contributor submits idea with mandatory fields blank (when Content Setting is on) → submission blocked
- Consumer navigates to Ideas catalogue → not accessible (Studio hidden)

---

## Calendar — Role Permissions

Feature area: Editorial calendar, scheduling, filtering, and timeline views.  
RAG tags: calendar, schedule, timeline, filter, date

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| View full team calendar | ✅ | ✅ | ❌ | ❌ |
| View own items on calendar | ✅ | ✅ | ✅ | ❌ |
| Drag/drop to reschedule content | ✅ | ✅ | own only | ❌ |
| Apply calendar filters | ✅ | ✅ | ✅ | ❌ |
| Save filter presets | ✅ | ✅ | ❌ | ❌ |
| Export calendar view | ✅ | ✅ | ❌ | ❌ |
| Create calendar events | ✅ | ✅ | ❌ | ❌ |
| View calendar events | ✅ | ✅ | ✅ | ❌ |

**Key role-specific notes:**
- Contributor calendar shows only items they are assigned to; the full team view is not accessible
- Filter presets saved by Admin or Editor are not visible to Contributors
- Consumer has no access to the calendar module at all

---

## Canvas — Role Permissions

Feature area: Strategic planning — Plans, Views, and Charts to visualise content strategy alignment with business objectives.  
RAG tags: canvas, plan, view, chart, strategy, alignment, TC-CANVAS

Canvas uses **plan-level** access control. Access is managed via the "Manage Access" button within each plan. Charts inside a plan inherit the plan's access — access levels **cannot** be changed at the chart level.

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| Create a plan | ✅ | ✅ | ❌ | ❌ |
| View a plan (with plan access) | ✅ | ✅ | ✅ | ❌ |
| Edit a plan (with owner or edit access) | ✅ | ✅ | ❌ | ❌ |
| Delete a plan | ✅ | ✅ (owner only) | ❌ | ❌ |
| Add views/charts to a plan | ✅ | ✅ (owner or edit access) | ❌ | ❌ |
| Manage Access on a plan (add/remove users) | ✅ | ✅ (owner only) | ❌ | ❌ |
| View who has access to a chart in a plan | ✅ | ✅ (if has plan access) | ✅ (if has plan access) | ❌ |
| Change access at chart level | ❌ | ❌ | ❌ | ❌ |

**Key role-specific notes:**
- Consumer has no access to Canvas at all
- Contributor can view plans they have been explicitly granted access to, but cannot create, edit, or delete plans
- All charts within a plan inherit the plan's access configuration — chart-level access is view-only (who has access) and cannot be modified independently
- Plan access levels follow the same Owner/Edit/View model as Studio items (see Object-Level Access section)
- Content in Studio is automatically reflected in Canvas plans in real time

---

## Studio — Campaign / Initiative — Role Permissions

Feature area: Campaign creation, initiative management, content grouping in Studio (initiative catalogue).  
RAG tags: campaign, initiative, program, group, TC-INIT, studio

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| Create campaign/initiative | ✅ | ✅ | ❌ | ❌ |
| Edit campaign details | ✅ | ✅ | ✅ (if granted owner or edit access via Manage Access) | ❌ |
| Archive/delete campaign | ✅ | ❌ | ❌ | ❌ |
| Add content to campaign | ✅ | ✅ | ✅ (if granted owner or edit access via Manage Access) | ❌ |
| View campaign overview | ✅ | ✅ | ✅ (if granted any access level via Manage Access) | ❌ |
| View campaign performance metrics | ✅ | ✅ | ❌ | ❌ |
| Manage Access on initiative (grant/revoke) | ✅ | ✅ (owner only) | ✅ (if owner of the initiative) | ❌ |

**Key role-specific notes:**
- Only Admin can delete or permanently archive a campaign/initiative
- **Contributor cannot create initiatives** — this is always blocked regardless of access level
- Contributor can be granted **owner or edit access** to an existing initiative via Manage Access — this gives them the ability to edit that initiative
- Contributor with **owner access** to an initiative: can edit it AND manage access (grant/revoke) on it
- Contributor with **edit access** to an initiative: can edit it but cannot delete it or manage its access
- Contributor with **view access** or no access: read-only or invisible — cannot edit
- Consumer cannot access Studio at all — initiatives and campaigns are not visible to Consumer

**Test case implications for Contributor + Initiative access:**
- Contributor attempts to create an initiative → should always fail (❌ button hidden or 403)
- Contributor is granted edit access to an initiative → can open and edit initiative details
- Contributor with edit access attempts to delete initiative → should fail
- Contributor is granted owner access → can edit AND use Manage Access to grant others access
- Contributor with view access attempts edit → edit controls hidden or 403

---

## Members / User Management — Role Permissions

Feature area: User invitations, role changes, team management.  
RAG tags: member, user, invite, team, role, permission, TC-MEMBERS

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| Invite new users | ✅ | ❌ | ❌ | ❌ |
| Change a user's role | ✅ | ❌ | ❌ | ❌ |
| Remove a user from workspace | ✅ | ❌ | ❌ | ❌ |
| View team member list | ✅ | ✅ | ✅ | ❌ |
| Edit own profile | ✅ | ✅ | ✅ | ✅ |
| Deactivate a user | ✅ | ❌ | ❌ | ❌ |

**Key role-specific notes:**
- All user management actions are Admin-only; attempting any of these as Editor/Contributor/Consumer must return 403
- Users can always edit their own profile regardless of role

---

## Settings — Role Permissions

Feature area: All workspace configuration. Settings is accessible by **Admin only**. Editor, Contributor, and Consumer have no access to any Settings section.  
RAG tags: settings, configuration, custom field, content type, initiative type, crowdsourcing, workflow, TC-SETTINGS

### Access Rules
- **Admin** — full access to all Settings sections
- **Editor / Contributor / Consumer** — the Settings module is completely hidden in the navigation; any direct URL attempt returns 403
- Exception: non-admin users managing their own notification preferences (if exposed as a profile setting outside of Settings module)

### Settings Sections and What They Control

#### 1. General Settings
Top-level workspace configuration. Admin only.

#### 2. Content Settings
Workspace-wide content behaviour toggles. Admin only. Key configurable checkboxes:

| Setting | Effect when enabled |
|---|---|
| Make initiatives required for all content | Content cannot be submitted or published without an initiative assigned |
| Use Personas and Buying Stages | Persona and Buying Stage fields appear on the content details page |
| Make Personas and Buying Stages required | These fields must be completed before submit/publish |
| Assign sequential Content ID to content | Each content item gets an auto-incremented numeric ID |
| Set all content and initiatives to In-Progress upon creation | New items start in In-Progress stage instead of the default first workflow stage |
| Prevent Idea Submit when required fields empty | Idea cannot be submitted if mandatory fields are blank |
| Prevent Content Submit when required fields empty | Content cannot move to Submit stage if mandatory fields are blank |
| Prevent Content Publish when required fields empty | Content cannot be published if mandatory fields are blank |
| Prevent Initiative Progress when required fields empty | Initiative cannot advance if mandatory fields are blank |
| Only Task Assignees may check off tasks | Only the user assigned to a task can mark it complete |
| Restrict non-admin users from changing content types | Editor and Contributor cannot change the content type of an existing content item |
| Allow admins and content authors to duplicate completed tasks | Admin and the original content author can duplicate tasks that are already marked done |

**Test case implications for Content Settings:**
- When "required fields" settings are on, test: submit/publish with blank mandatory fields → should be blocked; fill all mandatory fields → should proceed
- When "Only Task Assignees may check off tasks" is on, test: non-assignee attempts to check off a task → should be blocked
- When "Restrict non-admin users from changing content types" is on, test: Editor/Contributor attempts to change type → dropdown grayed out or 403

#### 3. Custom Fields
Admin configures custom fields that appear on Content, Initiative, and Idea detail pages. Non-admin users fill in custom fields but cannot create or modify the field definitions.

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| Create / edit / delete custom field definitions | ✅ | ❌ | ❌ | ❌ |
| Mark a custom field as mandatory (red asterisk) | ✅ | ❌ | ❌ | ❌ |
| Fill in custom field values on content/initiative | ✅ | ✅ | ✅ | ❌ |
| Fill in custom field values on ideas | ✅ | ✅ | ✅ | ❌ |
| Bulk-paste values into multi-select custom fields | ✅ | ✅ | ✅ | ❌ |

**Key notes:**
- Custom fields with a red asterisk are mandatory; content/initiative cannot publish if they are blank
- Multi-select paste: if ALL pasted values are invalid → existing values kept, error shown; if PARTIAL match → valid values applied, error lists count of applied values
- Custom fields are scoped per content type or initiative type (configured in Content Types / Initiative Types settings)

#### 4. Content Types
Defines the types of content (e.g. Blog Post, eBook, Webinar, Social Media) and their full configuration. Admin only to create/edit/delete.

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| Create new content type | ✅ | ❌ | ❌ | ❌ |
| Edit content type settings | ✅ | ❌ | ❌ | ❌ |
| Delete content type | ✅ | ❌ | ❌ | ❌ |
| Create content of a permitted type | ✅ | ✅ (if type grants access) | ✅ (if type grants access) | ❌ |
| Change content type on an existing item | ✅ | ✅ (unless restricted by Content Settings) | ✅ (unless restricted) | ❌ |

Each content type configures:
- **Options** — icon, title, body type (HTML / Document / Video / Social Media), publish settings, destinations
- **Access Defaults** — which users/groups can create this type (Admin can always view and change all types regardless)
- **Workflow** — stages, task workflows, task owners, smart deadlines
- **Supporting Attachment Folders** — folders that appear on the content page for file attachments
- **Custom Fields** — which custom fields appear on this content type
- **Custom Field Prefills** — default values pre-populated when content of this type is created

**Body type thumbnail rules (for Gallery display):**
- HTML: uses Featured image, else first body image; else no thumbnail
- Document: thumbnail generated from PDF at Publish URL only; Word/PowerPoint not supported
- Video: thumbnail only if Publish URL is YouTube AND destination is YouTube or Unknown
- Social Media: supports Facebook, Instagram, X, Pinterest, LinkedIn, YouTube; preview from attached media (video preferred over image, except Pinterest)
- All other types: no thumbnail unless manually uploaded

**Test case implications for Content Types:**
- User with access to a type can create content of that type; user without access sees the type grayed out
- If "Restrict non-admin users from changing content types" is on → only Admin can change type on existing items
- Workflow tasks: only task assignees can check off tasks if the Content Setting is enabled
- Mandatory custom fields on the type block submit/publish until filled

#### 5. Initiative Types
Same configuration model as Content Types, but for Initiatives. Admin only to create/edit/delete.

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| Create / edit / delete initiative types | ✅ | ❌ | ❌ | ❌ |
| Create an initiative of a permitted type | ✅ | ✅ | ❌ | ❌ |

#### 6. Crowdsourcing
Enables external (non-licensed) users to submit content ideas or initiative ideas via a public form. Admin only to configure.

| Action | Admin | Editor | Contributor | Consumer | External (Source) User |
|---|---|---|---|---|---|
| Configure crowdsourcing forms | ✅ | ❌ | ❌ | ❌ | ❌ |
| Approve or reject submitted ideas | ✅ (default approver) | configurable | ❌ | ❌ | ❌ |
| Submit a content idea via crowdsource form | ✅ | ✅ | ✅ | ✅ | ✅ (via email or URL) |
| Submit an initiative idea via crowdsource form | ✅ | ✅ | ✅ | ✅ | ✅ (via email only) |
| View Ideas catalogue | ✅ | ✅ | ✅ | ❌ | ❌ |

**Crowdsourcing flow:**
- Content idea submissions: accessible via content-type-specific email OR direct content-type-specific URL
- Initiative idea submissions: accessible via initiative-type-specific email ONLY (no URL)
- Submitted ideas land in the Ideas catalogue (in Studio) awaiting approval
- On approval: content idea → becomes a Content item; initiative idea → becomes an Initiative
- On rejection: idea status changes to Rejected; idea remains in the Ideas catalogue
- Default approver is Admin; can be reconfigured per crowdsourcing form

**Test case implications for Crowdsourcing:**
- External user submits via URL → idea appears in Ideas catalogue awaiting approval
- External user submits initiative idea via URL → should fail (initiative ideas are email-only)
- Admin approves content idea → content item is created in Studio
- Admin rejects idea → idea status changes to Rejected and remains visible in the catalogue
- Non-admin attempts to access Settings > Crowdsourcing → 403 or hidden

### Settings — Permissions Summary Table

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| Access Settings module | ✅ | ❌ | ❌ | ❌ |
| Configure General Settings | ✅ | ❌ | ❌ | ❌ |
| Configure Content Settings toggles | ✅ | ❌ | ❌ | ❌ |
| Create / edit custom field definitions | ✅ | ❌ | ❌ | ❌ |
| Create / edit content types | ✅ | ❌ | ❌ | ❌ |
| Create / edit initiative types | ✅ | ❌ | ❌ | ❌ |
| Configure crowdsourcing forms | ✅ | ❌ | ❌ | ❌ |
| Approve/reject crowdsourced ideas | ✅ | configurable | ❌ | ❌ |

---

## Search — Role Permissions

Feature area: Global search, saved searches, search filters.  
RAG tags: search, find, filter, TC-SEARCH

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| Search across all content | ✅ | ✅ | own content only | ❌ |
| Save search presets | ✅ | ✅ | ❌ | ❌ |
| Access advanced search filters | ✅ | ✅ | limited | ❌ |

**Key role-specific notes:**
- Contributor search results are automatically scoped to content they are assigned to
- Consumer has no search access to editorial content

---

## Insights — Role Permissions

Feature area: Analytics and reporting — content performance, reach metrics, and operational visibility.  
RAG tags: insights, analytics, reporting, metrics, reach, performance, TC-INSIGHTS

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| View all workspace analytics | ✅ | ✅ | ❌ | ❌ |
| View own content analytics only | ✅ | ✅ | ✅ | ❌ |
| View reach metrics (internal and external) | ✅ | ✅ | ❌ | ❌ |
| Create/save analytics boards | ✅ | ✅ | ❌ | ❌ |
| View saved boards | ✅ | ✅ | ❌ | ❌ |
| Export analytics data | ✅ | ✅ | ❌ | ❌ |

**Key role-specific notes:**
- Consumer has no access to Insights at all
- Contributor can only see analytics for content they own or are assigned to; workspace-wide metrics are hidden
- Admin and Editor can view reach metrics under the Reach tab (internal vs external) inside Insights
- Saved boards are used in executive presentations and planning meetings (Admin/Editor only)

---

## Gallery — Role Permissions

Feature area: Consumer-facing content browsing — Collections, Collection Groups, and Bundles. Gallery is the ONLY module accessible to Consumer.  
RAG tags: gallery, napa, published, browse, collection, bundle, TC-GALLERY, TC-DASH

### Gallery Structure
- **Collection Group** — a landing page / location (e.g. Salesforce, internal intranet). Acts as a top-level container.
- **Collection** — a group of content items within a Collection Group, organised by topic, initiative, or audience.
- **Bundle** — a curated content journey shared with stakeholders, customers, or prospects.

Gallery has its own permission system for Collections: each Collection can be restricted to specific authenticated users or groups. When a user accesses a Collection Group, Kapost only shows them the Collections they have permission to see.

| Action | Admin | Editor | Contributor | Consumer |
|---|---|---|---|---|
| Access Gallery module | ✅ | ✅ | ✅ | ✅ |
| View and browse Collections | ✅ | ✅ | ✅ | ✅ (if permitted) |
| Download/share gallery items | ✅ | ✅ | ✅ | ✅ |
| Submit ideas from Gallery | ✅ | ✅ | ✅ | ✅ |
| Create Collection Groups | ✅ | ✅ | ❌ | ❌ |
| Create Collections | ✅ | ✅ | ❌ | ❌ |
| Add/remove content from Collections | ✅ | ✅ | ❌ | ❌ |
| Set Collection permissions (who can see it) | ✅ | ✅ (if owner) | ❌ | ❌ |
| Transfer Collection ownership | ✅ | ✅ (if owner or Admin) | ❌ | ❌ |
| Configure Collection auto-add rules | ✅ | ✅ | ❌ | ❌ |
| Upload content directly to Gallery | ✅ | ✅ | ❌ | ❌ |
| Feature/pin items in a Collection | ✅ | ✅ | ❌ | ❌ |
| View Gallery reach analytics | ✅ | ✅ | ❌ | ❌ |

**Key role-specific notes:**
- Gallery is the ONLY module Consumer can access — Consumer cannot enter Studio, Canvas, or Insights
- Consumer must be authenticated (logged in) to access Collections unless a Collection Group is explicitly set to public
- Consumer only sees Collections they have been given permission to see; other Collections are completely hidden
- Content uploaded directly to Gallery also appears in Studio; the reverse is NOT automatic — Studio content must be explicitly added to a Collection to appear in Gallery
- Collection ownership can be transferred by the current owner or an Admin; the new owner must have the necessary Gallery permissions
- Idea Submission allows Consumer to submit content ideas from Gallery; submitted ideas flow into the Ideas section of Studio
