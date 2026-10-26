from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERVER = PLUGIN_ROOT / "server" / "cet_mww_server.py"
sys.path.insert(0, str(PLUGIN_ROOT / "server"))

from storage import LexiconError, LexiconStore  # noqa: E402
from word_export import V, W, is_current  # noqa: E402


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
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        self.process.wait(timeout=5)
        if self.process.stdout and not self.process.stdout.closed:
            self.process.stdout.close()
        if self.process.stderr and not self.process.stderr.closed:
            self.process.stderr.close()


class EndToEndTest(unittest.TestCase):
    def test_complete_persistent_workflow(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cet-mww-test-") as temp:
            data_dir = Path(temp) / "CET-Lexicon"
            client = McpClient(data_dir)
            self.addCleanup(client.close)
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
            self.addCleanup(restarted.close)
            persisted = restarted.call("read_lexicon", {"include_markdown": True})
            self.assertEqual(set(persisted["entries"]), {"alienating", "bleak"})
            self.assertEqual(persisted["current_exam"], {"level": "CET-6", "year": 2025, "month": 6, "set_number": 2})
            self.assertTrue((data_dir / "vocabulary.json").exists())
            self.assertTrue((data_dir / "CET-Lexicon.md").exists())
            self.assertEqual(persisted["word_path"], str((data_dir / "CET-Lexicon.docx").resolve()))
            with ZipFile(persisted["word_path"]) as archive:
                self.assertIsNone(archive.testzip())
                for name in archive.namelist():
                    if name.endswith((".xml", ".rels")):
                        ET.fromstring(archive.read(name))
                root = ET.fromstring(archive.read("word/document.xml"))
                text = "".join(root.itertext())
                self.assertIn("The outlook remains bleak.", text)
                self.assertIn("不乐观的；前景暗淡的", text)
                self.assertIn("令人反感的", text)
                self.assertNotIn("alienatinge", text)
                self.assertIn("2024年12月四级第1套", text)
                self.assertLess(text.index("试卷目录"), text.index("The outlook remains bleak."))
                self.assertLess(text.index("字母索引"), text.index("The outlook remains bleak."))
                self.assertIn("释义 1", text)
                self.assertIn("例句", text)
                cols = root.findall(f".//{{{W}}}sectPr/{{{W}}}cols")
                self.assertEqual([c.attrib[f"{{{W}}}num"] for c in cols], ["1", "2"])
                for header_name in ("word/header1.xml", "word/header2.xml"):
                    header = ET.fromstring(archive.read(header_name))
                    line = header.find(f".//{{{V}}}line")
                    self.assertIsNotNone(line)
                    self.assertEqual(line.attrib["strokecolor"], "#24546A")
                    self.assertEqual(line.attrib["strokeweight"], "0.5pt")
                bookmarks = root.findall(f".//{{{W}}}bookmarkStart")
                names = {b.attrib[f"{{{W}}}name"] for b in bookmarks}
                self.assertEqual(len([name for name in names if name.startswith("word_")]), 2)
                self.assertTrue({"paper_index", "alphabet_index", "entry_body"}.issubset(names))
                self.assertEqual(len({b.attrib[f"{{{W}}}id"] for b in bookmarks}), len(bookmarks))
                for link in root.findall(f".//{{{W}}}hyperlink"):
                    self.assertIn(link.attrib[f"{{{W}}}anchor"], names)
            restarted.close()

    def test_paraphrased_gloss_does_not_duplicate_same_chinese_sense(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cet-mww-sense-merge-") as temp:
            store = LexiconStore(temp)
            store.save_or_update_entry(BLEAK)
            same_sense = {"headword": "bleak", "parts_of_speech": [{"pos": "adjective", "senses": [{
                "zh": "不乐观的；前景暗淡的", "en": "without much hope",
                "examples": [{"en": "The future looks bleak.", "zh": "未来看起来不容乐观。"}],
            }]}]}
            store.save_or_update_entry(same_sense)
            entry = store.read_lexicon(headword="bleak")["entries"]["bleak"]
            senses = entry["parts_of_speech"][0]["senses"]
            self.assertEqual(len(senses), 2)
            self.assertEqual(senses[0]["en"], BLEAK["parts_of_speech"][0]["senses"][0]["en"])
            self.assertEqual(len(senses[0]["examples"]), 2)

    def test_existing_data_migrates_without_changing_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cet-mww-migrate-") as temp:
            store = LexiconStore(temp)
            store.save_or_update_entry(BLEAK)
            original = store.json_path.read_bytes()
            store.word_path.unlink()
            status = store.initialize()
            self.assertEqual(store.json_path.read_bytes(), original)
            self.assertTrue(Path(status["word_path"]).exists())
            self.assertTrue(is_current(store.word_path, json.loads(original)))
            store.word_path.write_bytes(b"broken word file")
            store.read_lexicon()
            self.assertTrue(is_current(store.word_path, json.loads(original)))
            self.assertEqual(store.json_path.read_bytes(), original)

    def test_word_open_does_not_change_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cet-mww-word-open-") as temp:
            store = LexiconStore(temp)
            store.initialize()
            original = store.json_path.read_bytes()
            (Path(temp) / "~$CET-Lexicon.docx").touch()
            with self.assertRaisesRegex(LexiconError, "先关闭 Word"):
                store.save_or_update_entry(BLEAK)
            self.assertEqual(store.json_path.read_bytes(), original)

    def test_generation_failure_preserves_old_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cet-mww-word-failure-") as temp:
            store = LexiconStore(temp)
            store.save_or_update_entry(BLEAK)
            paths = [store.json_path, store.markdown_path, store.word_path]
            before = [p.read_bytes() for p in paths]
            with patch("storage.render_word", side_effect=ValueError("export failed")):
                with self.assertRaises(ValueError):
                    store.save_or_update_entry(ALIENATING)
            self.assertEqual([p.read_bytes() for p in paths], before)

    def test_export_write_failure_is_reported_and_repairable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cet-mww-export-write-") as temp:
            store = LexiconStore(temp)
            store.initialize()
            original_word = store.word_path.read_bytes()
            with patch.object(store, "_write_word", side_effect=OSError("disk write failed")):
                with self.assertRaisesRegex(LexiconError, "数据已保存到 JSON"):
                    store.save_or_update_entry(BLEAK)
            self.assertEqual(store.word_path.read_bytes(), original_word)
            self.assertIn("bleak", json.loads(store.json_path.read_bytes())["entries"])
            store.read_lexicon()
            self.assertTrue(is_current(store.word_path, json.loads(store.json_path.read_bytes())))

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
