"""Agent transcript cost & waste analyzer

CLI that parses local Claude Code / Codex session JSONL transcripts and reports token
spend per tool, repeated file re-reads, oversized tool outputs and cache misses, with
concrete suggestions. For heavy agent users who don't know where their tokens go.
"""

__version__ = "0.1.0"
