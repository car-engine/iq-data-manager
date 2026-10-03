"""Tests for iqdm.transfer.uncached: reading past the Windows file cache (D55).

The files are under tmp_path on a local disk. The tests show that unbuffered reads
give the same bytes as ordinary reads for every size around the alignment. Whether
the reads reach past the PC's cache on the NAS is checked in the NAS field test.
"""

import hashlib
import sys
from contextlib import closing

import pytest

from iqdm.transfer.uncached import ALIGN_BYTES, aligned, read_chunks
from iqdm.transfer.verify import file_sha256

SIZES = [0, 1, 511, 512, 4095, 4096, 4097, ALIGN_BYTES - 1, ALIGN_BYTES, ALIGN_BYTES + 1]


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("uncached", [False, True])
def test_reads_every_byte(tmp_path, size, uncached):
    path = tmp_path / "f.dat"
    data = bytes((i * 7 + 3) % 256 for i in range(size))
    path.write_bytes(data)
    with closing(read_chunks(path, 4096, uncached=uncached)) as chunks:
        assert b"".join(chunks) == data


@pytest.mark.parametrize("chunk", [1, 4096, ALIGN_BYTES, 3 * ALIGN_BYTES + 5])
def test_uncached_hash_equals_the_buffered_hash(tmp_path, chunk):
    path = tmp_path / "f.dat"
    path.write_bytes(bytes(range(256)) * 1000 + b"tail")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert file_sha256(path, chunk_bytes=chunk, uncached=True) == expected
    assert file_sha256(path, chunk_bytes=chunk) == expected


def test_a_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError), closing(read_chunks(tmp_path / "gone", 4096, uncached=True)) as c:
        next(c)


def test_stopping_early_closes_the_file(tmp_path):
    path = tmp_path / "f.dat"
    path.write_bytes(bytes(3 * ALIGN_BYTES))
    with closing(read_chunks(path, ALIGN_BYTES, uncached=True)) as chunks:
        assert len(next(chunks)) == ALIGN_BYTES
    path.rename(tmp_path / "renamed.dat")  # Windows refuses to rename an open file


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, ALIGN_BYTES),
        (1, ALIGN_BYTES),
        (ALIGN_BYTES, ALIGN_BYTES),
        (ALIGN_BYTES + 1, 2 * ALIGN_BYTES),
    ],
)
def test_aligned_rounds_up_to_whole_units(n, expected):
    assert aligned(n) == expected


@pytest.mark.skipif(sys.platform != "win32", reason="the unbuffered path exists on Windows only")
def test_windows_uses_the_unbuffered_reader(tmp_path):
    path = tmp_path / "f.dat"
    path.write_bytes(b"x" * 10)
    chunks = read_chunks(path, 4096, uncached=True)
    assert chunks.__name__ == "_unbuffered"
    chunks.close()
