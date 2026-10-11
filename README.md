# tokenscope

**Reads your local Claude Code and Codex CLI transcripts and tells you where the
tokens went — per tool, per re-read file, per cache miss — for people whose agent
bill is bigger than they expected.**

## The problem

Your agent session cost $14 and you have no idea why. The provider dashboard
gives you one number per day, and the transcript is a 9 MB wall of JSONL. The
expensive parts are invisible: a `cat` of a log file that then rides along in
every later turn's context, the same file read four times, a coffee break that
blew the cache TTL and made the next turn re-pay full cache-write price.
tokenscope reads the transcript you already have on disk and prints that list.

## Real terminal output

```console
$ tokenscope analyze ~/.claude/projects/C--Users-Raj-Desktop-Poly --top 3
=== Cost & Waste Report ===
Sessions: 3
Total tokens: 106,075,297
Total cost: $13.8073
Cache hit ratio: 98.8%

-- Per-tool spend --
TOOL  CALLS  OUTPUT     CARRIED     COST
Bash    360  78,634  14,183,082  $1.4969
Read     16  14,000   1,134,148  $0.1274
Edit     85   3,485     433,397  $0.0468

-- Repeated re-reads (top 3) --
PATH                    READS  WASTED READS  WASTED TOKENS
src/providers/index.ts      3             2          1,976
src/feeds/index.ts          2             1            454
echo                        3             2            387

-- Oversized outputs (top 3) --
  (none above 5,000 tokens -- raise with --threshold)

-- Cache misses (top 3) --
TURN   TOKENS  GAP (s)  EXTRA COST
  67  159,848   1832.0     $0.1439
  59  147,588    253.9     $0.1328
  45  108,067    135.1     $0.0973

-- Suggestions (top 3) --
[cache_miss] Batch work to stay within cache TTL (~159,848 tok, ~$0.1439)
[cache_miss] Batch work to stay within cache TTL (~147,588 tok, ~$0.1328)
[cache_miss] Batch work to stay within cache TTL (~108,067 tok, ~$0.0973)
```

Three real sessions, 106M tokens carried through context, and 360 Bash calls
accounting for most of the bill. The dollar figures come from the bundled
pricing table, which did not recognize these model ids and fell back to its
generic estimate — see [Limitations](#limitations).

## Install

Not on PyPI. Clone the repo and install from the checkout:

```bash
pip install -e .
```

Requires Python 3.11+ and has no runtime dependencies.

## Usage

```bash
tokenscope sessions                              # list discovered transcripts with date, size, cost
tokenscope analyze                               # analyze every session in the default locations
tokenscope analyze path/to/session.jsonl --top 3 # one transcript, 3 rows per section
tokenscope analyze examples/ --format markdown   # markdown report to paste into an issue
```

With no path, both commands search `~/.claude/projects` and `~/.codex/sessions`.

`analyze` flags: `--format {text,json,markdown}`; `--top N` to limit rows per
section; `--since YYYY-MM-DD` to skip older sessions; `--threshold N` for the
oversized-output cutoff in tokens (default 5,000); `--prices file.json` to
override the pricing table; `--min-savings DOLLARS` to hide small suggestions;
`--group-by {session,project,day}` to rank sessions and bucket findings.
`sessions` takes `--format {text,json}`, `--since` and `--prices`.

## How it works

| Section | What it measures |
| --- | --- |
| Per-tool spend | Each tool result billed once at the turn's input price, then re-billed at cache-read price for every later turn that carries it ("carried tokens"). |
| Repeated re-reads | A `Read`, or a plain `cat`/`head`/`tail`/`sed` in Bash, of a file already read in the session with no `Edit`/`Write` in between. |
| Oversized outputs | Any single tool result above `--threshold` tokens, with the command or path that produced it. |
| Cache misses | Turns with large `cache_creation_tokens` after an idle gap past the ~5 minute TTL, or after a model switch, priced as cache-write minus cache-read. |
| Suggestions | One line per finding worth money: paginate that Read, note that file in your instructions, batch work inside the TTL. |

Empty sections state the criterion and threshold they used, so `(none)` never
looks like a broken detector.

Everything runs locally: transcripts are read from disk and never uploaded.
No network calls, no telemetry.

## Limitations

Token counts are a `chars/4` heuristic, not Anthropic's tokenizer — roughly
±10% on English prose, worse on dense JSON or minified code. Costs come from a
small bundled pricing table covering a few Claude and GPT model ids; any model
it does not recognize is priced with a generic fallback, so dollars for newer
models are indicative, not a bill. Pass `--prices` with your own rates when the
number has to be right, and trust your provider's billing over this tool.

Carried-token cost assumes nothing is ever evicted from the cached prefix, which
makes it an upper bound rather than an exact figure. The Bash parser understands
only simple read commands and will occasionally attribute a read to the wrong
operand (the `echo` row above is one). Cache-TTL detection assumes 5 minutes.
Only Claude Code and Codex CLI JSONL transcripts are parsed — there is no live
monitoring, no server, and no way to analyze a session whose transcript you do
not have.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

MIT licensed. See [LICENSE](LICENSE).
