# Examples

Two anonymized sample transcripts, plus the reports `tokenscope` generates from them,
so you can see the tool's output without pointing it at your own sessions.

- `claude/sample-session.jsonl` -- a Claude Code session investigating and
  fixing a slow login handler. It contains a re-read of the same file, an
  unfiltered `cat` of a log file that trips the oversized-output threshold,
  and a model switch mid-session that forces a cold cache write.
- `codex/sample-session.jsonl` -- a Codex CLI session chasing a flaky Go test.
  It contains a re-read of the same source file and a verbose `go test -v`
  run that trips the oversized-output threshold.
- `reports/report.txt`, `reports/report.json`, `reports/report.md` -- the
  text, JSON, and Markdown reports `tokenscope analyze` produces from the two
  sessions above.

All names, paths, IPs, and log lines in the sample transcripts are made up
for this example; none of it is real user data.

## Regenerating the reports

After changing either sample transcript (or the analyzer/renderer code), 
regenerate the reports from the repo root:

```bash
tokenscope analyze examples/ --format text     > examples/reports/report.txt
tokenscope analyze examples/ --format json     > examples/reports/report.json
tokenscope analyze examples/ --format markdown > examples/reports/report.md
```

`tests/test_examples.py` runs `tokenscope analyze examples/` as a smoke test and
checks that these report files exist.
