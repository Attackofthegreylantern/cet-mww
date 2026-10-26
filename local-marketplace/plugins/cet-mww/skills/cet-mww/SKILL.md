---
name: cet-mww
description: Explain English words and phrases for a Chinese CET-4/CET-6 learner, automatically maintain the local CET lexicon, switch active exam papers, or read and edit saved vocabulary. Use for direct word/phrase lookups, contextual vocabulary questions, and requests about the user's CET wordbook. Do not activate for ordinary translation or writing tasks that do not ask about a particular word or phrase.
---

# CET My Word World

Use the `cet-mww-storage` MCP tools for persistent state. The skill controls the language workflow; the MCP server writes `vocabulary.json` and automatically generates the Word notebook `CET-Lexicon.docx` and a Markdown copy. Word is the default reading format.

## Recognize requests

Treat a bare English word or short phrase, “X 是什么意思”, “X 在这里怎么理解”, or a question about one highlighted word in a sentence as an explicit lookup. If a likely typo such as `alienatinge` has one clear correction, explain the correction and use the canonical headword (`alienating`) for storage while passing the typed form as `query_form`. If more than one correction is plausible, ask briefly before saving.

Do not treat a general translation, essay revision, or casual mention as a lookup. If the user says “不要保存”, explain the word but do not call the save tool.

## Lookup workflow

1. If the user names a paper, call `switch_exam` first. For a lookup that should be saved, call `read_lexicon` with the canonical headword to load existing knowledge and the server's current paper. On a new conversation, rely on that persisted paper rather than guessing from chat history. If no paper is active, saving automatically uses “未分类”. A no-save lookup needs no storage calls.
2. Interpret an included sentence before selecting senses. State the in-context meaning first; add only common secondary CET-relevant senses. When an IPA or usage is uncertain, verify it using an available reliable dictionary/reference or disclose uncertainty; do not fabricate pronunciations or meanings.
3. Answer in this compact, consistent order:
   - headword, part of speech, and BrE or NAmE IPA;
   - numbered Chinese senses, with a short English gloss only when useful;
   - 2–3 common collocations;
   - 1–2 natural English examples paired with Chinese translations;
   - one brief CET usage note only when it adds value.
4. Create a canonical structured entry matching the save tool schema. For a new entry, include `pronunciations`, `parts_of_speech` with numbered senses and paired `examples`, and common `collocations`. Put IPA, Chinese meanings and examples in their actual structured fields, not only in the chat answer or `cet_notes`, so Word can display them. Use original wording; do not copy dictionary prose. Call `save_or_update_entry` after composing the answer.
5. Say “已保存，Word 单词本已更新” only when the tool returns `saved: true`. On failure, report the actual tool message: it distinguishes an unchanged source from JSON being saved with a reading-file refresh failure. Never claim Word was updated unless the tool confirms success. If Word has the notebook open and the tool requests closing it, ask the user to close it before retrying.

Keep content accurate and concise. Do not invent a rare sense merely to fill the format. Use standard IPA delimiters. For phrases, store the complete phrase as the headword. For inflected forms, prefer the dictionary form only when that is the natural learning entry; keep the queried form as `query_form`.

## Deduplication and updates

- Repeated lookups use the same canonical `headword`. The server merges missing knowledge and adds a new paper source without creating another main entry.
- Reuse the existing wording for the same sense and attach new examples to it. A paraphrased English gloss is not a new sense. Do not submit duplicate Chinese meanings as separate senses. If the user explicitly requests consolidating existing duplicates, read the entry, combine their examples, and replace the complete corrected `parts_of_speech` field.
- A clear misspelling must never become a second main entry when the intended canonical word is known.
- For a user-requested correction such as “修改第二个释义”, first call `read_lexicon` for that headword. Send the complete corrected top-level field and use `update_mode: replace_fields`; do not construct a partial array that would erase neighboring senses.
- Update JSON through the tool and let the server regenerate Word and Markdown. Do not edit either generated reading file directly. Tell a user who wants to edit in Word that manual changes will not sync back to JSON and may be replaced on the next refresh; use chat to update saved vocabulary instead.

## Reading the wordbook

- “打开我的单词本”: call `read_lexicon`, then present `word_path` as a clickable local Word file link. If a file-opening action is available, use it to open that path. Do not dump the whole wordbook into chat. Use `include_markdown: true` only when a text preview is requested. If the user explicitly asks for Markdown, provide `markdown_path`.
- “查看某套试卷”: pass that exact exam filter to `read_lexicon`.
- Exam/headword filters limit returned entries, not the generated Word file. Show the requested subset in chat; do not call the full notebook a filtered Word export.
- “查看某词”: pass `headword`.

Do not claim the file was opened in a separate app unless the host actually provides and successfully runs a file-opening action.

## Word reading design

The exporter owns the established style: full-width title and front matter, two-column body with a thin muted-blue centre rule, Georgia headwords at 14 pt, Calibri and Songti SC body at 10 pt, IPA and English glosses at 9.5 pt, paired English/Chinese examples, and sources at 9 pt. The front matter comes first: clickable contents, CET-4/CET-6 → year → month → paper directory, then an alphabetical word index. The full entries start on a new page after those indexes. Links navigate to one canonical entry per word. Preserve this design on subsequent saves. Layout changes belong in the exporter, not in one-off edits to generated Word files.

Black squares beside paragraphs are Word's non-printing paragraph-format marks, not bullets or missing text. Guide the user to turn off “显示段落标记” (⌘8 on macOS) if unwanted; keep pagination controls that hold a headword with its definition and an example with its translation.

When the user asks to review a design, provide a separate preview generated from existing JSON. If they say they will review it themselves, perform content and file-integrity checks only and leave visual approval to them. Do not silently replace a document that Word has open.
