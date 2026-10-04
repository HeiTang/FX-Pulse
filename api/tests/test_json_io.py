"""Regression coverage for failure during durable JSON writes."""

from unittest.mock import patch

import pytest

from fx_pulse.json_io import atomic_write_json


def test_fsync_failure_preserves_original_and_cleans_temporary_file(tmp_path):
    path = tmp_path / "state.json"
    atomic_write_json(path, {"value": "original"})
    before = path.read_bytes()
    with patch("fx_pulse.json_io.os.fsync", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            atomic_write_json(path, {"value": "replacement"})
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]
