# Notes Feature

## Overview

Notes is a personal productivity workspace within Kapost that enables users to create, organize, and manage information without leaving the application. It is designed for capturing meeting notes, planning work, maintaining documentation, tracking tasks, and storing reference material.

All notes are private to the logged-in user and cannot be viewed by other users.

---

## Purpose

The Notes feature provides a centralized workspace where users can:

- Capture meeting notes
- Maintain project documentation
- Track action items
- Create personal checklists
- Store reference information
- Organize information into books and pages

---

## Key Features

### Books

Books act as top-level containers for organizing notes.

Users can:

- Create books
- Rename books
- Delete books
- Reorder books using drag and drop

---

### Pages

Each book can contain multiple pages.

Users can:

- Create pages
- Rename pages
- Delete pages
- Reorder pages
- Edit page content

---

### Rich Text Editor

The Notes editor supports rich text formatting.

Available formatting options include:

- Bold
- Italic
- Underline
- Strikethrough
- Font color
- Text highlight
- Bullet list
- Numbered list
- Checklist (To-Do)
- Hyperlinks
- Images
- Important marker
- Date insertion

---

### Search

Users can search across all books and pages.

Search should return matching note content quickly.

---

### Auto Save

Changes are automatically saved.

Users are not required to manually save their work.

---

### Privacy

Notes are user-specific.

- One user's notes are not visible to another user.
- Notes remain available across user sessions.

---

## Navigation

The Notes feature is accessible from the top navigation bar.

Selecting the Notes icon opens a floating Notes window.

On first launch:

- A default book is created automatically.
- A default page is created automatically.

---

## Typical User Workflow

1. Open Notes from the navigation bar.
2. Create a new book.
3. Create one or more pages.
4. Enter content using the HTML editor.
5. Apply formatting.
6. Insert images or links if required.
7. Add checklist items.
8. Search existing notes.
9. Continue editing without manually saving.

---

## Business Rules

- Every page belongs to exactly one book.
- A book may contain multiple pages.
- Users can reorder books.
- Users can reorder pages.
- Changes are auto-saved.
- Notes are private to the logged-in user.
- Rich text formatting should be preserved after reload.
- Images and links should persist after saving.
- Search should locate matching notes across all books.

---

## Common QA Scenarios

### Book Management

- Create book
- Rename book
- Delete book
- Reorder books

### Page Management

- Create page
- Rename page
- Delete page
- Reorder pages

### Rich Text Editor

Validate:

- Text formatting
- Lists
- Hyperlinks
- Images
- Font colors
- Highlighting
- Important marker
- Date insertion

### Search

Verify:

- Search returns matching notes
- Search works across books
- Search updates while notes change

### Auto Save

Verify:

- No manual save required
- Changes persist after refresh
- Changes persist after logout/login

### Privacy

Verify:

- Users cannot access another user's notes.

---

## Keywords

Notes, Book, Page, HTML Editor, Rich Text Editor, Search, Checklist, Auto Save, Images, Hyperlinks, Formatting, Productivity Workspace, Personal Notes