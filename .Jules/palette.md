## 2025-01-20 - [Added Context to Icon Buttons]
**Learning:** Icon-only buttons (like edit, refresh, and especially toggle switches) often lack accessible names, making them unusable for screen reader users who can't see the icon or the visual context.
**Action:** Always verify that icon-only buttons and form inputs (like checkboxes without text labels) have specific, descriptive `aria-label` attributes that include the object's name (e.g., "Enable [Server Name]").
