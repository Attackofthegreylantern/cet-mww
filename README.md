# CET My Word World (MWW) V1.0

一个仅在本机运行的 ChatGPT Desktop / Codex 个人插件：Skill 负责识别查词意图并生成统一词条，本地 stdio MCP 负责安全持久化。

## 能力边界

- 支持本地运行的 ChatGPT Desktop Work/Codex 线程。
- 不会让纯云端普通聊天自动获得本机文件权限；需要先安装并在本地线程中启用插件。
- 不使用公网服务、账号、数据库或独立网页。
- `vocabulary.json` 是唯一数据源；`CET-Lexicon.md` 每次写入后自动生成。

## 安装

本仓库包含可导入的本地 marketplace：`local-marketplace/`。

1. 在本项目目录运行：

   ```bash
   codex plugin marketplace add ./local-marketplace
   ```

2. 完全退出并重新打开 ChatGPT Desktop。
3. 打开 Plugins Directory，选择 `cet-mww-local` 来源，安装 **CET My Word World**。
4. 在本地 Work/Codex 新对话中用 `@` 选择插件，或直接输入查词请求让 Skill 自动匹配。
5. macOS 首次访问桌面时如出现“文件与文件夹”权限提示，请允许。

可用下面的命令确认 marketplace 已被发现：

```bash
codex plugin marketplace list
```

## 使用

```text
我正在做2024年12月四级第一套。
bleak
alienating 是什么意思？
这个词不要保存：substantial
切换到2025年6月六级第二套。
打开我的单词本。
修改 substantial 的第二个释义。
```

默认数据位置：

```text
~/Desktop/CET-Lexicon/vocabulary.json
~/Desktop/CET-Lexicon/CET-Lexicon.md
```

测试或需要自定义位置时，可在启动 MCP server 前设置 `CET_MWW_DATA_DIR`。

## 测试

```bash
python3 -m unittest discover -s local-marketplace/plugins/cet-mww/tests -v
```

端到端测试通过真实 stdio JSON-RPC 进程执行：切换试卷、保存 `bleak` 和 `alienating`、以误拼 `alienatinge` 查询并按规范化词头去重、切换试卷、读取 Markdown、重启 server 后验证 JSON 中的词条和当前试卷仍存在。
