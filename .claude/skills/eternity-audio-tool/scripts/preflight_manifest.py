"""Read-only WAV and import-manifest preflight for Eternity Audio Tool workflows.

This validates RIFF/WAVE structure, uncompressed PCM/IEEE-float encoding, unique
source/track mappings, explicit expected metadata, and the known combine limits.
It does not parse ACB/AWB/CSB/CPK/UAsset files or predict Eternity/game behavior.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any


class PreflightError(ValueError):
    """A WAV or manifest does not meet the declared preflight contract."""


class DuplicateKeyError(ValueError):
    """A JSON object repeats a key, making the manifest ambiguous."""


_GUID_SUFFIX = bytes.fromhex("00 00 10 00 80 00 00 aa 00 38 9b 71")
_EXPECTED_FIELDS = {
    "expected_channels": "channels",
    "expected_sample_rate": "sample_rate_hz",
    "expected_frames": "sample_frames",
}
_ENTRY_FIELDS = {"track_id", "wav", *_EXPECTED_FIELDS}


def _read_exact(stream: Any, size: int, what: str) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise PreflightError(f"truncated {what}")
    return data


def inspect_wav(path: Path) -> dict[str, int | str]:
    """Read WAV headers without loading or changing audio payload bytes."""
    try:
        file_size = path.stat().st_size
        stream_context = path.open("rb")
    except OSError as exc:
        raise PreflightError(f"cannot read WAV ({exc.strerror or exc.__class__.__name__})") from exc

    with stream_context as stream:
        header = _read_exact(stream, 12, "RIFF header")
        if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            raise PreflightError("not a little-endian RIFF/WAVE file")
        riff_end = 8 + struct.unpack("<I", header[4:8])[0]
        if riff_end < 12 or riff_end > file_size:
            raise PreflightError("RIFF size is inconsistent with the file length")

        fmt: dict[str, int | str] | None = None
        data_sizes: list[int] = []
        offset = 12
        while offset < riff_end:
            if riff_end - offset < 8:
                raise PreflightError("incomplete RIFF chunk header")
            stream.seek(offset)
            chunk_header = _read_exact(stream, 8, "RIFF chunk header")
            chunk_id = chunk_header[:4]
            chunk_size = struct.unpack("<I", chunk_header[4:])[0]
            payload_start = offset + 8
            payload_end = payload_start + chunk_size
            next_offset = payload_end + (chunk_size & 1)
            if payload_end > riff_end or next_offset > riff_end:
                raise PreflightError("RIFF chunk exceeds the declared container size")

            if chunk_id == b"fmt ":
                if fmt is not None:
                    raise PreflightError("multiple fmt chunks are ambiguous")
                if chunk_size < 16:
                    raise PreflightError("fmt chunk is shorter than WAVEFORMAT")
                stream.seek(payload_start)
                raw_fmt = _read_exact(stream, 16, "WAVEFORMAT")
                format_code, channels, sample_rate, byte_rate, block_align, bits = struct.unpack(
                    "<HHIIHH", raw_fmt
                )
                valid_bits = bits
                if format_code == 0xFFFE:
                    if chunk_size < 40:
                        raise PreflightError("WAVE_FORMAT_EXTENSIBLE fmt chunk is shorter than 40 bytes")
                    stream.seek(payload_start + 16)
                    extension = _read_exact(stream, 24, "WAVE_FORMAT_EXTENSIBLE fields")
                    extension_size, valid_bits, _channel_mask = struct.unpack("<HHI", extension[:8])
                    guid = extension[8:]
                    if extension_size < 22 or guid[4:] != _GUID_SUFFIX:
                        raise PreflightError("unsupported WAVE_FORMAT_EXTENSIBLE subformat GUID")
                    format_code = struct.unpack("<I", guid[:4])[0]
                    if not 1 <= valid_bits <= bits:
                        raise PreflightError("extensible valid-bits value is inconsistent")

                if format_code == 1:
                    encoding = "PCM"
                    if bits not in (8, 16, 24, 32):
                        raise PreflightError(f"unsupported PCM container width: {bits} bits")
                elif format_code == 3:
                    encoding = "IEEE float"
                    if bits not in (32, 64):
                        raise PreflightError(f"unsupported IEEE-float container width: {bits} bits")
                else:
                    raise PreflightError(f"unsupported/compressed WAV format code: {format_code}")

                if channels < 1 or sample_rate < 1:
                    raise PreflightError("channel count and sample rate must be positive")
                expected_align = channels * ((bits + 7) // 8)
                if block_align != expected_align:
                    raise PreflightError("block-align value does not match channels and sample width")
                if byte_rate != sample_rate * block_align:
                    raise PreflightError("byte-rate value does not match sample rate and block alignment")
                fmt = {
                    "encoding": encoding,
                    "channels": channels,
                    "sample_rate_hz": sample_rate,
                    "bits_per_sample": bits,
                    "valid_bits_per_sample": valid_bits,
                    "block_align": block_align,
                }
            elif chunk_id == b"data":
                data_sizes.append(chunk_size)

            offset = next_offset

        if fmt is None:
            raise PreflightError("missing fmt chunk")
        if not data_sizes:
            raise PreflightError("missing data chunk")
        block_align = int(fmt["block_align"])
        if any(size % block_align for size in data_sizes):
            raise PreflightError("data chunk length is not a whole number of sample frames")
        data_bytes = sum(data_sizes)
        sample_frames = data_bytes // block_align
        if sample_frames < 1:
            raise PreflightError("WAV contains no audio sample frames")
        return {
            **fmt,
            "data_bytes": data_bytes,
            "sample_frames": sample_frames,
        }


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _error_report(manifest_name: str, message: str) -> dict[str, Any]:
    return {
        "status": "ERROR",
        "manifest": manifest_name,
        "operation": None,
        "entry_count": 0,
        "entries": [],
        "errors": [message],
        "limitations": ["This checker does not parse a game bank or verify tool/game compatibility."],
    }


def validate_manifest(manifest: str | Path) -> dict[str, Any]:
    """Validate a version-1 manifest and its contained WAV inputs."""
    candidate = Path(manifest)
    try:
        manifest_path = candidate.resolve(strict=True)
        payload = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateKeyError) as exc:
        detail = getattr(exc, "strerror", None) or str(exc)
        return _error_report(candidate.name, f"cannot load manifest: {detail}")

    if not isinstance(payload, dict):
        return _error_report(manifest_path.name, "manifest root must be a JSON object")

    errors: list[str] = []
    allowed_root = {"version", "operation", "entries", "output_track_id"}
    for key in sorted(set(payload) - allowed_root):
        errors.append(f"unknown manifest field: {key}")
    if type(payload.get("version")) is not int or payload.get("version") != 1:
        errors.append("version must be integer 1")
    operation = payload.get("operation")
    if operation not in ("replace", "combine"):
        errors.append('operation must be "replace" or "combine"')
        operation = None
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        return {
            "status": "FAIL",
            "manifest": manifest_path.name,
            "operation": operation,
            "entry_count": 0,
            "entries": [],
            "errors": [*errors, "entries must be a non-empty array"],
            "limitations": ["WAV/manifest preflight only; no game-bank or runtime validation."],
        }

    output_track_id = payload.get("output_track_id")
    if operation == "combine":
        if not isinstance(output_track_id, str) or not output_track_id.strip():
            errors.append('combine requires a non-empty string "output_track_id"')
    elif "output_track_id" in payload:
        errors.append('output_track_id is valid only when operation is "combine"')

    if operation == "combine" and not 2 <= len(entries) <= 8:
        errors.append("combine requires 2–8 source entries")

    root = manifest_path.parent.resolve()
    seen_tracks: set[str] = set()
    seen_wavs: set[str] = set()
    checked_entries: list[dict[str, Any]] = []

    for index, item in enumerate(entries, start=1):
        label = f"entries[{index - 1}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be a JSON object")
            continue
        for key in sorted(set(item) - _ENTRY_FIELDS):
            errors.append(f"{label}: unknown field: {key}")

        track_id = item.get("track_id")
        if not isinstance(track_id, str) or not track_id.strip():
            errors.append(f"{label}: track_id must be a non-empty string")
            track_id = None
        elif track_id.casefold() in seen_tracks:
            errors.append(f"{label}: duplicate track_id (case-insensitive): {track_id}")
        else:
            seen_tracks.add(track_id.casefold())

        wav_value = item.get("wav")
        if not isinstance(wav_value, str) or not wav_value.strip():
            errors.append(f"{label}: wav must be a non-empty relative path")
            checked_entries.append({"track_id": track_id, "wav": wav_value, "wav_info": None})
            continue

        relative = Path(wav_value)
        if relative.is_absolute():
            errors.append(f"{label}: wav path must be relative to the manifest folder")
            checked_entries.append({"track_id": track_id, "wav": wav_value, "wav_info": None})
            continue
        try:
            wav_path = (root / relative).resolve(strict=False)
            if not wav_path.is_relative_to(root):
                errors.append(f"{label}: wav path escapes the manifest folder")
                checked_entries.append({"track_id": track_id, "wav": wav_value, "wav_info": None})
                continue
        except (OSError, RuntimeError) as exc:
            errors.append(f"{label}: invalid wav path ({exc.__class__.__name__})")
            checked_entries.append({"track_id": track_id, "wav": wav_value, "wav_info": None})
            continue

        source_key = str(wav_path).replace("\\", "/").casefold()
        if source_key in seen_wavs:
            errors.append(f"{label}: duplicate WAV source path: {wav_value}")
        else:
            seen_wavs.add(source_key)
        if not wav_path.is_file():
            errors.append(f"{label}: WAV file is missing or not a regular file: {wav_value}")
            checked_entries.append({"track_id": track_id, "wav": wav_value, "wav_info": None})
            continue

        try:
            wav_info = inspect_wav(wav_path)
        except (OSError, PreflightError, RuntimeError) as exc:
            errors.append(f"{label}: {wav_value}: {exc}")
            checked_entries.append({"track_id": track_id, "wav": wav_value, "wav_info": None})
            continue

        for manifest_field, wav_field in _EXPECTED_FIELDS.items():
            if manifest_field not in item:
                continue
            expected = item[manifest_field]
            if type(expected) is not int or expected < 1:
                errors.append(f"{label}: {manifest_field} must be a positive integer")
            elif wav_info[wav_field] != expected:
                errors.append(
                    f"{label}: {manifest_field}={expected} does not match WAV {wav_field}={wav_info[wav_field]}"
                )
        checked_entries.append({"track_id": track_id, "wav": wav_value, "wav_info": wav_info})

    if operation == "combine" and len(checked_entries) >= 2:
        complete = [entry["wav_info"] for entry in checked_entries]
        if all(info is not None for info in complete):
            keys = ("sample_frames", "sample_rate_hz", "channels")
            signatures = [tuple(info[key] for key in keys) for info in complete]
            if len(set(signatures)) != 1:
                errors.append(
                    "combine sources must have identical sample_frames, sample_rate_hz, and channels"
                )

    return {
        "status": "PASS" if not errors else "FAIL",
        "manifest": manifest_path.name,
        "operation": operation,
        "output_track_id": output_track_id if operation == "combine" else None,
        "entry_count": len(entries),
        "entries": checked_entries,
        "errors": errors,
        "limitations": [
            "Read-only WAV/manifest preflight; ACB/AWB/CSB/CPK/UAsset contents are not parsed.",
            "A PASS does not establish Eternity import, saved-bank integrity, or in-game playback.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="version-1 JSON manifest (WAV paths stay within its folder)")
    args = parser.parse_args(argv)
    report = validate_manifest(args.manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else (1 if report["status"] == "FAIL" else 2)


if __name__ == "__main__":
    sys.exit(main())
