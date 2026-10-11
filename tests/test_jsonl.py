"""Tests for JSONL streaming reader."""

import json
import tempfile
from pathlib import Path

from tokenscope.jsonl import JSONLReader


def test_valid_file() -> None:
    """Test reading a valid JSONL file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"id": 1, "name": "a"}\n')
        f.write('{"id": 2, "name": "b"}\n')
        f.write('{"id": 3, "name": "c"}\n')
        path = f.name

    try:
        reader = JSONLReader(path)
        results = list(reader.read())
        assert len(results) == 3
        assert results[0] == {"id": 1, "name": "a"}
        assert results[1] == {"id": 2, "name": "b"}
        assert results[2] == {"id": 3, "name": "c"}
        assert len(reader.warnings) == 0
    finally:
        Path(path).unlink()


def test_blank_lines() -> None:
    """Test that blank lines are skipped."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"id": 1}\n')
        f.write('\n')
        f.write('   \n')
        f.write('{"id": 2}\n')
        f.write('\n')
        path = f.name

    try:
        reader = JSONLReader(path)
        results = list(reader.read())
        assert len(results) == 2
        assert results[0] == {"id": 1}
        assert results[1] == {"id": 2}
        assert len(reader.warnings) == 0
    finally:
        Path(path).unlink()


def test_truncated_final_line() -> None:
    """Test handling of truncated final line."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"id": 1}\n')
        f.write('{"id": 2, "name": "incomplete')
        path = f.name

    try:
        reader = JSONLReader(path)
        results = list(reader.read())
        assert len(results) == 1
        assert results[0] == {"id": 1}
        assert len(reader.warnings) == 1
        assert reader.warnings[0]["line_number"] == 2
        assert "incomplete" in reader.warnings[0]["content_preview"]
    finally:
        Path(path).unlink()


def test_invalid_json_mid_file() -> None:
    """Test recording invalid JSON mid-file in warnings."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"id": 1}\n')
        f.write('not valid json\n')
        f.write('{"id": 2}\n')
        f.write('{"broken": [1, 2, 3\n')
        f.write('{"id": 3}\n')
        path = f.name

    try:
        reader = JSONLReader(path)
        results = list(reader.read())
        assert len(results) == 3
        assert results[0] == {"id": 1}
        assert results[1] == {"id": 2}
        assert results[2] == {"id": 3}
        assert len(reader.warnings) == 2
        assert reader.warnings[0]["line_number"] == 2
        assert reader.warnings[1]["line_number"] == 4
    finally:
        Path(path).unlink()


def test_large_file_streaming() -> None:
    """Test streaming a large file without loading fully into memory."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for i in range(50000):
            f.write(json.dumps({"id": i, "value": f"line_{i}"}) + "\n")
        path = f.name

    try:
        reader = JSONLReader(path)
        count = 0
        for obj in reader.read():
            count += 1
            assert isinstance(obj, dict)
            assert "id" in obj
            if count == 1:
                assert obj["id"] == 0
            if count == 50000:
                assert obj["id"] == 49999
        assert count == 50000
        assert len(reader.warnings) == 0
    finally:
        Path(path).unlink()
