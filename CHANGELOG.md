# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-29

### Added
- CLI with `analyze`, `sessions`, and `summary` commands for parsing Claude Code/Codex session transcripts
- Token spend analysis by tool type and per-tool usage reporting
- Detection of repeated file re-reads with concrete suggestions for optimization
- Identification of oversized tool outputs impacting token usage
- Cache miss detection and analysis
- Support for JSONL transcript format
- JSON and Markdown output formats for analysis results
- Cross-session aggregation and trend summary capabilities
- Python 3.10+ support with GitHub Actions CI/CD
- Comprehensive test coverage with pytest
- Code quality checks with ruff linter

### Changed
- Initial release

[0.1.0]: https://github.com/rajmaurya0904/tokenscope/releases/tag/0.1.0
