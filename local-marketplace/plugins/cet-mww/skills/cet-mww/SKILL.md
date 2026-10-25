---
name: cet-mww
description: Explain English words and phrases for a Chinese CET-4/CET-6 learner, automatically maintain the local CET lexicon, switch active exam papers, or read and edit saved vocabulary. Use for direct word/phrase lookups, contextual vocabulary questions, and requests about the user's CET wordbook. Do not activate for ordinary translation or writing tasks that do not ask about a particular word or phrase.
---

# CET My Word World

Use the `cet-mww-storage` MCP tools for persistent state. The skill controls the language workflow; the MCP server is the only writer for `vocabulary.json` and the generated Markdown.

## Recognize requests

Treat a bare English word or short phrase, “X 是什么意思”, “X 在这里怎么理解”, or a question about one highlighted word in a sentence as an explicit lookup. If a likely typo such as `alienatinge` has one clear correction, explain the correction and use the canonical headword (`alienating`) for storage while passing the typed form as `query_form`. If more than one correction is plausible, ask briefly before saving.

Do not treat a general translation, essay revision, or casual mention as a lookup. If the user says “不要保存”, explain the word but do not call the save tool.

## Lookup workflow

1. If the user names a paper, call `switch_exam` first. Preserve the current paper across later lookups and conversations; do not ask for it again. If no paper is active, saving automatically uses “未分类”.
2. Interpret an included sentence before selecting senses. Prefer the meaning used in that sentence; add only common secondary CET-relevant senses.
3. Answer in this compact, consistent order:
   - headword, part of speech, and BrE or NAmE IPA;
   - numbered Chinese senses, with a short English gloss only when useful;
   - 2–3 common collocations;
   - 1–2 natural English examples paired with Chinese translations;
   - one brief CET usage note only when it adds value.
4. Create a canonical structured entry matching the save tool schema. Use original wording; do not copy dictionary prose. Call `save_or_update_entry` after composing the answer.
5. Say “已保存” only when the tool returns `saved: true`. If it fails, say that the explanation succeeded but saving failed, include the returned reason, and do not imply persistence.

Keep content accurate and concise. Do not invent a rare sense merely to fill the format. Use standard IPA delimiters. For phrases, store the complete phrase as the headword. For inflected forms, prefer the dictionary form only when that is the natural learning entry; keep the queried form as `query_form`.

## Deduplication and updates

- Repeated lookups use the same canonical `headword`. The server merges missing knowledge and adds a new paper source without creating another main entry.
- A clear misspelling must never become a second main entry when the intended canonical word is known.
- For a user-requested correction such as “修改第二个释义”, first call `read_lexicon` for that headword. Send the complete corrected top-level field and use `update_mode: replace_fields`; do not construct a partial array that would erase neighboring senses.
- Never edit `CET-Lexicon.md` directly. Update JSON through the tool and let the server regenerate Markdown.

## Reading the wordbook

- “打开我的单词本”: call `read_lexicon` with `include_markdown: true`, then present its `markdown_path` as the local file location and show a concise preview or the requested content.
- “查看某套试卷”: pass that exact exam filter to `read_lexicon`.
- “查看某词”: pass `headword`.

Do not claim the file was opened in a separate app unless the host actually provides and successfully runs a file-opening action.
