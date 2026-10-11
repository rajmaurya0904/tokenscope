# Agent Transcript Cost & Waste Analyzer

Analyze your Claude Code and Codex session transcripts to find where your AI tokens—and money—go. This tool parses local session JSONL files and reports token spend per tool, repeated file re-reads, oversized tool outputs, and cache misses, with concrete optimization suggestions.

For teams and individual power users of Claude Code who want to audit their token usage and reduce waste.

## Features

- **Per-tool spend breakdown**: See which tools consume the most tokens, including how results are re-billed as cached context in later turns.
- **Repeated file re-reads**: Flag files read multiple times in a session with no edit in between (pure waste).
- **Oversized outputs**: Identify tool calls returning results above a configurable token threshold (e.g., unfiltered `cat` of a log file).
- **Cache hit ratio & misses**: Track cache efficiency and pinpoint turns that likely paid full cache-write pricing due to idle gaps or model switches.
- **Cost-aware suggestions**: Get actionable recommendations ranked by estimated token and dollar savings.
- **Cross-session aggregation**: Optional per-project or per-day rollup to spot trends across many sessions.

## Install

```bash
pip install -e ".[dev]"
```

Requires Python 3.11+.

## Quick Start

Analyze your local Claude Code and Codex transcripts:

```bash
tokenscope analyze
```

By default, this discovers and processes all session files in the standard locations (`~/.claude/transcripts`, `~/.codex_sessions`, etc.). Use `--format text` (default), `--format json`, or `--format markdown` to customize output.

See a list of all discovered sessions:

```bash
tokenscope sessions
```

## Usage

### `tokenscope analyze` — Full cost and waste report

Parse transcript files and print a comprehensive report.

```
usage: tokenscope analyze [-h] [--format {text,json,markdown}] [--top TOP]
                    [--since SINCE] [--threshold THRESHOLD] [--prices PRICES]
                    [--min-savings MIN_SAVINGS] [--group-by {project,day}]
                    [paths ...]

positional arguments:
  paths                 Transcript files or directories (default: the standard
                        Claude Code/Codex locations)

options:
  --format {text,json,markdown}
                        Output format (default: text)
  --top TOP             Limit each section to its top N findings
                        (default: 10)
  --since SINCE         Only include sessions modified since this date
                        (YYYY-MM-DD)
  --threshold THRESHOLD
                        Token threshold for flagging oversized tool outputs
                        (default: 5000)
  --prices PRICES       Path to a JSON file of per-model pricing overrides
  --min-savings MIN_SAVINGS
                        Only show suggestions estimated to save at least this
                        many dollars (default: 0.0)
  --group-by {project,day}
                        Also rank sessions by cost and merge findings into
                        project or day buckets
```

### `tokenscope sessions` — List and summarize transcripts

Discover and list all session files with their date, size, and cost.

```
usage: tokenscope sessions [-h] [--format {text,json}] [--since SINCE]
                     [--prices PRICES]
                     [paths ...]

positional arguments:
  paths                 Transcript files or directories (default: the standard
                        Claude Code/Codex locations)

options:
  --format {text,json}  Output format (default: text)
  --since SINCE         Only include sessions modified since this date
                        (YYYY-MM-DD)
  --prices PRICES       Path to a JSON file of per-model pricing overrides
```

## Examples

Two sample transcripts are provided in `examples/` to show tool output without running on your own sessions:

- `examples/claude/sample-session.jsonl` — a Claude Code session investigating and fixing a slow login handler. Contains a re-read of the same file, an unfiltered `cat` of a log file that trips the oversized-output threshold, and a model switch mid-session that forces a cold cache write.
- `examples/codex/sample-session.jsonl` — a Codex CLI session chasing a flaky Go test. Contains a re-read of the same source file and a verbose `go test -v` run that trips the oversized-output threshold.

### Sample output (text format)

```
=== Cost & Waste Report ===
Sessions: 2
Total tokens: 22,790
Total cost: $0.1222
Cache hit ratio: 65.7%

-- Per-tool spend --
TOOL  CALLS  OUTPUT  CARRIED     COST
Bash      2  10,898   43,592  $0.0516
Read      6     866    2,612  $0.0058
Edit      2      20       40  $0.0002

-- Repeated re-reads (top 10) --
PATH                       READS  WASTED READS  WASTED TOKENS
payment_service.go             3             2            243
src/auth/login_handler.py      3             1            175

-- Oversized outputs (top 10) --
TOOL  COMMAND                                     TOKENS
Bash  cat /var/log/demo-app/access.log             5,673
Bash  bash -lc go test ./... -run TestPayment -v   5,225

-- Cache misses (top 10) --
TURN  TOKENS  GAP (s)  EXTRA COST
   4   4,200      9.0     $0.0567

-- Suggestions (top 10) --
[cache_miss] Batch work to stay within cache TTL (~4,200 tok, ~$0.0567)
[oversized_output] Add head/tail or grep filter to cat /var/log/demo-app/access.log (~4,538 tok, ~$0.0045)
[oversized_output] Add head/tail or grep filter to bash -lc go test ./... -run TestPayment -v (~4,180 tok, ~$0.0042)
[repeated_reread] Note file payment_service.go in CLAUDE.md to avoid re-reads (~243 tok, ~$0.0002)
[repeated_reread] Note file src/auth/login_handler.py in CLAUDE.md to avoid re-reads (~175 tok, ~$0.0002)
```

Try it yourself:

```bash
tokenscope analyze examples/ --format text
tokenscope analyze examples/ --format json
tokenscope analyze examples/ --format markdown
```

## How it Works

### Per-tool spend

The analyzer tracks every tool call and attributes tokens to it in two phases:

1. **Output tokens**: The result from the tool is billed once at the input price of the turn that called it.
2. **Carried tokens**: That result is re-billed at the cache-read price on every later turn in the session (because it becomes part of the cached context). Each re-billing uses the pricing of the turn that carries it.

This reveals which tools are truly expensive over the lifetime of a session. For example, a large Read result might seem cheap initially but become expensive if it's carried for 10+ turns at cache rates.

**Heuristics:**
- Token estimation uses a simple chars/4 rule (rounded up) to avoid a hard dependency on the Anthropic tokenizer.
- Cache re-billing assumes every turn after a tool result carries that result in its context. (Claude Code actually implements smarter eviction, but this provides an upper bound.)

### Repeated file re-reads

A "wasted re-read" is a Read or Bash command (e.g., `cat`) of a file that was already read in the same session, with no intervening Edit or Write in between.

The analyzer tracks reads and writes per file and flags reads that occur after a file has already been read in the session but before any edit.

**Heuristics:**
- Paths are normalized (e.g., `./foo.py` and `foo.py` are treated as the same).
- Bash commands are parsed to extract file operands from simple `cat`, `head`, `tail`, `sed`, and `nl` invocations. Commands with pipes, redirects, or complex logic are skipped.
- Edit tools include `Read`, `Write`, `Edit`, `MultiEdit`, and `NotebookEdit`.

### Oversized outputs

An oversized result is any tool output exceeding the configured token threshold (default 5,000 tokens). This often indicates an unfiltered output that could be reduced.

The analyzer extracts a human-readable command/path identifier for each tool call, making it easy to spot which `Read` or `Bash` invocation returned the large result.

**Heuristics:**
- Token estimation uses chars/4.
- A flag is set if the tool call had no `limit` or `offset` parameters, suggesting the result could be paginated or filtered.

### Cache hit ratio & cache misses

The analyzer computes the session's overall cache hit ratio as:

```
cache_read_tokens / (cache_read_tokens + cache_creation_tokens + input_tokens)
```

A **cache miss** is a turn with large `cache_creation_tokens` (default: ≥1,000) that likely paid full cache-write pricing. Misses are triggered by:

1. **Idle gap**: More than ~5 minutes (configurable) since the previous turn. The Claude API's cache TTL defaults to 5 minutes; sessions longer than this likely lose the cached prefix.
2. **Model switch**: The model changed between the previous turn and this one, invalidating the cached prefix.

For a flagged miss, the analyzer estimates the extra cost as:

```
cache_creation_tokens * (cache_write_per_million - cache_read_per_million) / 1,000,000
```

**Heuristics:**
- The cache TTL is assumed to be ~5 minutes. If you use a different TTL, adjust with the `--prices` file (see FAQ).
- The session's first turn with usage tokens is never flagged, since there is no prior prefix to have reused.

### Suggestions

The analyzer synthesizes the above findings into concrete, actionable suggestions, ranked by estimated token and dollar savings. Suggestion types include:

- `repeated_reread`: Re-read a file; consider noting it in CLAUDE.md to avoid future re-reads.
- `oversized_output`: Large tool output; consider filtering with `head`, `tail`, `grep`, or pagination.
- `cache_miss`: Large cache creation (possibly due to idle gap or model switch); consider batching work to stay within cache TTL.

## Privacy

All analysis is **fully local**. Transcript files are read from your machine and never uploaded anywhere. Prices and models are assumed from defaults or from a local overrides file you provide. No telemetry or external API calls are made (except to read files on disk).

## FAQ

### How accurate is token estimation?

The tool uses a **chars/4 heuristic** to estimate tokens from tool output text, which is quick and works well for rough cost analysis but is not exact. For precise token counts, you would need Anthropic's official tokenizer, which is not bundled to keep dependencies minimal.

The heuristic typically estimates within ±10% of the true count for English text. For billing purposes, rely on Claude's official usage tracking, not this tool.

### What transcript formats are supported?

The tool discovers and parses JSONL transcripts from:

- **Claude Code** (`~/.claude/transcripts/` on macOS/Linux; `%APPDATA%\.claude` on Windows)
- **Codex CLI** (`~/.codex_sessions/` and related locations)

Transcripts are expected to be newline-delimited JSON, with each line representing a turn or event in the session. The tool auto-detects the format and skips files it cannot parse.

### Can I override model pricing?

Yes. Use the `--prices` flag to specify a JSON file of per-model pricing overrides. Format:

```json
{
  "claude-3-5-sonnet-20241022": {
    "input_per_million": 3.0,
    "output_per_million": 15.0,
    "cache_creation_per_million": 37.5,
    "cache_read_per_million": 0.3
  }
}
```

Prices are in dollars per million tokens. Omitted models fall back to tool defaults. This is useful if:

- Prices have changed since the tool was released.
- You're on a volume discount or custom plan.
- You want to simulate pricing for different models.

### What's the cache TTL assumption?

The tool assumes a **~5-minute cache TTL** (the Claude API default). If your setup uses a different TTL, it will misidentify cache misses. To adjust, create a `--prices` override file; the cache-miss heuristic respects the per-model configuration (if provided).

### Can I filter by date, session ID, or other criteria?

Use `--since YYYY-MM-DD` to include only sessions modified on or after that date. Use `--min-savings` to show only suggestions estimated to save at least that many dollars.

For custom filtering, you can:

1. Point `tokenscope` at a subset of directories (e.g., `tokenscope analyze ./my-sessions/`).
2. Use `tokenscope sessions` to get a JSON list and pipe it through your own tools.

### How do I interpret "carried tokens"?

"Carried tokens" is the cumulative token cost of re-billing a tool result as cached context in later turns. For example, if a Read returns 1,000 tokens and the session has 5 later turns, the tool's "carried tokens" includes at least 5,000 (1,000 × 5) at cache-read rates, depending on eviction.

This helps you spot tools whose initial output is small but whose long-term cost is high (because they persist in cache).

### Can I use this with other providers or models?

The tool is built for Claude transcripts and Anthropic pricing. Other providers (OpenAI, Gemini, etc.) have different transcript formats and pricing structures; they are not currently supported. If you have access to transcripts in a different format, file an issue or contribute a parser.

### What if I have very old sessions or many sessions?

Use `--since` to filter by date, and `--top` to limit output per section. For bulk analysis, use `--group-by project` or `--group-by day` to roll up findings and spot trends.

## License

MIT — see [LICENSE](LICENSE).
