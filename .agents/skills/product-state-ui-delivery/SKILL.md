---
name: product-state-ui-delivery
description: Use when building or changing product status indicators, desktop floating UI, alert sounds, packaging, or release flows, especially after user reports that UI state, animations, resources, or distribution behavior differs from real product use.
origin: local
---

# Product State UI Delivery

Use this skill to keep product-facing desktop utilities honest, usable, and shippable. It records lessons from the Codex Traffic Lights project across v0.1–v0.5.

## Core Rule

Treat repeated user correction as a product-signal interrupt. Stop pushing the current abstraction and re-check what the person is actually seeing, hearing, clicking, or installing.

## Product Truth

- Do not infer important states from generic fields such as `idle`, `completed`, or old timestamps when the upstream source does not expose that state.
- Prefer real runtime evidence: live IPC samples, real app behavior, real close/disconnect events, real file dialogs, and real packaged executables.
- If evidence is missing, document "unobservable" instead of pretending a fallback means success.
- Never commit raw diagnostic samples that may contain prompts, paths, commands, diffs, or generated content. Convert findings into a short sanitized Markdown note.
- Keep state mapping explainable: each product status should have a named upstream signal or a documented absence rule.

## Interaction Design First

Before writing any animation or state-machine code:

1. **Ask for a real-world analogy.** "What does this feel like?" beats "what are the parameters?" The USB detection popup analogy (slide in → retract → leave visible icon) produced a better design than any threshold tuning on the old hide-behind-edge logic.
2. **Do not inherit old behavior by default.** When redesigning an interaction, start from the user's mental model, not from the existing code's parameters. The old code had "hide behind edge leaving 6px" — optimizing that was the wrong direction entirely.
3. **Draw the lifecycle.** Sketch all states side-by-side (ASCII is fine) before coding. Show what the user sees at each stage, not what the data model holds. This catches "half off-screen" problems before they reach code.

## Multi-State UI Design

When a widget has more than two visual modes (e.g., free / snapped / docked / expanded):

### State Machine Rules

- **Audit every pair for direct transitions.** Do not assume linear progression (A→B→C). Users will jump A→C. Each direct path must work without side effects from the skipped intermediate state.
- **Skip intermediate animations when jumping states.** If the user goes from docked to expanded, animate directly from docked size to expanded size — never docked→compact→expanded. Two animations on the same property will fight and cause stuttering.
- **Cancel all timers before switching modes.** Double-click, hover, auto-collapse, dock-timer, and expand should never compete. Each state transition method must stop every timer it does not explicitly re-schedule.
- **Separate cleanup from positioning.** State cleanup functions must not destroy alignment information that the next step still needs. Save positioning references (`snap_edge`) before clearing, or defer the clear until after `_apply_size()` consumes them.

### Scale Consistency

- Scaling must apply to content, not only containers. Check main lamps, mini lamps, icons, text, spacing, hit areas, docked mode, expanded mode, and retiring/exit states.
- **When adding a new visual mode, audit every global modifier.** The checklist: zoom/scale, theme/colors, language/i18n, accessibility, screen DPI. A new mode that ignores `window_scale` is a guaranteed bug report.
- Every UI state variant needs the same scale audit: compact, expanded, docked, snapped, hover-expanded, settings panel, and session matrix.
- Constants for mode-specific dimensions must be multiplied by the scale factor at the point of use, not hard-coded.

### Boundary Testing

- **Test boundary conditions from both directions.** "Near the edge from inside" AND "past the edge from outside." Users drag widgets partially off-screen all the time — that must still trigger correct behavior.
- Use signed distance, not `abs()`, for boundary detection. Negative distance (past the boundary) should be treated as "at the boundary," not "far away."
- Test multi-monitor: verify the widget snaps to its *own* screen edge, not always the primary screen.

## UI Animation

- Avoid restarting animations on repeated same-state refreshes. Deduplicate at the animation layer so frequent upstream updates do not cut off blinks or breathing cycles.
- Dynamic effects need loop-safe keyframes: the end of a cycle must return smoothly to the next cycle's start.
- All animations use `InOutCubic` or `InOutSine` easing. Never linear.
- For state-machine UI, the animation target geometry must be recalculated from the *target* state's dimensions and alignment, not inherited from the *current* geometry which may be mid-animation.

## Resources And Distribution

- **One canonical resource directory.** Do not maintain parallel hidden and visible default resource folders. For portable/folder distribution, user-visible resources live beside the executable. No copy step, no fallback chain through internal packaged resources.
- Avoid over-engineering resource resolution. If the product distributes as a portable folder (not single exe), the resource directory is writable — no need for a read-only/writable split.
- Settings panels should display the actual current resource filename, including defaults, not a blank placeholder.
- File dialogs must handle cancellation and invalid files without crashing. Choosing nothing is a valid user action. Every `raise ValueError` from a utility function must be caught by the UI handler that called it.
- Test the packaged executable separately from the dev entrypoint. Packaging bugs can be invisible in unit tests.
- Guard against packaged GUI executables being used as background hook runners; that can create launch loops.

## Release Hygiene

- Before release, run the actual quality gates and write the real numbers in release notes.
- Stage only source, tests, and docs intended for Git. Do not stage `dist/`, `build/`, spec files, local custom sounds, or raw diagnostics.
- Release notes should be in the user's language and describe product-visible changes, not only internal implementation details.
- If shipping a portable zip, verify the zip contents: executable, visible resources, user guide, and absence of duplicate hidden resource folders.
- Preserve historical GitHub Releases and tags so progress can be reviewed later.

## Architecture Lessons

- Split by concern, not by arbitrary line count. A file is too broad when one product change forces edits across unrelated responsibilities, not merely when it exceeds a number.
- Do not package a whole feature into one module if it mixes UI, storage, playback, protocol parsing, and policy. Each concern should be removable or testable on its own.
- Keep user-facing text operational and short. Implementation words such as IPC, registry, diagnostic, pipeline, or protocol belong in docs/logs unless the user needs them.
- Prefer conservative product increments: prove behavior with existing runtime evidence before inventing new states, schemas, settings, or abstractions.
- **Three-question judgment for every new module**: What user problem does it solve? What existing module could be extended instead? What happens if we skip it entirely?

## Delivery Checklist

Before saying done:

1. Verify the real path the user will use, not only helper functions.
2. Test at least one boundary case from the user report — from both inside and outside the boundary.
3. Confirm UI scale and animation in **every** affected mode (compact, expanded, snapped, docked, hover-expanded).
4. Confirm packaged distribution if packaging changed.
5. Review staged files for artifacts and sensitive diagnostics.
6. Report exact tests, lint, build/package results, and any remaining unverified scenarios.
7. For state-machine features, confirm every pair of states has a tested direct transition.
