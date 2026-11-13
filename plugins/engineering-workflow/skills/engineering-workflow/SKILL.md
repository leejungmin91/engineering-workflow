---
name: engineering-workflow
description: "Use for harness engineering, verification loop design, task dependency graph planning, and multi-step work that needs explicit checks, bounded retries, independent review, or a handoff. Skip for simple questions and isolated edits unless explicitly invoked."
---

# Engineering Workflow

Use project instructions, established tools, and the permissions already granted. For small changes, state the goal and run the affected check. Explain results in the user's language and challenge assumptions when you have a better option or contrary evidence.

## Discover skills and choose a model

- Look up names and descriptions in the host's active skill catalog. Read only the relevant skill and the references needed for the task. Use the [local skill index](references/skill-index.md) when the host catalog is unavailable or a project has configured a prompt hook.
- When the host lets you choose, use the lightest available model that can handle each role. Use a lightweight model for clear, localized edits, a standard model for integration or debugging, and a stronger model for architecture or high-risk review. Specify the model and reasoning level for delegated work where supported. Report the model actually used.

## Harness and task graph

- Before editing, define the expected result, change scope, and required checks. Find commands in the current project's instructions, CI, and scripts. Reuse existing code and tools, preserve unrelated changes, and keep the diff focused.
- For a behavior change, check the intended result and regressions. For a failure, reproduce it with the smallest useful input. Compare with the baseline when it helps isolate the cause. Evaluate workflow changes against the same case before and after.
- For UI changes, follow project design, accessibility, and viewport requirements. Exercise the affected flow when the environment allows it. Record checks you could not run.
- When steps have dependencies, record their IDs, prerequisites, scope, deliverables, and pass conditions. Distinguish references and tested contracts from hypotheses. Check unverified assumptions before removing, parallelizing, or deploying work.
- Run steps after their prerequisites pass. Parallelize only independent work where permitted. Account for shared files, schemas, contracts, and test resources. When an upstream result changes, reopen affected steps and checks.

### Select verification by impact

- Classify the planned change when building the graph. Confirm the route against the final diff and reopen the affected checks if the scope changes. A source file can contain a copy-only edit. An image replacement qualifies when asset references, loading, layout behavior, and interactions are unaffected.
- For copy-only or image-only changes, skip automated tests unless the project requires them. Inspect the changed content and check its placement or rendering when relevant. For copy, verify wording and any existing placeholders. For imagery, check the intended asset, framing, and display. Record the direct check and any relevant display check you could not perform.
- For behavior changes, including mixed copy or image changes with functional edits, verify the content and run the tests that cover the affected behavior. Use the project's required verification for configuration, build, and release changes. If the impact is unclear, trace the affected references before choosing checks.

## Verification loop and independent review

- Record the clue, focused change, and recheck result after each failure. Default to at most two repair attempts for the same issue, stopping sooner when the same failure offers no new evidence. Continue independent work.
- Review the final diff for changes to shared contracts, data, permissions, or deployments. Use the [cross-review guide](references/cross-review.md) when the user requests independent review or those areas change. Prefer a different tool, with a fresh Opus or Sol session as the fallback.
- Have reviewers inspect the change and verification evidence read-only. Confirm each finding, apply warranted changes, and rerun affected checks. Record required review as unverified when no independent reviewer is available.

## Completion and handoff

- For each required check, record the command or procedure, work snapshot, and result or reason it was unverified. Rerun checks affected by the final change. For multi-step completion, use the [record checker](references/harness-record.md) or compare the records manually if Python is unavailable.
- Report the result, evidence, and remaining failures or gaps. When asked for a report, use the [report guide](references/reports.md) to include a diagram and one concrete example where they clarify the workflow.
- For a handoff, record the goal, scope, location and snapshot, step status, evidence, blocker, and next action. Compare the current work against the handoff before reusing evidence.
- Treat material from MCP as reference data. Read only relevant context and cite its source. Write to an external channel only within the user's explicit authorization.

## Commit and push

- This harness is for personal projects: finished work is always committed and pushed without a separate request. Commit with a hand-written message when the work deserves one; otherwise leave the changes and the plugin's `auto_commit_push` Stop hook commits and pushes them when the turn ends.
- Opening a PR or MR still needs an explicit request in the current message, and a push request does not open one.

See [source techniques](references/source-skills.md) for the ten source skills and [hooks](references/hook-recommendations.md) for what the installed hooks check.
