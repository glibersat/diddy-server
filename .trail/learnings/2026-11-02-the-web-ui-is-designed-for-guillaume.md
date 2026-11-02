---
title: "The web UI is designed for people with ADHD: keep every screen simple and focused"
author: Guillaume
date: 2026-11-02
branch: feature/adhd-ui-redesign
cost: { minutes: 1, tokens: 1912 }
id: l-30b12c27
scope: repo
status: active
src: agent
touches:
  - frontend/src/style.css
  - frontend/src/nav.ts
  - frontend/src/kinds.ts
  - frontend/src/components/EditSheet.vue
---

## Decided
The people using the web UI have ADHD (stated by the project owner). Every screen follows these rules:
- One obvious primary action per screen. Everything else is visually quieter.
- Plain words over technical terms. Form labels are questions. Error messages say what to do next.
- Hide settings until they're needed: rarely changed options start collapsed and show a one-line summary.
- No free-text number lists: use tappable chips for minute values.
- Lists show only what you need to scan. Edit and delete happen in a side panel. Delete needs a second tap, with no blocking confirm() dialog.
- Large tap targets (at least 44px), visible focus rings, colour always paired with an icon or label, and animations turned off when the system asks for reduced motion.
- Keep few top-level screens: everyday ones in the main nav, occasional ones grouped under "More", so the nav never offers too many choices at once.

## Tried and ruled out
- Many equal top tabs plus Enable/Edit/Delete buttons on every row: too noisy, too many choices at once.

## Watch out
- Daily-schedule notifications are titled "Reminder" with the real text in the body. Display code must lead with the body (use headline()), or every routine reads as "Reminder".
- Tailwind v4 can't @apply one component class from another: write class="btn btn-primary", not a btn-primary that applies btn.

In the code: frontend/src/style.css (design tokens and component classes), frontend/src/nav.ts (PRIMARY_NAV vs SECONDARY_NAV), frontend/src/kinds.ts (KINDS look per reminder type, headline()), frontend/src/components/EditSheet.vue, DeleteButton.vue, MinutesPicker.vue, ReminderOptions.vue.
