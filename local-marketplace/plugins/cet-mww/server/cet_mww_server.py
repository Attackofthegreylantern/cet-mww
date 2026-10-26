#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from storage import LexiconError, LexiconStore  # noqa: E402


SERVER_INFO = {"name": "cet-mww-storage", "version": "1.4.0"}


TOOLS = [
    {
        "name": "switch_exam",
        "description": "Set the active CET paper. Later saved entries are linked to this paper until it is switched again.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["level", "year", "month", "set_number"],
            "properties": {
                "level": {"type": "string", "enum": ["CET-4", "CET-6"]},
                "year": {"type": "integer", "minimum": 2000, "maximum": 2100},
                "month": {"type": "integer", "enum": [6, 12]},
                "set_number": {"type": "integer", "minimum": 1, "maximum": 9},
            },
        },
        "annotations": {"title": "Switch active CET paper", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "save_or_update_entry",
        "description": "Create or update one canonical dictionary entry, deduplicate it, link the active paper, and regenerate Word and Markdown. Close the Word document before saving. Call only after an explicit lookup unless the user says not to save.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["entry"],
            "properties": {
                "entry": {
                    "type": "object",
                    "required": ["headword"],
                    "additionalProperties": False,
                    "properties": {
                        "headword": {"type": "string", "minLength": 1},
                        "pronunciations": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"uk": {"type": "string"}, "us": {"type": "string"}},
                        },
                        "parts_of_speech": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["pos", "senses"],
                                "properties": {
                                    "pos": {"type": "string"},
                                    "senses": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "required": ["zh"],
                                            "properties": {
                                                "zh": {"type": "string"},
                                                "en": {"type": "string"},
                                                "examples": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "object",
                                                        "required": ["en", "zh"],
                                                        "properties": {"en": {"type": "string"}, "zh": {"type": "string"}},
                                                    },
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        "collocations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["en"],
                                "properties": {"en": {"type": "string"}, "zh": {"type": "string"}},
                            },
                        },
                        "cet_notes": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "query_form": {"type": "string", "description": "The spelling or inflected form typed by the user; the entry headword must be canonical."},
                "update_mode": {"type": "string", "enum": ["merge", "replace_fields"], "default": "merge"},
                "save_to_current_exam": {"type": "boolean", "default": True},
            },
        },
        "annotations": {"title": "Save or update vocabulary entry", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "read_lexicon",
        "description": "Read lexicon status and entries, optionally filtered by headword or CET paper. Return word_path for the Word notebook. Include Markdown only when a text preview is needed. Reading can regenerate missing or stale reading files from JSON.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "headword": {"type": "string"},
                "exam": {
                    "type": "object",
                    "required": ["level", "year", "month", "set_number"],
                    "properties": {
                        "level": {"type": "string", "enum": ["CET-4", "CET-6"]},
                        "year": {"type": "integer"},
                        "month": {"type": "integer", "enum": [6, 12]},
                        "set_number": {"type": "integer"},
                    },
                },
                "include_markdown": {"type": "boolean", "default": False},
            },
        },
        "annotations": {"title": "Read CET lexicon", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
    },
]


def tool_result(payload: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": payload,
        "isError": False,
    }


def call_tool(store: LexiconStore, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "switch_exam":
        result = store.switch_exam(arguments)
        exam = result["current_exam"]
        return tool_result(result, f"已切换到 {exam['year']}年{exam['month']}月 {exam['level']} 第{exam['set_number']}套。")
    if name == "save_or_update_entry":
        result = store.save_or_update_entry(
            entry=arguments["entry"],
            query_form=arguments.get("query_form"),
            update_mode=arguments.get("update_mode", "merge"),
            save_to_current_exam=arguments.get("save_to_current_exam", True),
        )
        action = "新增" if result["created"] else "更新（未创建重复词条）"
        return tool_result(result, f"已{action}：{result['headword']}。Word 和 Markdown 已刷新。Word：{result['word_path']}")
    if name == "read_lexicon":
        result = store.read_lexicon(
            headword=arguments.get("headword"),
            exam=arguments.get("exam"),
            include_markdown=arguments.get("include_markdown", False),
        )
        return tool_result(result, f"已读取 {len(result['entries'])} 个词条。Word：{result['word_path']}")
    raise LexiconError(f"未知工具: {name}")


def handle(store: LexiconStore, request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        requested = request.get("params", {}).get("protocolVersion", "2025-06-18")
        result = {
            "protocolVersion": requested,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = request.get("params", {})
        try:
            result = call_tool(store, params.get("name", ""), params.get("arguments", {}))
        except (LexiconError, OSError, KeyError, TypeError, ValueError) as exc:
            result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> int:
    store = LexiconStore()
    try:
        store.initialize()
    except Exception as exc:
        print(f"CET MWW initialization failed: {exc}", file=sys.stderr, flush=True)
    for raw_line in sys.stdin:
        if not raw_line.strip():
            continue
        try:
            request = json.loads(raw_line)
            response = handle(store, request)
            if response is not None:
                print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
        except Exception as exc:  # keep the stdio server alive after a malformed request
            request_id = request.get("id") if isinstance(locals().get("request"), dict) else None
            error = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(exc)}}
            print(json.dumps(error, ensure_ascii=False, separators=(",", ":")), flush=True)
            traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
