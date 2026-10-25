from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERVER = PLUGIN_ROOT / "server" / "cet_mww_server.py"
sys.path.insert(0, str(PLUGIN_ROOT / "server"))

from storage import LexiconError, LexiconStore  # noqa: E402


BLEAK = {
    "headword": "bleak",
    "pronunciations": {"uk": "/bliːk/", "us": "/bliːk/"},
    "parts_of_speech": [
        {
            "pos": "adjective",
            "senses": [
                {
                    "zh": "不乐观的；前景暗淡的",
                    "en": "not hopeful or encouraging",
                    "examples": [{"en": "The outlook remains bleak.", "zh": "前景依然黯淡。"}],
                },
                {
                    "zh": "阴冷的；荒凉的",
                    "en": "cold, empty, and unattractive",
                    "examples": [{"en": "They crossed a bleak winter landscape.", "zh": "他们穿过了一片阴冷荒凉的冬日景色。"}],
                },
            ],
        }
    ],
    "collocations": [
        {"en": "a bleak outlook", "zh": "黯淡的前景"},
        {"en": "a bleak future", "zh": "暗淡的未来"},
        {"en": "look bleak", "zh": "看起来不容乐观"},
    ],
    "cet_notes": ["阅读中常用来描述前景、形势或未来。"],
}

ALIENATING = {
    "headword": "alienating",
    "pronunciations": {"uk": "/ˈeɪliəneɪtɪŋ/", "us": "/ˈeɪliəneɪtɪŋ/"},
    "parts_of_speech": [
        {
            "pos": "adjective",
            "senses": [
                {
                    "zh": "使人疏远的；令人产生隔阂的",
                    "en": "causing someone to feel isolated or unfriendly",
                    "examples": [
                        {"en": "The policy had an alienating effect on young voters.", "zh": "这项政策使年轻选民产生了疏离感。"},
                        {"en": "The website's cold tone can be alienating.", "zh": "这个网站冷冰冰的语气可能让人感到疏远。"},
                    ],
                }
            ],
        }
    ],
    "collocations": [
        {"en": "an alienating effect", "zh": "疏离作用"},
        {"en": "an alienating experience", "zh": "令人感到疏离的经历"},
    ],
    "cet_notes": ["可由动词 alienate 的现在分词转化为形容词。"],
}


class McpClient:
    def __init__(self, data_dir: Path):
        env = os.environ.copy()
        env["CET_MWW_DATA_DIR"] = str(data_dir)
        self.process = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        self.next_id = 1
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
        self.notify("notifications/initialized", {})

    def request(self, method: str, params: dict) -> dict:
        request_id = self.next_id
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        response = json.loads(self.process.stdout.readline())
        self.assert_response(response, request_id)
        return response["result"]

    @staticmethod
    def assert_response(response: dict, request_id: int) -> None:
        if response.get("id") != request_id or "error" in response:
            raise AssertionError(response)

    def notify(self, method: str, params: dict) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n")
        self.process.stdin.flush()

    def call(self, name: str, arguments: dict) -> dict:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise AssertionError(result)
        return result["structuredContent"]

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        self.process.wait(timeout=5)
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.stderr:
            self.process.stderr.close()


class EndToEndTest(unittest.TestCase):
    def test_complete_persistent_workflow(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cet-mww-test-") as temp:
            data_dir = Path(temp) / "CET-Lexicon"
            client = McpClient(data_dir)
            tools = client.request("tools/list", {})["tools"]
            self.assertEqual([tool["name"] for tool in tools], ["switch_exam", "save_or_update_entry", "read_lexicon"])

            client.call("switch_exam", {"level": "CET-4", "year": 2024, "month": 12, "set_number": 1})
            first = client.call("save_or_update_entry", {"entry": BLEAK, "query_form": "bleak"})
            second = client.call("save_or_update_entry", {"entry": ALIENATING, "query_form": "alienating"})
            duplicate = client.call("save_or_update_entry", {"entry": ALIENATING, "query_form": "alienatinge"})
            self.assertTrue(first["created"])
            self.assertTrue(second["created"])
            self.assertTrue(duplicate["deduplicated"])
            self.assertEqual(duplicate["entry_count"], 2)
            by_word = client.call("read_lexicon", {"headword": "alienatinge"})
            self.assertEqual(list(by_word["entries"]), ["alienating"])
            self.assertIn("alienatinge", by_word["entries"]["alienating"]["aliases"])

            corrected = dict(ALIENATING)
            corrected["parts_of_speech"] = [
                {
                    "pos": "adjective",
                    "senses": [
                        {"zh": "使人疏远的；令人感到孤立的", "en": "making people feel isolated", "examples": []},
                        {"zh": "令人反感的", "en": "causing dislike", "examples": []},
                    ],
                }
            ]
            replaced = client.call(
                "save_or_update_entry",
                {"entry": corrected, "query_form": "alienating", "update_mode": "replace_fields"},
            )
            self.assertTrue(replaced["deduplicated"])
            corrected_read = client.call("read_lexicon", {"headword": "alienating"})
            senses = corrected_read["entries"]["alienating"]["parts_of_speech"][0]["senses"]
            self.assertEqual(len(senses), 2)

            switched = client.call("switch_exam", {"level": "CET-6", "year": 2025, "month": 6, "set_number": 2})
            self.assertEqual(switched["current_exam"]["level"], "CET-6")
            opened = client.call("read_lexicon", {"include_markdown": True})
            self.assertIn("# CET Lexicon", opened["markdown"])
            self.assertIn("2024年12月四级第1套", opened["markdown"])
            self.assertEqual(opened["markdown"].count("### alienating"), 1)
            self.assertEqual(opened["entry_count"], 2)
            client.close()

            restarted = McpClient(data_dir)
            persisted = restarted.call("read_lexicon", {"include_markdown": True})
            self.assertEqual(set(persisted["entries"]), {"alienating", "bleak"})
            self.assertEqual(persisted["current_exam"], {"level": "CET-6", "year": 2025, "month": 6, "set_number": 2})
            self.assertTrue((data_dir / "vocabulary.json").exists())
            self.assertTrue((data_dir / "CET-Lexicon.md").exists())
            restarted.close()

    def test_corrupt_source_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cet-mww-corrupt-") as temp:
            data_dir = Path(temp) / "CET-Lexicon"
            store = LexiconStore(data_dir)
            store.initialize()
            corrupt = b'{"schema_version": 1, "entries": '
            store.json_path.write_bytes(corrupt)
            with self.assertRaises(LexiconError):
                store.save_or_update_entry(BLEAK)
            self.assertEqual(store.json_path.read_bytes(), corrupt)


if __name__ == "__main__":
    unittest.main()
