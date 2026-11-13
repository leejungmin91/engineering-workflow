# 선택형 스킬 색인 훅

턴이 끝나면 남은 변경을 커밋·푸시하는 `Stop` 훅은 플러그인에 포함되어 있다. 동작과 한계는 [훅 안내](../../plugins/engineering-workflow/skills/engineering-workflow/references/hook-recommendations.md)를 본다. 이 폴더에는 선택형 스킬 색인 훅의 설정 예제만 남긴다.

## 스킬 색인 훅

[스킬 색인 안내](../../plugins/engineering-workflow/skills/engineering-workflow/references/skill-index.md)대로 색인을 만든 뒤 `skill-index.example.json`의 스크립트와 색인 경로를 로컬 절대 경로로 바꾼다. Python 실행 파일이 `python3`가 아니라면 해당 실행 파일의 절대 경로를 쓴다.

- Codex는 프로젝트의 `.codex/hooks.json` 또는 사용자 `~/.codex/hooks.json`에 `UserPromptSubmit`을 병합하고, CLI의 `/hooks`에서 새 훅을 검토하고 신뢰한다.
- Claude Code는 프로젝트의 `.claude/settings.local.json` 또는 사용자 `~/.claude/settings.json`에 `UserPromptSubmit`을 병합하고, `/hooks`에서 확인한다.
- 기존 훅이 있다면 해당 배열에 새 항목을 추가한다. 호스트의 기본 스킬 목록이 이미 맞는 스킬을 찾는다면 이 훅은 필요 없다.

이 훅은 프롬프트를 로컬에서 읽어 후보 이름을 최대 3개만 돌려준다. 스킬을 불러오거나 프롬프트를 디스크에 쓰지 않는다. 후보 목록은 요청에 맥락을 더하므로 토큰 절감을 주장하기 전에 실제 사용량을 측정한다.

[Codex 훅 문서](https://learn.chatgpt.com/docs/hooks) · [Claude Code 훅 문서](https://code.claude.com/docs/en/hooks)
