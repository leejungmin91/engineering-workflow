# 게임 개발용 상위 저장소와 반영한 규칙

2026-11-15 한국 시간에 GitHub API로 확인했다. 스타는 저장소에 매겨진다. 게임 개발용 에이전트 도구 중 스타가 많은 저장소를 골라 고정 커밋에서 읽었다. 하네스에는 원문을 우리 형식으로 바꿔 쓴 규칙(`../SKILL.md`)과 설치 안내(`docs/mcp-setup.md`)만 넣었다. 원본 플러그인과 MCP 서버는 자동으로 설치하지 않는다.

| 저장소 | 스타 | 라이선스 | 고정 커밋 | 분류 | 하네스에 넣은 방식 |
| --- | ---: | --- | --- | --- | --- |
| [Donchitos/Claude-Code-Game-Studios](https://github.com/Donchitos/Claude-Code-Game-Studios) | 39,344 | MIT | `abc0de79d6ce` | 에이전트 49개, 스킬 72개 | 아래 8개 스킬의 규칙을 `game-dev` 스킬로 옮김 |
| [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) (현재 이름 mcp-for-blender) | 34,458 | MIT | `8f40787fbde8` | Blender MCP 서버와 애드온 | 설치 안내와 필수 안전 설정 |
| [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) | 15,975 | MIT | `5914ce5bd9d1` | Unity 에디터 MCP | 설치 안내와 필수 안전 설정 |
| [IvanMurzak/Unity-MCP](https://github.com/IvanMurzak/Unity-MCP) | 4,637 | Apache-2.0 | — | Unity MCP·CLI | 대안으로만 기록 |

## Claude-Code-Game-Studios에서 읽은 스킬

| 스킬 | 반영한 규칙 |
| --- | --- |
| [balance-check](https://github.com/Donchitos/Claude-Code-Game-Studios/blob/abc0de79d6ceb0b5d7aa693945849b3937afbe6a/.claude/skills/balance-check/SKILL.md) | 입력마다 FOUND·ABSENT를 적고, 데이터가 없으면 `NOT ASSESSED — NO DATA`로 답한다. 이상치, 막힌 진행, 압도적 전략, 경제 폭주를 찾는다. |
| [asset-audit](https://github.com/Donchitos/Claude-Code-Game-Studios/blob/abc0de79d6ceb0b5d7aa693945849b3937afbe6a/.claude/skills/asset-audit/SKILL.md) | 크기·형식은 측정 명령으로만 채우고, 측정할 수 없으면 추정하지 않는다. 고아 파일과 깨진 참조를 찾는다. |
| [perf-profile](https://github.com/Donchitos/Claude-Code-Game-Studios/blob/abc0de79d6ceb0b5d7aa693945849b3937afbe6a/.claude/skills/perf-profile/SKILL.md) | 예산 대비 측정, 측정된 이득 순으로 개선안을 낸다. |
| [playtest-report](https://github.com/Donchitos/Claude-Code-Game-Studios/blob/abc0de79d6ceb0b5d7aa693945849b3937afbe6a/.claude/skills/playtest-report/SKILL.md) | 플레이 메모를 장소·재현·심각도가 있는 발견으로 정리한다. |
| [regression-suite](https://github.com/Donchitos/Claude-Code-Game-Studios/blob/abc0de79d6ceb0b5d7aa693945849b3937afbe6a/.claude/skills/regression-suite/SKILL.md) | 고친 버그마다 그 버그를 잡았을 시험을 붙이고, 핵심 경로 시험 목록을 유지한다. |
| [scope-check](https://github.com/Donchitos/Claude-Code-Game-Studios/blob/abc0de79d6ceb0b5d7aa693945849b3937afbe6a/.claude/skills/scope-check/SKILL.md) | 계획 문서와 현재 상태를 비교해 추가분과 비용을 밝히고 자를 것을 제안한다. |
| [art-bible](https://github.com/Donchitos/Claude-Code-Game-Studios/blob/abc0de79d6ceb0b5d7aa693945849b3937afbe6a/.claude/skills/art-bible/SKILL.md) | 에셋을 대량으로 만들기 전에 시각 기준을 글로 정한다. |
| [vertical-slice](https://github.com/Donchitos/Claude-Code-Game-Studios/blob/abc0de79d6ceb0b5d7aa693945849b3937afbe6a/.claude/skills/vertical-slice/SKILL.md) | 핵심 루프 하나를 완성 품질로 끝까지 만들어 제작 속도와 파이프라인을 확인한다. |

이 저장소는 스킬마다 `model:`을 지정한다(검토·감사는 sonnet, 범위 점검은 haiku). 우리 하네스의 "역할을 감당하는 가장 가벼운 모델" 지침과 같은 방향이다.

## MCP 서버를 쓸 때 반드시 지킬 것

두 서버 모두 기본으로 사용 통계를 외부로 보낸다. 우리 하네스는 사용자의 프롬프트와 산출물을 외부 서비스로 보내지 않으므로, 설치할 때 아래를 반드시 적용한다.

| 서버 | 확인한 내용 | 끄는 방법 |
| --- | --- | --- |
| blender-mcp | `src/blender_mcp/telemetry.py`가 도구 호출을 기록해 전송한다. 도구들은 `user_prompt` 인자를 받는다. Poly Haven, Sketchfab, Poly Pizza, Hunyuan3D, Hyper3D, Meshy, Tripo, World Labs 연동이 있다 | 환경 변수 `DISABLE_TELEMETRY=1`(또는 `BLENDER_MCP_DISABLE_TELEMETRY=1`). 생성·라이브러리 연동은 애드온에서 끄고, 쓰려면 사용자에게 먼저 묻는다 |
| unity-mcp | `Server/src/core/telemetry.py`가 `https://api-prod.coplay.dev/telemetry/events`로 보낸다. 에디터 쪽 `TelemetryHelper.cs`도 있다 | 서버와 Unity 에디터 양쪽에 `DISABLE_TELEMETRY=1`(또는 `UNITY_MCP_DISABLE_TELEMETRY=1`), 에디터 설정의 텔레메트리 끄기 |

설치 스크립트를 인터넷에서 받아 바로 실행하는 방식(`curl … | sh`, `irm … | iex`)은 쓰지 않고, 버전을 고정해 설치한다.
