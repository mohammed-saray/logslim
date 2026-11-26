# logslim ✂️

**Stop pasting 2,000-line logs into Claude, ChatGPT or Gemini. logslim keeps the error and the context around it, folds the noise, and typically cuts the tokens by 80–95%.**

[![CI](https://github.com/mohammed-saray/logslim/actions/workflows/ci.yml/badge.svg)](https://github.com/mohammed-saray/logslim/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

```text
$ logslim app.log
logslim: 1,648 → 176 tokens (89% smaller, heuristic (≈ chars/4))
INFO GET /api/health 200 3ms   [×40]
Downloading weights 100% |#########################   [progress: 50 earlier updates hidden]
DEBUG cache miss key=user:1000 took 0ms
    … 23 similar lines …
DEBUG cache miss key=user:1024 took 48ms
ERROR request <uuid> failed
Traceback (most recent call last):
  File "/app/main.py", line 10, in <module>
    run()
  File "/usr/lib/python3.12/site-packages/click/core.py", line 1157, in __call__
    return self.main(*args, **kwargs)
    … 3 library frames hidden …
  File "/app/service.py", line 42, in run
    db.connect()
  File "/usr/lib/python3.12/site-packages/psycopg/connection.py", line 99, in connect
    raise e
psycopg.OperationalError: connection refused
```

## The problem

Debugging with an AI usually means pasting output: test runs, build logs, server
logs, stack traces. Most of it is noise. Timestamps on every line, the same
health check 500 times, progress bars, 40 frames of framework internals. You
pay for all of it in tokens, you hit the message or usage limit sooner, and the
real error gets buried. Agents like Claude Code and Codex read the same
bloated command output too.

## Install

```bash
pipx install git+https://github.com/mohammed-saray/logslim
```

## Usage

```bash
npm test 2>&1 | logslim | pbcopy          # macOS
pytest 2>&1 | logslim | clip              # Windows
docker logs api | logslim -t 2000         # hard budget of ~2000 tokens
logslim build.log server.log -p           # prepend "Find the root cause and suggest a fix."
logslim crash.log -p "Why does this only fail on CI?"
```

| Option | Effect |
|---|---|
| `-t, --max-tokens N` | Fit a budget: keep the head, the tail and ±`C` lines around every error/warning; drop the middle with markers. If it still doesn't fit, prefer the **last** errors. |
| `-C, --context N` | Lines kept around each error in budget mode (default 3). |
| `--frames N` | Library frames kept at each end of a stack trace (default 2). |
| `-p, --prompt [TEXT]` | Wrap the output in a code block with a question in front. |
| `--keep-timestamps`, `--keep-ansi`, `--no-normalize`, `--no-similar`, `--no-stacks` | Turn individual steps off. |
| `-q` | Don't print the before/after stats (they go to stderr, so pipes stay clean). |

### In agent instructions

Add to `CLAUDE.md` / `AGENTS.md`:

```markdown
When running tests or builds, pipe output through `logslim -t 3000` to save context.
```

### As a library

```python
from logslim import slim, Options
short = slim(open("ci.log").read(), Options(max_tokens=1500))
```

## What it does (in order)

1. Strips ANSI colors and leading timestamps (ISO-8601, `[HH:MM:SS]`, syslog).
2. Normalizes volatile values: UUIDs → `<uuid>`, hex addresses → `<addr>`, long hashes → `<hash>`, inline timestamps → `<time>`. Lines that differ only by these become identical.
3. Keeps only the final state of `\r`-redrawn lines and folds progress-bar runs.
4. Folds **library frames** in Python, Node.js, Java/Kotlin, Go and Rust stack traces (site-packages, node_modules, `node:internal`, JDK…). Your own frames and the first/last frames are kept.
5. Collapses exact repeats (`[×40]`) and runs of lines that differ only by numbers (`… 23 similar lines …`).
6. Optional token budget, keeping errors first.

Lines with `error`, `fail`, `exception`, `fatal`, `panic`, `timeout`, `denied`, `warning`… are never part of a progress fold.

## Limitations

- It's lossy on purpose. If the AI needs the exact raw value of something that got folded, paste that part raw.
- Token counts are estimates (install `tiktoken` for closer numbers).

## Roadmap

- [ ] `--json` log support (pick fields, drop noisy keys)
- [ ] Shell wrapper `logslim run -- npm test` that keeps the exit code
- [ ] More stack-trace dialects (.NET, Ruby, PHP)

## Related tools in this suite

Small, dependency-free tools for people fighting AI usage limits:

| Tool | What it does |
|---|---|
| [burnrate](https://github.com/mohammed-saray/burnrate) | Forecast Claude Code / Codex limits from local logs |
| [context-diet](https://github.com/mohammed-saray/context-diet) | Find the CLAUDE.md / AGENTS.md / GEMINI.md bloat you pay for on every message |
| [ai-handoff](https://github.com/mohammed-saray/ai-handoff) | Hit a limit? Move the task to another AI with a handoff file |
| [ai-error-decoder](https://github.com/mohammed-saray/ai-error-decoder) | Explain 429 / 529 / quota errors from Anthropic, OpenAI and Gemini |
| [ratelimit-retry](https://github.com/mohammed-saray/ratelimit-retry) | Retry that respects provider rate-limit headers (JS) |
| [chat-export-md](https://github.com/mohammed-saray/chat-export-md) | ChatGPT / Claude / Gemini exports → Markdown |
| [mcp-token-audit](https://github.com/mohammed-saray/mcp-token-audit) | Measure how many tokens each MCP server's tools cost |
| **logslim** | Shrink logs and stack traces before pasting them into a chat |
| [chunkwise](https://github.com/mohammed-saray/chunkwise) | Split big files into token-budgeted chunks with continuation prompts |
| [ai-reset-clock](https://github.com/mohammed-saray/ai-reset-clock) | When does my quota reset? A countdown in your timezone |

## Contributing

Have a log format it handles badly? Open an issue with a **redacted** sample. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
