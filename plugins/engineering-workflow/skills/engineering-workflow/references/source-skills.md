# GitHub 상위 저장소의 스킬 10개와 적용한 규칙

2026-11-11 한국 시간에 확인했다. GitHub의 스타는 스킬 파일이 아니라 저장소에 매겨진다. [The Skill Leaderboard](https://www.skillleaderboard.com/)와 [HotSkills](https://hotskills.dev/)의 후보를 합치고, 스킬이나 스킬 묶음이 주 산출물인 공개 저장소를 대상으로 GitHub API의 스타 수를 비교했다. 별도 에이전트 런타임·앱은 순위에서 뺐다. 두 목록에서 찾은 후보 기준이며 GitHub 전체 순위를 뜻하지 않는다.

각 저장소에서 하네스에 쓸 대표 스킬을 하나 골라 표시된 커밋에서 지침을 읽었다. 아래는 원문을 우리 전역 워크플로에 맞게 바꿔 쓴 규칙이다. 원본 플러그인, 설치 프로그램, 패키지는 설치하지 않았다.

| 순위 | GitHub 저장소 | 스타 | 대표 스킬 | 전역 하네스에 반영 |
| ---: | --- | ---: | --- | --- |
| 1 | [mattpocock/skills](https://github.com/mattpocock/skills) | 321,436 | [diagnosing-bugs](https://github.com/mattpocock/skills/blob/4ae2317ddb22b046e26455e4f9c9b3aaaf62212d/skills/engineering/diagnosing-bugs/SKILL.md) | 같은 증상을 빠르게 재현하는 입력이나 검사부터 만든다. |
| 2 | [obra/superpowers](https://github.com/obra/superpowers) | 315,984 | [verification-before-completion](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/verification-before-completion/SKILL.md) | 마지막 변경 이후의 통과 결과가 있어야 완료로 판단한다. |
| 3 | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 301,006 | [eval-harness](https://github.com/affaan-m/ECC/blob/d2ef2680594f9a17526a6e1a2e18b3d242c5d17b/skills/eval-harness/SKILL.md) | 성공 기준과 회귀 사례를 먼저 정하고 같은 사례로 개선 전후를 비교한다. |
| 4 | [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) | 232,033 | [karpathy-guidelines](https://github.com/multica-ai/andrej-karpathy-skills/blob/2c606141936f1eeef17fa3043a72095b4765b9c2/skills/karpathy-guidelines/SKILL.md) | 작업 범위와 확인 기준을 먼저 정하고 관련 없는 diff를 피한다. |
| 5 | [anthropics/skills](https://github.com/anthropics/skills) | 192,772 | [webapp-testing](https://github.com/anthropics/skills/blob/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/webapp-testing/SKILL.md) | UI 동작은 허용된 실제 화면에서 사용자 경로를 실행해 확인한다. |
| 6 | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 188,704 | [ponytail](https://github.com/DietrichGebert/ponytail/blob/96608e078b2d5ea607c5c3b8b5a54d1c1fba6846/skills/ponytail/SKILL.md) | 새 코드보다 기존 구현과 도구를 먼저 살펴본다. |
| 7 | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 147,999 | [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/6ae86f61f520d6ca229d2f40e070410638c908c5/.claude/skills/ui-ux-pro-max/SKILL.md) | UI 검사에 접근성과 영향을 받는 화면 크기를 넣는다. |
| 8 | [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | 145,877 | [graphify (Codex)](https://github.com/Graphify-Labs/graphify/blob/35d1d2038b9e9d470f117bf8f2473d415b5f5358/graphify/skill-codex.md) | 작업 의존성이 출처에서 확인됐는지 추정인지 표시한다. |
| 9 | [garrytan/gstack](https://github.com/garrytan/gstack) | 141,160 | [review](https://github.com/garrytan/gstack/blob/f0cd9f8c4b453c1eadd714e4149174ee01179eae/review/SKILL.md) | 통과 여부와 별도로 최종 diff에서 계약, 데이터, 권한 영향을 검토한다. |
| 10 | [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | 119,000 | [caveman](https://github.com/JuliusBrussee/caveman/blob/3dc497a7f858c774d6e15b25e8c6120ef3a0eda8/skills/caveman/SKILL.md) | 결과와 근거부터 짧게 말하고 중요한 조건은 생략하지 않는다. |
