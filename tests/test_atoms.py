from __future__ import annotations

import struct
from pathlib import Path

from mp4defrag.atoms import scan_top_level_atoms


def _box(atom_type: str, payload: bytes = b"") -> bytes:
    size = 8 + len(payload)
    return struct.pack(">I4s", size, atom_type.encode("ascii")) + payload


def test_scan_counts_single_mdat(tmp_path: Path) -> None:
    data = _box("ftyp", b"isom") + _box("moov", b"\x00" * 16) + _box("mdat", b"\x00" * 1024)
    f = tmp_path / "sano.mp4"
    f.write_bytes(data)

    result = scan_top_level_atoms(f)

    assert [a.type for a in result.atoms] == ["ftyp", "moov", "mdat"]
    assert result.mdat_count == 1
    assert not result.is_fragmented(threshold=8)


def test_scan_detects_many_mdat_as_fragmented(tmp_path: Path) -> None:
    data = _box("ftyp", b"isom") + _box("moov", b"\x00" * 8)
    data += b"".join(_box("mdat", b"\x00" * 100) for _ in range(20))
    f = tmp_path / "fragmentado.mp4"
    f.write_bytes(data)

    result = scan_top_level_atoms(f)

    assert result.mdat_count == 20
    assert result.is_fragmented(threshold=8)
    assert not result.is_fragmented(threshold=20)


def test_scan_handles_extended_64bit_size(tmp_path: Path) -> None:
    payload = b"\x00" * 32
    total_size = 16 + len(payload)
    header = struct.pack(">I4sQ", 1, b"mdat", total_size)
    f = tmp_path / "extendido.mp4"
    f.write_bytes(header + payload)

    result = scan_top_level_atoms(f)

    assert result.mdat_count == 1
    assert result.atoms[0].size == total_size
    assert result.atoms[0].header_size == 16
