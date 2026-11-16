"""Compressed, memory-bounded storage for market data and results.

Two different pressures get conflated as "make it smaller", and they need
different tools:

* **Disk** -- a price history or a saved landscape sitting in a file.  Solved by
  compression, and float data compresses far better than most people expect once
  you stop insisting on all 52 mantissa bits.
* **RAM** -- how much has to be resident at once.  Compression does *not* help
  here; a decompressed array is the same size it always was.  What helps is
  memory-mapping (:func:`load_mmap`) and chunked iteration
  (:func:`iter_chunks`), which keep peak resident memory flat regardless of how
  large the file is.

Everything here is stdlib plus numpy.

Precision, honestly
-------------------
Downcasting is lossy and the loss is not uniform across use cases:

* ``float32`` carries ~7 significant digits, relative error ~1e-7.  Safe for
  prices, returns and covariances -- these are estimated from finite samples and
  carry statistical error many orders of magnitude larger.
* ``float16`` carries ~3 significant digits, relative error ~1e-3, and overflows
  above 65504.  Fine for correlations and weights in [0, 1]; **not** fine for
  prices, and not for anything that gets squared or inverted.
* Mantissa truncation (:func:`shave_mantissa`) keeps float64 range while zeroing
  low bits, which makes the data hugely more compressible without changing its
  dtype.  Prefer it when a consumer needs float64 but you control precision.

:func:`precision_report` measures the actual error on *your* array rather than
trusting these rules of thumb.
"""

from __future__ import annotations

import gzip
import io
import json
import lzma
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

__all__ = [
    "byte_shuffle",
    "byte_unshuffle",
    "recommended_dtype",
    "DowncastAdvice",
    "save_compressed",
    "load_compressed",
    "load_mmap",
    "iter_chunks",
    "shave_mantissa",
    "precision_report",
    "CompressionReport",
    "compare_codecs",
]


def byte_shuffle(array: np.ndarray) -> bytes:
    """Transpose bytes so all exponent bytes sit together, then all mantissa bytes.

    A compressor works on runs of similar bytes.  In native layout, each float's
    high-entropy mantissa bytes sit between its low-entropy exponent bytes, so
    the stream looks random.  Grouping by byte position puts the slowly-varying
    exponents in one long run.  This is what Blosc's shuffle filter does.

    **Measured on this package's data: +17% on prices, +19% on float32 prices,
    +16% on returns -- but -29% on a covariance matrix.** Covariances span a wide
    dynamic range, so their exponent bytes are high-entropy too and the shuffle
    only separates bytes that were already compressing well together.  Never
    apply it unconditionally; :func:`save_compressed` decides by measurement.
    """
    a = np.ascontiguousarray(array)
    raw = a.view(np.uint8).reshape(-1, a.dtype.itemsize)
    return np.ascontiguousarray(raw.T).tobytes()


def byte_unshuffle(buffer: bytes, dtype: np.dtype, shape: tuple[int, ...]) -> np.ndarray:
    """Invert :func:`byte_shuffle`."""
    itemsize = np.dtype(dtype).itemsize
    raw = np.frombuffer(buffer, np.uint8).reshape(itemsize, -1)
    # Transpose back to native byte order, flatten, *then* reinterpret: viewing
    # before flattening would reinterpret across the wrong axis.
    flat = np.ascontiguousarray(raw.T).reshape(-1)
    return flat.view(dtype).reshape(shape)


@dataclass
class DowncastAdvice:
    """Whether a matrix can safely be stored in a narrower float type."""

    dtype: str
    condition_number: float
    reason: str
    safe: bool

    def __repr__(self) -> str:  # pragma: no cover - display helper
        return f"<Downcast {self.dtype} cond={self.condition_number:.2e} safe={self.safe}>"


def recommended_dtype(matrix: np.ndarray, margin: float = 0.1) -> DowncastAdvice:
    """Decide whether ``matrix`` survives float32 storage, from its conditioning.

    A relative perturbation of ``eps`` shifts eigenvalues by roughly
    ``eps * lambda_max``, so a matrix stays usable only while
    ``cond(M) <~ margin / eps``.  With ``margin=0.1`` that is about ``1e6`` for
    float32 and ``1e4`` for float16.

    This matters because it is exactly the failure mode a covariance matrix
    walks into: a sample covariance estimated from roughly as many observations
    as assets is near-singular, and downcasting it can push the smallest
    eigenvalue negative -- turning a valid covariance into one that is not
    positive semi-definite, which breaks Cholesky and makes the optimiser
    produce nonsense rather than an error.

    Shrink or regularise first (see :func:`quantum.market.ledoit_wolf_shrinkage`),
    then re-check.  Storage precision and *arithmetic* precision are separate
    decisions: computing in float64 while storing in float32 is fine.
    """
    m = np.asarray(matrix, dtype=np.float64)
    if m.ndim != 2 or m.shape[0] != m.shape[1]:
        # Not a matrix: only the value range matters, not conditioning.
        finite = np.abs(m[np.isfinite(m)])
        largest = float(finite.max()) if finite.size else 0.0
        if largest > 3.0e38:
            return DowncastAdvice("float64", float("nan"), "values exceed the float32 range", False)
        return DowncastAdvice("float32", float("nan"), "not a matrix; range fits float32", True)

    condition = float(np.linalg.cond(m))
    float32_limit = margin / float(np.finfo(np.float32).eps)
    if not np.isfinite(condition):
        return DowncastAdvice("float64", condition, "matrix is singular", False)
    if condition <= float32_limit:
        return DowncastAdvice(
            "float32", condition,
            f"cond {condition:.2e} is within the float32 limit of {float32_limit:.2e}",
            True,
        )
    return DowncastAdvice(
        "float64", condition,
        f"cond {condition:.2e} exceeds the float32 limit of {float32_limit:.2e}; "
        "downcasting risks losing positive semi-definiteness",
        False,
    )


_CODECS = {
    "zlib": (zlib.compress, zlib.decompress),
    "gzip": (gzip.compress, gzip.decompress),
    "lzma": (lzma.compress, lzma.decompress),
}


@dataclass
class CompressionReport:
    """What a codec/precision combination actually achieved."""

    codec: str
    dtype: str
    raw_bytes: int
    stored_bytes: int
    compress_seconds: float
    decompress_seconds: float
    max_relative_error: float

    @property
    def ratio(self) -> float:
        return self.raw_bytes / max(self.stored_bytes, 1)

    def __repr__(self) -> str:  # pragma: no cover - display helper
        return (
            f"<{self.codec}/{self.dtype} {self.ratio:.2f}x "
            f"({self.raw_bytes/1e6:.2f} -> {self.stored_bytes/1e6:.2f} MB) "
            f"rel_err={self.max_relative_error:.1e}>"
        )


# --------------------------------------------------------------------------
# Precision control
# --------------------------------------------------------------------------


def shave_mantissa(array: np.ndarray, keep_bits: int = 20) -> np.ndarray:
    """Zero the low mantissa bits of a float array, preserving dtype and range.

    A float64 mantissa is 52 bits.  Scientific data rarely justifies all of them,
    and the low bits are effectively random -- which is exactly what defeats a
    compressor, since random bits are incompressible.  Zeroing them leaves long
    runs the codec can collapse.

    ``keep_bits=20`` retains about 6 significant decimal digits (relative error
    ~1e-6), comfortably finer than any statistically estimated quantity here.
    Returns a new array; the input is not modified.
    """
    a = np.asarray(array)
    if a.dtype == np.float64:
        mantissa_bits, int_type = 52, np.uint64
    elif a.dtype == np.float32:
        mantissa_bits, int_type = 23, np.uint32
    else:
        return a.copy()

    keep_bits = max(0, min(int(keep_bits), mantissa_bits))
    drop = mantissa_bits - keep_bits
    if drop == 0:
        return a.copy()

    view = a.astype(a.dtype, copy=True).view(int_type)
    mask = int_type(~((int_type(1) << int_type(drop)) - int_type(1)))
    # Round to nearest rather than truncating, which halves the bias.
    half = int_type(1) << int_type(drop - 1)
    np.add(view, half, out=view)
    np.bitwise_and(view, mask, out=view)
    return view.view(a.dtype)


def precision_report(original: np.ndarray, restored: np.ndarray) -> float:
    """Maximum relative error between an array and its round-tripped version."""
    a = np.asarray(original, dtype=np.float64).reshape(-1)
    b = np.asarray(restored, dtype=np.float64).reshape(-1)
    if a.shape != b.shape:
        raise ValueError("arrays must have the same shape")
    scale = np.maximum(np.abs(a), 1e-300)
    return float(np.max(np.abs(a - b) / scale))


# --------------------------------------------------------------------------
# Save / load
# --------------------------------------------------------------------------


def save_compressed(
    path: str | Path,
    arrays: dict[str, np.ndarray],
    dtype: str | None = None,
    keep_bits: int | None = None,
    codec: str = "zlib",
    level: int = 1,
    shuffle: bool | str = "auto",
    metadata: dict | None = None,
) -> Path:
    """Write named arrays to one compressed file.

    Parameters
    ----------
    dtype:
        Optional downcast applied before compression, e.g. ``"float32"``.
    keep_bits:
        Optional mantissa truncation (see :func:`shave_mantissa`), applied before
        compression.  Combines with ``dtype``.
    codec:
        ``"zlib"`` (fast, good), ``"gzip"`` (same algorithm plus a header), or
        ``"lzma"`` (much smaller, much slower).  Use :func:`compare_codecs` to
        pick on real data.
    level:
        Deflate level, default **1**.  Measured on price data, level 1 gives
        1.056x and level 6 gives 1.064x -- a 0.8% ratio gain for 25% more time,
        and level 9 is identical to level 6.  High deflate levels buy nothing on
        float data; the entropy is in the mantissas, not in repeated substrings.
    shuffle:
        Byte-transpose before compressing (see :func:`byte_shuffle`).  ``"auto"``
        measures both on a sample and keeps the better, which matters because
        the shuffle helps prices by ~17% and hurts covariances by ~29%.
    """
    path = Path(path)
    if codec not in _CODECS:
        raise ValueError(f"unknown codec {codec!r}; choose from {sorted(_CODECS)}")

    prepared: dict[str, np.ndarray] = {}
    for name, array in arrays.items():
        a = np.asarray(array)
        if keep_bits is not None and a.dtype.kind == "f":
            a = shave_mantissa(a, keep_bits)
        if dtype is not None and a.dtype.kind == "f":
            a = a.astype(dtype)
        prepared[name] = a

    compress = _CODECS[codec][0]

    def _compress(payload: bytes) -> bytes:
        return compress(payload) if codec == "lzma" else compress(payload, level)

    use_shuffle = _decide_shuffle(shuffle, prepared, _compress)
    if use_shuffle:
        # Store each array's shuffled bytes plus enough to rebuild it.
        payload = b"".join(byte_shuffle(a) for a in prepared.values())
    else:
        buffer = io.BytesIO()
        np.savez(buffer, **prepared)
        payload = buffer.getvalue()

    blob = _compress(payload)

    header = json.dumps(
        {
            "codec": codec,
            "shuffled": bool(use_shuffle),
            "order": list(prepared),
            "arrays": {k: {"dtype": str(v.dtype), "shape": list(v.shape)}
                       for k, v in prepared.items()},
            "keep_bits": keep_bits,
            "metadata": metadata or {},
        }
    ).encode("utf-8")

    with path.open("wb") as fh:
        fh.write(b"QTZ1")
        fh.write(len(header).to_bytes(4, "little"))
        fh.write(header)
        fh.write(blob)
    return path


def load_compressed(path: str | Path) -> tuple[dict[str, np.ndarray], dict]:
    """Read a file written by :func:`save_compressed`.

    Returns ``(arrays, header)``.  Note this decompresses fully into RAM -- for a
    file larger than memory use :func:`load_mmap` on an uncompressed ``.npy``
    instead, since compression and random access are mutually exclusive.
    """
    path = Path(path)
    with path.open("rb") as fh:
        if fh.read(4) != b"QTZ1":
            raise ValueError(f"{path} is not a quantum-storage file")
        header_len = int.from_bytes(fh.read(4), "little")
        header = json.loads(fh.read(header_len).decode("utf-8"))
        blob = fh.read()

    decompress = _CODECS[header["codec"]][1]
    payload = decompress(blob)

    if header.get("shuffled"):
        arrays = {}
        offset = 0
        for name in header["order"]:
            spec = header["arrays"][name]
            dtype = np.dtype(spec["dtype"])
            shape = tuple(spec["shape"])
            nbytes = int(np.prod(shape)) * dtype.itemsize if shape else dtype.itemsize
            arrays[name] = byte_unshuffle(payload[offset : offset + nbytes], dtype, shape)
            offset += nbytes
        return arrays, header

    with np.load(io.BytesIO(payload)) as data:
        arrays = {k: data[k] for k in data.files}
    return arrays, header


def _decide_shuffle(shuffle, prepared: dict[str, np.ndarray], compress) -> bool:
    """Resolve ``shuffle="auto"`` by measuring both layouts on a sample."""
    if isinstance(shuffle, bool):
        return shuffle
    if shuffle != "auto":
        raise ValueError("shuffle must be True, False, or 'auto'")
    if not prepared:
        return False

    # Sample the largest array; the decision is layout-driven, not size-driven.
    sample = max(prepared.values(), key=lambda a: a.nbytes)
    flat = np.asarray(sample).reshape(-1)
    if flat.size == 0 or sample.dtype.kind != "f":
        return False
    limit = min(flat.size, 1 << 17)
    probe = np.ascontiguousarray(flat[:limit])
    plain = len(compress(probe.tobytes()))
    shuffled = len(compress(byte_shuffle(probe)))
    return shuffled < plain


def load_mmap(path: str | Path) -> np.ndarray:
    """Memory-map an uncompressed ``.npy`` file.

    The array is not read into RAM; pages load on access and the OS evicts them
    under pressure.  This is the tool for arrays larger than memory -- but it
    requires the file to be *uncompressed*, which is the trade: compression saves
    disk, memory-mapping saves RAM, and you cannot have both on one file.
    """
    return np.load(Path(path), mmap_mode="r")


def iter_chunks(
    array: np.ndarray,
    chunk_rows: int = 100_000,
) -> Iterator[np.ndarray]:
    """Iterate an array in row blocks, bounding resident memory.

    Works on a memory-mapped array too, which is the point: the combination
    streams a file of any size through a fixed-size window.
    """
    if chunk_rows < 1:
        raise ValueError("chunk_rows must be positive")
    total = array.shape[0]
    for start in range(0, total, chunk_rows):
        yield array[start : min(start + chunk_rows, total)]


def compare_codecs(
    array: np.ndarray,
    codecs: tuple[str, ...] = ("zlib", "lzma"),
    dtypes: tuple[str | None, ...] = (None, "float32"),
    keep_bits: tuple[int | None, ...] = (None, 20, 12),
) -> list[CompressionReport]:
    """Measure ratio, speed and accuracy of each option on *this* array.

    Compression ratios are extremely data-dependent -- smooth series compress,
    noise does not -- so measuring beats trusting a table.
    """
    import time

    a = np.asarray(array)
    raw = a.nbytes
    reports: list[CompressionReport] = []

    for codec in codecs:
        compress, decompress = _CODECS[codec]
        for dtype in dtypes:
            for bits in keep_bits:
                prepared = a
                if bits is not None and prepared.dtype.kind == "f":
                    prepared = shave_mantissa(prepared, bits)
                if dtype is not None and prepared.dtype.kind == "f":
                    prepared = prepared.astype(dtype)

                payload = prepared.tobytes()
                t0 = time.perf_counter()
                blob = compress(payload) if codec == "lzma" else compress(payload, 6)
                t1 = time.perf_counter()
                restored_bytes = decompress(blob)
                t2 = time.perf_counter()

                restored = np.frombuffer(restored_bytes, dtype=prepared.dtype).reshape(
                    prepared.shape
                )
                label = f"{dtype or a.dtype}" + (f"/{bits}b" if bits is not None else "")
                reports.append(
                    CompressionReport(
                        codec=codec,
                        dtype=label,
                        raw_bytes=raw,
                        stored_bytes=len(blob),
                        compress_seconds=t1 - t0,
                        decompress_seconds=t2 - t1,
                        max_relative_error=precision_report(a, restored),
                    )
                )
    return sorted(reports, key=lambda r: -r.ratio)
