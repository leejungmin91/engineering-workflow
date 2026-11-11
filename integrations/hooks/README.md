# 선택형 Git PreToolUse 훅

`pre-tool-use.example.json`에서 스크립트 경로를 로컬 체크아웃의 절대 경로로 바꾼다. Python 실행 파일이 `python3`가 아니라면 해당 실행 파일의 절대 경로를 사용한다.

- Codex는 프로젝트의 `.codex/hooks.json` 또는 사용자 `~/.codex/hooks.json`에 `PreToolUse`를 병합하고, CLI의 `/hooks`에서 새 훅을 검토하고 신뢰한다.
- Claude Code는 프로젝트의 `.claude/settings.local.json` 또는 사용자 `~/.claude/settings.json`에 `PreToolUse`를 병합하고, `/hooks`에서 확인한다.
- 기존 훅이 있다면 해당 배열에 새 항목을 추가한다. 설치한 플러그인은 이 설정을 자동으로 등록하지 않는다.

이 예제는 한 줄에 쓴 첫 직접 `git` 명령의 리터럴 옵션을 검사한다. `git -C <경로>`도 지원한다. 줄 연속, 셸 변수나 별칭, 복잡한 인용, 옵션을 취소하는 부정 플래그가 포함된 명령은 호스트 권한과 Git 보호 규칙에서 다룬다. 읽기 명령과 드라이런은 통과한다. 허용·거부 테스트는 저장소 루트에서 `python3 -m unittest discover -s integrations/hooks`로 실행한다. 테스트는 JSON을 훅에 전달하며 Git 명령을 실행하지 않는다.

[Codex 훅 문서](https://learn.chatgpt.com/docs/hooks) · [Claude Code 훅 문서](https://code.claude.com/docs/en/hooks)
