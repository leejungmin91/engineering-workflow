# Slack·Discord MCP 연결

MCP는 작업에 필요한 외부 자료를 읽을 때 선택해서 연결합니다. 각 앱에서 연결 범위와 계정을 결정합니다.

| 연결 | 용도 | 사용 환경 |
| --- | --- | --- |
| Slack 공식 MCP | 허용된 워크스페이스에서 메시지와 문서 맥락 조회 | Codex CLI·데스크톱, Claude Code·Claude 앱 |
| Discord 읽기 MCP | 설정한 Discord 채널의 최근 텍스트 조회 | Codex CLI·데스크톱 로컬 환경, Claude Code, Claude Desktop의 로컬 MCP를 사용할 수 있는 환경 |
| 기타 MCP | 같은 절차로 도구를 추가 | 해당 호스트가 지원하는 MCP 전송 방식과 인증에 따름 |

## Slack

Slack 관리자가 MCP 통합을 허용한 워크스페이스를 사용합니다.

- **Codex CLI**에서 `codex mcp add slack --url https://mcp.slack.com/mcp`를 실행합니다. OAuth가 시작되지 않으면 `codex mcp login slack`으로 연결하고 `codex mcp list`로 확인합니다. 설치한 CLI의 `codex mcp add --help`에서 지원 문법을 확인할 수 있습니다. [Slack의 Codex 연결 안내](https://docs.slack.dev/ai/slack-mcp-server/connect-to-harnesses/#connect-to-codex)
- **Codex 데스크톱**에서 MCP 설정의 Slack 연결을 확인하고 해당 워크스페이스로 OAuth를 완료합니다. CLI와 데스크톱에서 로컬 Codex MCP 설정을 공유합니다. [OpenAI MCP 안내](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
- **Claude Code**에서 `claude plugin install slack@claude-plugins-official`을 실행하고 Slack OAuth를 완료합니다. **Claude 앱**에서는 Customize → Connectors → Add에서 Slack을 선택합니다. [Slack의 Claude 연결 안내](https://docs.slack.dev/ai/slack-mcp-server/connect-to-claude/)

Slack 공식 MCP는 승인된 범위에 따라 쓰기 도구도 노출할 수 있습니다. 이 워크플로는 맥락 조회에 사용하며, 채널에 게시할 때는 사용자에게 대상과 작업을 확인합니다. 서버 수준에서 쓰기를 막아야 한다면 해당 워크스페이스의 OAuth 권한과 관리 정책으로 제한합니다.

## Discord

1. 이 저장소를 로컬에 복제하고 Python 3.11 이상으로 가상 환경을 만든 다음 `python -m pip install -r integrations/discord/requirements.txt`를 실행합니다. 이후 아래 예시에서 그 가상 환경의 Python을 절대 경로로 지정합니다.
2. Discord Developer Portal에서 관리하는 봇을 대상 서버에 설치하고, 사용할 텍스트 채널에 `View Channel`과 `Read Message History` 권한을 줍니다. 메시지 본문 조회에 필요한 Message Content Intent는 봇 설정과 Discord 정책에 따릅니다. [Discord 메시지 API](https://docs.discord.com/developers/resources/message#get-channel-messages) · [Discord 앱 가이드](https://docs.discord.com/developers/quick-start/getting-started)
3. 로컬 비밀 파일이나 MCP 프로세스에 제공한 `DISCORD_BOT_TOKEN` 환경변수로 봇 토큰을 전달합니다. 예시처럼 토큰 파일을 쓰면 토큰을 명령 인자나 호스트 설정에 넣을 필요가 없습니다. 비밀 파일은 저장소 밖에 두고 본인만 읽을 수 있게 관리합니다.

### CLI

경로와 채널 ID를 실제 값으로 바꿉니다. 채널을 여러 개 허용하려면 `--channel`을 반복합니다. Windows에서는 가상 환경의 `Scripts/python.exe` 절대 경로를 사용합니다.

```sh
codex mcp add discord -- /path/to/venv/bin/python /path/to/harness/integrations/discord/server.py --channel 123456789012345678 --token-file /path/to/private/discord-token
claude mcp add --scope user --transport stdio discord -- /path/to/venv/bin/python /path/to/harness/integrations/discord/server.py --channel 123456789012345678 --token-file /path/to/private/discord-token
```

### 데스크톱 앱

Codex 데스크톱의 로컬 MCP 설정에서 CLI로 추가한 서버를 사용할 수 있습니다. Claude Desktop은 로컬 MCP 설정을 열고 기존 `mcpServers` 객체에 아래 `discord` 항목을 추가한 뒤 다시 시작합니다. 로컬 MCP를 실행할 수 있는 앱 모드에서 사용합니다. [Claude Desktop 로컬 MCP 안내](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop) · [앱과 웹의 커넥터 범위](https://support.claude.com/en/articles/11725091-when-to-use-desktop-and-web-connectors)

```json
{
  "mcpServers": {
    "discord": {
      "command": "/path/to/venv/bin/python",
      "args": [
        "/path/to/harness/integrations/discord/server.py",
        "--channel", "123456789012345678",
        "--token-file", "/path/to/private/discord-token"
      ]
    }
  }
}
```

연결을 확인하려면 허용된 채널에서 최근 메시지 한 건을 읽도록 요청합니다. 서버는 읽기 도구 하나를 제공하고 요청당 최대 20건을 반환합니다. 서버에서 읽어 온 메시지는 참고 자료로 취급합니다.

### 연결 추가

다른 서비스가 필요하면 해당 호스트에서 공식 MCP나 검토한 MCP를 등록합니다. 작업 스킬은 연결 목록과 별도로 업데이트할 수 있습니다.
