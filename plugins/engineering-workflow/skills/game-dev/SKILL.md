---
name: game-dev
description: "Use when building or polishing a game: balance and progression checks, asset audits against budgets, performance budgets, playtest reports, regression coverage for fixed bugs, scope checks, art direction, sound review, and driving Unity or Blender from the agent. Works with the engineering-workflow skill for verification and reporting."
---

# Game development checks

Rules adapted from the most-starred game-development agent repositories (sources and pinned commits in
[references/game-dev-sources.md](references/game-dev-sources.md)). Use them together with the engineering-workflow
skill; its verification, review and reporting rules still apply.

## Measure, never estimate

- A report that needs numbers (frame time, draw calls, file sizes, texture sizes, sample rates, loudness, quest
  timings) uses only values measured in this run. A value that could not be measured is written `NOT ASSESSED`,
  never guessed. A table filled from guesses looks like evidence and is worse than an empty one.
- Before producing a check, list its inputs and mark each `FOUND` or `ABSENT`. If every required input is absent,
  the verdict is `NOT ASSESSED — NO DATA`, naming what is missing and what would produce it. That verdict is a
  success, not a failure to hide.

## Balance and progression

- Compare against a written target (a timetable per stage, a resource flow, damage per second per tier). Without a
  target, write one down first and get it agreed; do not tune by feel.
- Look for outliers (one item or enemy far above its tier), dead ends (a stage with no way to get what the next
  needs), degenerate strategies (one action that beats everything), and runaway economies.
- Measure with a scripted playthrough where possible; propose number changes with the measurement, and leave
  balance decisions that change the game's direction to the user.

## Assets

- Every asset has a budget: triangles, texture size, file size, materials (draw calls), audio length and loudness.
  Audit against the budget with measured values and list offenders.
- Find orphans (files nothing references) and missing references (code naming a file that does not exist).
- Record source and licence of every third-party asset next to it; attribution-required licences must also show in
  the game's credits.

## Art direction

- Before producing a batch of characters or props, write the visual target down: references, what is out of
  bounds, scale, palette, level of detail at the game camera's distance. Judge every new asset against it from the
  game camera, not from a close-up turntable only.
- Show a small sample and get the look approved before making a whole set.

## Sound

- Check placement (2D for interface, 3D with distance roll-off for world sounds), source fit (the recording matches
  the action and the material), variation (several takes, small pitch and level spread, no immediate repeats),
  timing against the animation frame, and the ambience bed under the effects.
- What cannot be judged by measurement (taste, timbre) is rendered to short videos with sound for the user to listen
  to; say plainly that it was not heard.

## Performance

- Agree a target device and frame rate, then budgets (frame ms, draw calls, triangles on screen, memory). Profile
  on or near the target; rank fixes by measured gain.

## Playtests and regressions

- Turn playtest notes into findings with a place, a reproduction and a severity; separate facts from opinions.
- Every fixed bug gets a test that would have caught it, added in the same change. Keep a short list of the tests
  that cover the critical path (start, core loop, save and load, the end of the chapter) and run it before merging.
- Any change to the save format ships with a test that loads a save from before the change.

## Scope

- Before adding a feature, compare the current state with the written plan; name additions, estimate their cost, and
  propose cuts when the plan is slipping. A feature that is not in the plan needs the user's agreement.

## Driving the editor and Blender

- When the Unity MCP or Blender MCP server is connected, prefer it for inspecting scenes, reading the console and
  taking viewport captures; keep batch scripts for repeatable checks that must run unattended.
- Their telemetry must be off and their third-party generation and asset-library integrations unused unless the user
  approved them (setup in `docs/mcp-setup.md` of this harness). Never send the user's prompts or files to a hosted
  service through them.
