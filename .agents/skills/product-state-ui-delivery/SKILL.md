---
name: product-state-ui-delivery
description: Use when building or changing product status indicators, desktop floating UI, alert sounds, packaging, or release flows, especially after user reports that UI state, animations, resources, or distribution behavior differs from real product use.
origin: local
---

# Product State UI Delivery

Use this skill to keep product-facing desktop utilities honest, usable, and shippable. It records lessons from the Codex Traffic Lights project.

## Core Rule

Treat repeated user correction as a product-signal interrupt. Stop pushing the current abstraction and re-check what the person is actually seeing, hearing, clicking, or installing.

## Product Truth

- Do not infer important states from generic fields such as `idle`, `completed`, or old timestamps when the upstream source does not expose that state.
- Prefer real runtime evidence: live IPC samples, real app behavior, real close/disconnect events, real file dialogs, and real packaged executables.
- If evidence is missing, document "unobservable" instead of pretending a fallback means success.
- Never commit raw diagnostic samples that may contain prompts, paths, commands, diffs, or generated content. Convert findings into a short sanitized Markdown note.
- Keep state mapping explainable: each product status should have a named upstream signal or a documented absence rule.

## UI State And Animation

- Avoid restarting animations on repeated same-state refreshes. Deduplicate at the animation layer so frequent upstream updates do not cut off blinks or breathing cycles.
- Dynamic effects need loop-safe keyframes: the end of a cycle must return smoothly to the next cycle's start.
- Scaling must apply to content, not only containers. Check main lamps, mini lamps, icons, text, spacing, hit areas, docked mode, expanded mode, and retiring/exit states.
- Every UI state variant needs the same scale audit: compact, expanded, docked, snapped, hover-expanded, settings panel, and session matrix.
- For state-machine UI such as edge docking, cancel stale timers before switching modes. Double-click, hover, auto-collapse, and expand should not compete.
- When the user says "no empty space" or "frame inside a frame," draw or describe the layout boxes before changing code. Confirm which gap belongs to the container and which belongs inside the item.

## Resources And Distribution

- For portable/folder distribution, user-visible resources should live beside the executable when that is the product expectation. Avoid surprising users with AppData storage for core bundled assets.
- Keep one canonical default resource directory. Do not maintain parallel hidden and visible default sound folders unless there is a clear migration reason.
- Settings panels should display the actual current resource filename, including defaults, not a blank placeholder.
- File dialogs must handle cancellation and invalid files without crashing. Choosing nothing is a valid user action.
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

## Delivery Checklist

Before saying done:

1. Verify the real path the user will use, not only helper functions.
2. Test at least one boundary case from the user report.
3. Confirm UI scale and animation in every affected mode.
4. Confirm packaged distribution if packaging changed.
5. Review staged files for artifacts and sensitive diagnostics.
6. Report exact tests, lint, build/package results, and any remaining unverified scenarios.
