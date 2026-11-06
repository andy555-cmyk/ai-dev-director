# AI DEV DIRECTOR HUD implementation QA

- Source visual truth: docs/design/hud-reference.png (selected generated HUD design, 1672 × 941).
- Browser implementation: /workspace/scratch/director-hud-v030-final.jpg (1363 × 936 pixels / CSS viewport, DPR 1).
- Responsive evidence: /workspace/scratch/director-hud-mobile-final.jpg; real 390 × 844 CSS iframe viewport, with scrollbar leaving a 375 px content width.
- State: idle, default Claude / Antigravity / Codex roles, unknown connection state, unsubmitted example draft. No fictional run history or passed tests.
- Full-view comparison: docs/design/hud-comparison.jpg. Both images are shown together, with uniform contain scaling and no nonuniform stretching. Different aspect ratios are preserved; layout uses 21% left, 22% right and the remaining central stage.
- Focused comparison: docs/design/hud-core-comparison.jpg, central stage and AI card region.

## Comparison history

1. Initial browser capture: /workspace/scratch/director-hud-initial.jpg.
   - P1: WebGL unavailable in the cloud browser; the existing fallback left the reactor nearly invisible.
   - Fix: luminous dimensioned reactor asset in the canvas fallback, perspective-projected colored orbit bands and nodes; actual WebGL retains real shader geometry.
   - P2: a nested screen-blended backdrop darkened the core.
   - Fix: move the atmosphere to the root compositing layer. Post-fix browser screenshot shows a bright, readable reactor.
2. Interaction / mobile checks:
   - P2: successful polling hid the send-error notice immediately; draft was previously cleared on failure.
   - Fix: preserve draft on rejected/busy/failed submission and keep the notice visible for its display duration.
   - P2: inherited mobile rules hid brand text.
   - Fix: restore the brand in the small viewport. Mobile DOM and capture show the title and all primary controls without horizontal overflow.
3. Final comparison:
   - Central luminous core, three role-colored satellites, orbital rails, transparent cyan panels, left mission composer, right verification/connection panels and bottom pipeline match the selected concept's hierarchy.
   - Actual unknown and empty states replace the concept's invented sample events. The taller browser viewport expands panel height rather than stretching assets.
   - Added deterministic colored orbit particle bands and verified the post-fix release capture.
   - Remaining P3: the production panels use restrained bevels; exact movie-like glass refraction and ray tracing are not implemented.

## Primary interactions tested in the cloud browser

- Role menu opens with mouse and Enter; changing HEAD swaps the two roles and updates labels. Restored default roles afterward.
- Motion off/on updates pressed state and persists for the session.
- Draft input, attempted preview submission, error notice and retained input.
- Diagnosis navigation and return; workshop tab / HUD return.
- 390 px iframe viewport: core, menu and mission input remain accessible; no horizontal overflow.
- Console checked: no unhandled application errors; known WebGL2-unavailable warning is handled by the fallback. Browser-extension metadata errors are outside the app.

## Scope limits

The local browser preview intentionally uses empty simulated API responses and rejects actual AI runs. The installed app retains its Python API and CLI integrations. The cloud browser cannot exercise the WebGL2 path. macOS install, disk-image mounting, native dialog behavior and real signed-in AI workflows remain unverified.

final result: passed
