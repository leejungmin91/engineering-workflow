# Completion record

Run project checks first. The checker validates recorded evidence, the supplied work snapshot, and task dependencies. It does not run tests or verify the claims inside a record.

1. Record every required check, including checks that failed or could not run.
2. Identify the work snapshot from the actual inputs, such as a clean commit or a commit plus a working-tree snapshot. The checker requires the same snapshot for every passing check in the file. Keep unaffected older evidence in a handoff or compare it manually when the project permits independent snapshots.
3. Use unique task IDs and unique check IDs within each task. IDs start with an ASCII letter or digit and may contain letters, digits, periods, underscores, and hyphens. Maximum length is 64. Use an empty `after` list for a task without prerequisites. Use `passed`, `failed`, `blocked`, or `unverified`. A passing check needs the snapshot and a short evidence reference.

```json
{
  "tasks": [
    {
      "id": "parser",
      "after": [],
      "checks": [
        {"id": "regression", "status": "passed", "snapshot": "review-2", "evidence": "Four targeted checks passed, exit code 0"}
      ]
    },
    {
      "id": "ui",
      "after": ["parser"],
      "checks": [
        {"id": "error-flow", "status": "unverified"}
      ]
    }
  ]
}
```

Run from the skill directory using Python 3.9 or newer. Pass `-` to read JSON from standard input. Supply the current work snapshot independently of the record.

```sh
python3 scripts/check_record.py /absolute/path/to/record.json --snapshot review-2
```

| Exit code | Meaning |
| --- | --- |
| 0 | All recorded required checks pass for the supplied snapshot |
| 1 | A check failed, is blocked or unverified, or has missing or stale evidence |
| 2 | Invalid input or dependency graph |

The example exits 1 and reports `ui/error-flow: unverified`. The checker does not run recorded commands, print evidence text, or write repository files.
