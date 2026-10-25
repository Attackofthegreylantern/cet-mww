from __future__ import annotations

import copy
import fcntl
import json
import os
import re
import shutil
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = 1
DEFAULT_DATA_DIR = Path("~/Desktop/CET-Lexicon").expanduser()
KNOWLEDGE_FIELDS = ("pronunciations", "parts_of_speech", "collocations", "cet_notes")


class LexiconError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_headword(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\r\n.,;:!?\"'“”‘’")


def _dedupe(items: list[Any], key) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items:
        marker = key(item)
        if marker not in seen:
            seen.add(marker)
            result.append(item)
    return result


def _text_key(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


def _json_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class LexiconStore:
    def __init__(self, data_dir: Path | str | None = None):
        configured = data_dir or os.environ.get("CET_MWW_DATA_DIR") or DEFAULT_DATA_DIR
        self.data_dir = Path(configured).expanduser().resolve()
        self.json_path = self.data_dir / "vocabulary.json"
        self.markdown_path = self.data_dir / "CET-Lexicon.md"
        self.backup_path = self.data_dir / "vocabulary.json.bak"
        self.lock_path = self.data_dir / ".vocabulary.lock"

    def _empty_data(self) -> dict[str, Any]:
        stamp = now_iso()
        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": stamp,
            "updated_at": stamp,
            "current_exam": None,
            "entries": {},
        }

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.json_path.exists():
            data = self._empty_data()
            self._commit_unlocked(data, make_backup=False)
            return data
        try:
            data = json.loads(self.json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LexiconError(f"无法读取 {self.json_path}: {exc}") from exc
        self._validate(data)
        return data

    def _validate(self, data: Any) -> None:
        if not isinstance(data, dict):
            raise LexiconError("vocabulary.json 顶层必须是 JSON 对象")
        if data.get("schema_version") != SCHEMA_VERSION:
            raise LexiconError(f"不支持的数据版本: {data.get('schema_version')!r}")
        if not isinstance(data.get("entries"), dict):
            raise LexiconError("vocabulary.json 的 entries 必须是对象")
        exam = data.get("current_exam")
        if exam is not None:
            self._validate_exam(exam)

    def _validate_exam(self, exam: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(exam, dict):
            raise LexiconError("试卷信息必须是对象")
        level = str(exam.get("level", "")).upper().replace("CET", "CET-").replace("--", "-")
        if level not in {"CET-4", "CET-6"}:
            raise LexiconError("考试级别必须是 CET-4 或 CET-6")
        try:
            year = int(exam["year"])
            month = int(exam["month"])
            set_number = int(exam["set_number"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LexiconError("年份、月份和套数必须是整数") from exc
        if not 2000 <= year <= 2100:
            raise LexiconError("年份必须在 2000 到 2100 之间")
        if month not in {6, 12}:
            raise LexiconError("四六级考试月份必须是 6 或 12")
        if not 1 <= set_number <= 9:
            raise LexiconError("套数必须在 1 到 9 之间")
        return {"level": level, "year": year, "month": month, "set_number": set_number}

    def _atomic_text(self, path: Path, text: str) -> None:
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=self.data_dir)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def _commit_unlocked(self, data: dict[str, Any], make_backup: bool = True) -> None:
        self._validate(data)
        data["updated_at"] = now_iso()
        json_text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
        markdown_text = render_markdown(data)
        if make_backup and self.json_path.exists():
            backup_tmp = self.backup_path.with_suffix(".bak.tmp")
            shutil.copy2(self.json_path, backup_tmp)
            os.replace(backup_tmp, self.backup_path)
        self._atomic_text(self.json_path, json_text)
        self._atomic_text(self.markdown_path, markdown_text)

    def initialize(self) -> dict[str, Any]:
        with self._locked():
            data = self._load_unlocked()
            if not self.markdown_path.exists():
                self._atomic_text(self.markdown_path, render_markdown(data))
            return self._status(data)

    def _status(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "data_dir": str(self.data_dir),
            "json_path": str(self.json_path),
            "markdown_path": str(self.markdown_path),
            "entry_count": len(data["entries"]),
            "current_exam": data.get("current_exam"),
            "updated_at": data.get("updated_at"),
        }

    def switch_exam(self, exam: dict[str, Any]) -> dict[str, Any]:
        normalized_exam = self._validate_exam(exam)
        with self._locked():
            data = self._load_unlocked()
            data["current_exam"] = normalized_exam
            self._commit_unlocked(data)
            return {"changed": True, **self._status(data)}

    def save_or_update_entry(
        self,
        entry: dict[str, Any],
        query_form: str | None = None,
        update_mode: str = "merge",
        save_to_current_exam: bool = True,
    ) -> dict[str, Any]:
        if not isinstance(entry, dict):
            raise LexiconError("entry 必须是对象")
        headword = str(entry.get("headword", "")).strip()
        key = normalize_headword(headword)
        if not key:
            raise LexiconError("entry.headword 不能为空")
        if update_mode not in {"merge", "replace_fields"}:
            raise LexiconError("update_mode 必须是 merge 或 replace_fields")

        with self._locked():
            data = self._load_unlocked()
            existing_key = self._find_existing_key(data, key)
            created = existing_key is None
            actual_key = existing_key or key
            stamp = now_iso()
            if created:
                current: dict[str, Any] = {
                    "headword": headword,
                    "aliases": [],
                    "pronunciations": {},
                    "parts_of_speech": [],
                    "collocations": [],
                    "cet_notes": [],
                    "exam_sources": [],
                    "created_at": stamp,
                    "updated_at": stamp,
                }
            else:
                current = copy.deepcopy(data["entries"][actual_key])

            current["headword"] = current.get("headword") or headword
            if update_mode == "replace_fields":
                for field in KNOWLEDGE_FIELDS:
                    if field in entry:
                        current[field] = copy.deepcopy(entry[field])
            else:
                self._merge_knowledge(current, entry)

            aliases = list(current.get("aliases", []))
            for alias in [query_form, headword]:
                if alias and normalize_headword(alias) != normalize_headword(current["headword"]):
                    aliases.append(alias.strip())
            current["aliases"] = _dedupe(aliases, lambda value: normalize_headword(str(value)))

            if save_to_current_exam:
                source = copy.deepcopy(data.get("current_exam")) or {"category": "未分类"}
                sources = list(current.get("exam_sources", []))
                sources.append(source)
                current["exam_sources"] = _dedupe(sources, _json_key)

            current["updated_at"] = stamp
            data["entries"][actual_key] = current
            self._commit_unlocked(data)
            return {
                "saved": True,
                "created": created,
                "deduplicated": not created,
                "headword": current["headword"],
                "entry_key": actual_key,
                "exam_sources": current["exam_sources"],
                **self._status(data),
            }

    def _find_existing_key(self, data: dict[str, Any], normalized: str) -> str | None:
        if normalized in data["entries"]:
            return normalized
        for key, entry in data["entries"].items():
            if normalize_headword(str(entry.get("headword", ""))) == normalized:
                return key
            if any(normalize_headword(str(alias)) == normalized for alias in entry.get("aliases", [])):
                return key
        return None

    def _merge_knowledge(self, current: dict[str, Any], incoming: dict[str, Any]) -> None:
        pronunciations = dict(current.get("pronunciations", {}))
        pronunciations.update({k: v for k, v in incoming.get("pronunciations", {}).items() if v})
        current["pronunciations"] = pronunciations

        current_pos = list(current.get("parts_of_speech", []))
        for new_group in incoming.get("parts_of_speech", []):
            pos_name = _text_key(new_group.get("pos", ""))
            matching = next((group for group in current_pos if _text_key(group.get("pos", "")) == pos_name), None)
            if matching is None:
                current_pos.append(copy.deepcopy(new_group))
                continue
            senses = list(matching.get("senses", []))
            for new_sense in new_group.get("senses", []):
                sense_key = (_text_key(new_sense.get("zh", "")), _text_key(new_sense.get("en", "")))
                old_sense = next(
                    (
                        sense
                        for sense in senses
                        if (_text_key(sense.get("zh", "")), _text_key(sense.get("en", ""))) == sense_key
                    ),
                    None,
                )
                if old_sense is None:
                    senses.append(copy.deepcopy(new_sense))
                else:
                    examples = list(old_sense.get("examples", [])) + copy.deepcopy(new_sense.get("examples", []))
                    old_sense["examples"] = _dedupe(examples, _json_key)
            matching["senses"] = senses
        current["parts_of_speech"] = current_pos

        collocations = list(current.get("collocations", [])) + copy.deepcopy(incoming.get("collocations", []))
        current["collocations"] = _dedupe(
            collocations,
            lambda item: _text_key(item.get("en", "")) if isinstance(item, dict) else _text_key(item),
        )
        notes = list(current.get("cet_notes", [])) + copy.deepcopy(incoming.get("cet_notes", []))
        current["cet_notes"] = _dedupe(notes, _text_key)

    def read_lexicon(
        self,
        headword: str | None = None,
        exam: dict[str, Any] | None = None,
        include_markdown: bool = False,
    ) -> dict[str, Any]:
        with self._locked():
            data = self._load_unlocked()
            if not self.markdown_path.exists():
                self._atomic_text(self.markdown_path, render_markdown(data))
            entries = data["entries"]
            if headword:
                found_key = self._find_existing_key(data, normalize_headword(headword))
                entries = {found_key: entries[found_key]} if found_key else {}
            elif exam:
                normalized_exam = self._validate_exam(exam)
                entries = {
                    key: entry
                    for key, entry in entries.items()
                    if normalized_exam in entry.get("exam_sources", [])
                }
            result: dict[str, Any] = {**self._status(data), "entries": copy.deepcopy(entries)}
            if include_markdown:
                result["markdown"] = self.markdown_path.read_text(encoding="utf-8")
            return result


def _exam_sort_key(exam: dict[str, Any]) -> tuple[Any, ...]:
    if exam.get("category") == "未分类":
        return (9, 9999, 99, 99)
    return (0 if exam.get("level") == "CET-4" else 1, exam.get("year", 0), exam.get("month", 0), exam.get("set_number", 0))


def _exam_label(exam: dict[str, Any]) -> str:
    if exam.get("category") == "未分类":
        return "未分类"
    chinese_level = "四级" if exam["level"] == "CET-4" else "六级"
    return f"{exam['year']}年{exam['month']}月{chinese_level}第{exam['set_number']}套"


def _anchor(value: str) -> str:
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value.casefold()).strip("-")
    return slug or "item"


def render_markdown(data: dict[str, Any]) -> str:
    entries = data.get("entries", {})
    exam_index: dict[str, dict[str, Any]] = {}
    for key, entry in entries.items():
        for exam in entry.get("exam_sources", []) or [{"category": "未分类"}]:
            marker = _json_key(exam)
            bucket = exam_index.setdefault(marker, {"exam": exam, "keys": []})
            bucket["keys"].append(key)

    lines = [
        "# CET Lexicon",
        "",
        "> JSON 为唯一数据源；本文件由 CET MWW 自动生成，请不要直接编辑。",
        f"> 最近更新：{data.get('updated_at', '')}",
        "",
        "## 目录",
        "",
        "- [按试卷索引](#按试卷索引)",
    ]
    for bucket in sorted(exam_index.values(), key=lambda item: _exam_sort_key(item["exam"])):
        label = _exam_label(bucket["exam"])
        lines.append(f"  - [{label}](#exam-{_anchor(label)})")
    lines.extend(["- [主词条](#主词条)", "", "## 按试卷索引", ""])

    if not exam_index:
        lines.extend(["_暂无词条。_", ""])
    for bucket in sorted(exam_index.values(), key=lambda item: _exam_sort_key(item["exam"])):
        label = _exam_label(bucket["exam"])
        lines.extend([f'<a id="exam-{_anchor(label)}"></a>', f"### {label}", ""])
        words = sorted((entries[key]["headword"] for key in bucket["keys"]), key=str.casefold)
        lines.append(" · ".join(f"[{word}](#word-{_anchor(word)})" for word in words))
        lines.append("")

    lines.extend(["## 主词条", ""])
    if not entries:
        lines.extend(["_暂无词条。_", ""])
    for _, entry in sorted(entries.items(), key=lambda item: item[1].get("headword", "").casefold()):
        headword = entry.get("headword", "")
        lines.extend([f'<a id="word-{_anchor(headword)}"></a>', f"### {headword}", ""])
        pronunciations = entry.get("pronunciations", {})
        pronunciation_bits = []
        if pronunciations.get("uk"):
            pronunciation_bits.append(f"BrE {pronunciations['uk']}")
        if pronunciations.get("us"):
            pronunciation_bits.append(f"NAmE {pronunciations['us']}")
        if pronunciation_bits:
            lines.extend([" · ".join(pronunciation_bits), ""])

        for group in entry.get("parts_of_speech", []):
            lines.extend([f"**{group.get('pos', '').strip()}**", ""])
            for index, sense in enumerate(group.get("senses", []), start=1):
                definition = sense.get("zh", "").strip()
                if sense.get("en"):
                    definition += f" — {sense['en'].strip()}"
                lines.append(f"{index}. {definition}")
                for example in sense.get("examples", []):
                    lines.append(f"   - {example.get('en', '').strip()}")
                    if example.get("zh"):
                        lines.append(f"     - {example['zh'].strip()}")
            lines.append("")

        collocations = entry.get("collocations", [])
        if collocations:
            lines.extend(["**常用搭配**", ""])
            for item in collocations:
                if isinstance(item, dict):
                    suffix = f" — {item.get('zh', '').strip()}" if item.get("zh") else ""
                    lines.append(f"- {item.get('en', '').strip()}{suffix}")
                else:
                    lines.append(f"- {item}")
            lines.append("")

        notes = entry.get("cet_notes", [])
        if notes:
            lines.extend(["**四六级提示**", ""])
            lines.extend(f"- {note}" for note in notes)
            lines.append("")

        source_labels = [_exam_label(source) for source in entry.get("exam_sources", [])]
        lines.extend([f"_试卷来源：{'；'.join(source_labels) if source_labels else '未分类'}_", "", "---", ""])
    return "\n".join(lines).rstrip() + "\n"
