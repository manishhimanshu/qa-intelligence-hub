# Archived Content Type

## Overview

The Archive Content Type feature allows administrators to deactivate content types that are no longer needed while preserving all existing content created using those content types.

Archiving a content type prevents users from creating new content with that type but does not delete or modify previously created content.

---

## Purpose

The feature helps organizations:

- Retire obsolete content types.
- Reduce clutter in content creation menus.
- Preserve historical content.
- Prevent accidental use of outdated content types.

---

## Permissions

Only users with administrative permissions can archive or unarchive content types.

Regular users cannot perform archive or unarchive operations.

---

## Archiving a Content Type

To archive a content type:

1. Navigate to **Setup > Content Types**.
2. Locate the desired content type.
3. Click the **Archive** action.
4. Review the confirmation dialog.
5. Confirm the archive operation.

---

## Archive Confirmation

Before archiving, the system displays a confirmation dialog informing the administrator that:

- The selected content type will be archived.
- Archived content types can no longer be selected when creating new content.
- Existing content remains unchanged.

The administrator can:

- Cancel
- Archive

---

## Unarchiving a Content Type

Administrators can restore archived content types.

Steps:

1. Navigate to **Setup > Content Types**.
2. Enable the **Show Archived Content Types** filter.
3. Locate the archived content type.
4. Click **Unarchive**.
5. Confirm the operation.

---

## Unarchive Confirmation

The confirmation dialog informs the administrator that:

- The archived content type will become available again.
- Users will once again be able to create content using that type.

The administrator can:

- Cancel
- Unarchive

---

## Business Rules

### Archive

- Archived content types remain stored in the system.
- Existing content using the archived content type is preserved.
- Existing content remains editable.
- Existing workflows continue to function.
- Existing reports continue to include archived content.
- Archived content types cannot be selected when creating new content.

### Unarchive

- Unarchiving restores the content type.
- The content type becomes available immediately.
- Users can create new content using the restored content type.

---

## User Interface

The Content Types page provides:

- List of content types
- Archive action
- Unarchive action
- Show Archived filter
- Confirmation dialogs

---

## Expected System Behavior

### When Archiving

The system should:

- Display a confirmation dialog.
- Archive the selected content type.
- Hide it from active content type lists.
- Prevent it from appearing during content creation.
- Preserve all existing content.

### When Unarchiving

The system should:

- Display a confirmation dialog.
- Restore the content type.
- Display it in active content type lists.
- Allow users to create new content using it.

---

## Common QA Scenarios

### Archive

Verify:

- Archive option is available for administrators.
- Confirmation dialog appears.
- Archive succeeds.
- Archived content type disappears from active list.
- Archived content type appears when "Show Archived" is enabled.
- Existing content remains accessible.
- Existing content remains editable.
- New content cannot be created using the archived content type.

---

### Unarchive

Verify:

- Archived content type appears in archived view.
- Unarchive option is available.
- Confirmation dialog appears.
- Unarchive succeeds.
- Content type returns to active list.
- Users can create new content using it.

---

### Permissions

Verify:

- Only administrators can archive content types.
- Only administrators can unarchive content types.
- Unauthorized users cannot access archive actions.

---

### Regression

Verify that archiving does NOT impact:

- Existing content
- Existing workflows
- Reporting
- Content visibility
- Historical records

---

## Keywords

Archive Content Type, Unarchive Content Type, Content Types, Administration, Setup, Archived Content, Active Content Types, Show Archived, Confirmation Dialog, Content Creation, Permissions