# Lessons

- Keep generation-time discovery separate from future executor actions; only persistent progress metadata may be written while generating.
- Never infer business rules, ranges, owners, commands, or acceptance from names or conventions when authoritative evidence is absent.
- Explicit user-selected scope wins only when authorized and compatible with governing policy; automatic queue selection must remain fail-closed.
- Use one project-local progress source and reload it before decisions so context changes do not reset development state.
- Distinguish unchanged permitted baseline failures from new or changed failures using stable IDs and fingerprints.
- Keep the skill instruction-only; use a small installer rather than duplicating the skill into multiple discovery locations.
- Forward testing is most useful when agents receive raw tasks and artifacts rather than intended fixes.
- Never confuse the installed skill repository with the target development project; durable state follows the project being modified.
- Use exact, non-recursive cleanup operations in disposable installer tests so safety policy can verify every target.
- Set the working directory explicitly for every repository command; creating a target directory does not move the shell into it.
- Test persistence with a fresh agent context: recovery is proven only when the same unit and tracker survive without relying on conversation history.
