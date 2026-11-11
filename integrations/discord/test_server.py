import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from server import read_messages

ALLOWED = "123456789012345678"
OTHER = "987654321098765432"
TOKEN = "synthetic-test-token"


class DiscordTests(unittest.TestCase):
    @patch("server.build_opener")
    def test_channel_and_limit_checked_before_network(self, opener):
        for channel, limit in ((OTHER, 10), (ALLOWED, 0), (ALLOWED, 21)):
            with self.subTest(channel=channel, limit=limit), self.assertRaises(ValueError):
                read_messages(channel, limit, {ALLOWED}, TOKEN)
        opener.assert_not_called()

    @patch("server.build_opener")
    def test_get_filters_discord_response(self, opener):
        payload = [{
            "id": "1", "timestamp": "2026-11-11T00:00:00Z", "content": "hello",
            "attachments": [{"filename": "not-returned.txt"}], "author": {"username": "not-returned"},
        }]
        opener.return_value.open.return_value = io.BytesIO(json.dumps(payload).encode())
        result = read_messages(ALLOWED, 1, {ALLOWED}, TOKEN)
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, f"https://discord.com/api/v10/channels/{ALLOWED}/messages?limit=1")
        self.assertEqual(request.get_header("Authorization"), f"Bot {TOKEN}")
        self.assertEqual(result, [{"id": "1", "timestamp": "2026-11-11T00:00:00Z", "content": "hello"}])


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_lists_read_only_tool_and_rejects_unlisted_channel(self):
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("server.py")), "--channel", ALLOWED],
            env={"DISCORD_BOT_TOKEN": TOKEN},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                self.assertEqual([tool.name for tool in tools], ["read_recent_discord_messages"])
                self.assertTrue(tools[0].annotations.read_only_hint)
                rejected = await session.call_tool(tools[0].name, {"channel_id": OTHER})
                self.assertTrue(rejected.is_error)
                self.assertIn("allowlist", rejected.content[0].text)
