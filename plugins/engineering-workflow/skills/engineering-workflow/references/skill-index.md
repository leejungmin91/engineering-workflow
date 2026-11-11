# Skill discovery

Codex and Claude Code expose metadata for available skills. Use the current host catalog first. It includes names and descriptions, so you can choose a relevant skill before loading its instructions. An installed plugin's skill may have a namespaced name such as `engineering-workflow:engineering-workflow`.

The local index is a fallback or an input to the optional prompt hook. It stores names, descriptions, and paths. It does not store skill bodies or prompt history. Pass explicit skill roots, or an exported Codex `skills/list` response or array of skill metadata. Catalog entries marked disabled are excluded. Root discovery reads simple name and description fields, including wrapped descriptions and YAML block scalars. Export the host catalog for other YAML forms. Use an exported active catalog if host availability or precedence matters.

From the skill directory, run:

```sh
python3 scripts/skill_index.py build /absolute/path/to/skill-index.json --root /absolute/path/to/skills
python3 scripts/skill_index.py build /absolute/path/to/skill-index.json --catalog /absolute/path/to/catalog.json
python3 scripts/skill_index.py find /absolute/path/to/skill-index.json "dependency graph" --limit 3
```

Use the build command again when installed skills change. The index does not scan other roots or refresh in the background. A lookup ranks exact names above name and description matches. A small fixed dictionary maps common Korean engineering terms such as `하네스` and `교차검토` to English terms.

To run the lookup before the model receives a prompt, configure the [optional UserPromptSubmit hook](https://github.com/leejungmin91/codex-engineering-workflow/tree/main/integrations/hooks). It returns up to three candidate names as context. The host still decides which skill to load. The hook runs locally without calling a model, transmitting prompts, or saving them. The candidate list adds context to the request, so measure actual token use before claiming a saving.

[Codex hooks](https://learn.chatgpt.com/docs/hooks) · [Claude Code hooks](https://code.claude.com/docs/en/hooks)
