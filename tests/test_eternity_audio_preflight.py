import json
import struct
import subprocess
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "eternity-audio-tool" / "scripts" / "preflight_manifest.py"
preflight = types.ModuleType("eternity_preflight")
preflight.__file__ = str(SCRIPT)
exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), preflight.__dict__)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    assert len(kind) == 4
    return kind + struct.pack("<I", len(payload)) + payload + (b"\0" if len(payload) & 1 else b"")


def write_wav(
    path: Path,
    *,
    format_code: int = 1,
    channels: int = 2,
    sample_rate: int = 48_000,
    bits: int = 16,
    frames: int = 12,
    extensible: bool = False,
) -> Path:
    block_align = channels * ((bits + 7) // 8)
    base_fmt = struct.pack(
        "<HHIIHH",
        0xFFFE if extensible else format_code,
        channels,
        sample_rate,
        sample_rate * block_align,
        block_align,
        bits,
    )
    if extensible:
        guid = struct.pack(
            "<IHH8s",
            format_code,
            0,
            0x10,
            bytes.fromhex("80 00 00 aa 00 38 9b 71"),
        )
        fmt = base_fmt + struct.pack("<HHI", 22, bits, 0) + guid
    else:
        fmt = base_fmt
    data = bytes(frames * block_align)
    body = b"WAVE" + _chunk(b"fmt ", fmt) + _chunk(b"data", data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path


def write_manifest(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def replace_manifest(*entries: dict) -> dict:
    return {"version": 1, "operation": "replace", "entries": list(entries)}


def test_pcm_manifest_passes_with_unicode_and_spaces_in_paths(tmp_path):
    wav = write_wav(tmp_path / "entrada áudio" / "tema principal.wav", frames=20)
    manifest = write_manifest(
        tmp_path / "import list.json",
        replace_manifest(
            {
                "track_id": "voice_001",
                "wav": "entrada áudio/tema principal.wav",
                "expected_channels": 2,
                "expected_sample_rate": 48_000,
                "expected_frames": 20,
            }
        ),
    )

    result = preflight.validate_manifest(manifest)

    assert result["status"] == "PASS"
    assert result["entries"][0]["wav_info"]["encoding"] == "PCM"
    assert result["entries"][0]["wav_info"]["sample_frames"] == 20
    assert wav.exists()


@pytest.mark.parametrize(
    ("format_code", "bits", "extensible", "expected_encoding"),
    [(3, 32, False, "IEEE float"), (1, 24, True, "PCM"), (3, 32, True, "IEEE float")],
)
def test_pcm_and_float_formats_are_recognized(format_code, bits, extensible, expected_encoding, tmp_path):
    wav = write_wav(
        tmp_path / "sample.wav",
        format_code=format_code,
        bits=bits,
        extensible=extensible,
    )

    assert preflight.inspect_wav(wav)["encoding"] == expected_encoding


def test_combine_requires_two_to_eight_identical_sources(tmp_path):
    write_wav(tmp_path / "a.wav", frames=17)
    write_wav(tmp_path / "b.wav", frames=17)
    payload = {
        "version": 1,
        "operation": "combine",
        "output_track_id": "combined_01",
        "entries": [
            {"track_id": "source_01", "wav": "a.wav"},
            {"track_id": "source_02", "wav": "b.wav"},
        ],
    }
    manifest = write_manifest(tmp_path / "combine.json", payload)
    assert preflight.validate_manifest(manifest)["status"] == "PASS"

    write_wav(tmp_path / "b.wav", frames=18)
    result = preflight.validate_manifest(manifest)
    assert result["status"] == "FAIL"
    assert any("identical sample_frames" in error for error in result["errors"])


def test_combine_rejects_input_count_outside_known_limits(tmp_path):
    write_wav(tmp_path / "only.wav")
    manifest = write_manifest(
        tmp_path / "combine.json",
        {
            "version": 1,
            "operation": "combine",
            "output_track_id": "target",
            "entries": [{"track_id": "source", "wav": "only.wav"}],
        },
    )

    result = preflight.validate_manifest(manifest)
    assert result["status"] == "FAIL"
    assert any("2–8 source entries" in error for error in result["errors"])


@pytest.mark.parametrize("different", [{"sample_rate": 44_100}, {"channels": 1}])
def test_combine_rejects_rate_or_channel_mismatch(tmp_path, different):
    write_wav(tmp_path / "first.wav", frames=9)
    write_wav(tmp_path / "second.wav", frames=9, **different)
    manifest = write_manifest(
        tmp_path / "combine.json",
        {
            "version": 1,
            "operation": "combine",
            "output_track_id": "target",
            "entries": [
                {"track_id": "source-1", "wav": "first.wav"},
                {"track_id": "source-2", "wav": "second.wav"},
            ],
        },
    )

    result = preflight.validate_manifest(manifest)
    assert result["status"] == "FAIL"
    assert any("identical sample_frames" in error for error in result["errors"])


def test_duplicate_track_ids_and_input_paths_fail_closed(tmp_path):
    write_wav(tmp_path / "same.wav")
    manifest = write_manifest(
        tmp_path / "dupes.json",
        replace_manifest(
            {"track_id": "track-a", "wav": "same.wav"},
            {"track_id": "TRACK-A", "wav": "same.wav"},
        ),
    )

    result = preflight.validate_manifest(manifest)
    assert result["status"] == "FAIL"
    assert any("duplicate track_id" in error for error in result["errors"])
    assert any("duplicate WAV source path" in error for error in result["errors"])


def test_compressed_wav_and_escaping_paths_are_rejected(tmp_path):
    work = tmp_path / "work"
    write_wav(work / "compressed.wav", format_code=2)
    outside = write_wav(tmp_path / "outside.wav")
    manifest = write_manifest(
        work / "unsafe.json",
        replace_manifest(
            {"track_id": "compressed", "wav": "compressed.wav"},
            {"track_id": "outside", "wav": "../outside.wav"},
        ),
    )

    result = preflight.validate_manifest(manifest)
    assert result["status"] == "FAIL"
    assert any("escapes the manifest folder" in error for error in result["errors"])
    assert any("unsupported/compressed WAV format code" in error for error in result["errors"])
    assert outside.exists()


def test_truncated_riff_and_expected_metadata_mismatch_fail(tmp_path):
    wav = write_wav(tmp_path / "broken.wav", frames=5)
    wav.write_bytes(wav.read_bytes()[:-1])
    manifest = write_manifest(
        tmp_path / "broken.json",
        replace_manifest(
            {
                "track_id": "broken",
                "wav": "broken.wav",
                "expected_sample_rate": 44_100,
            }
        ),
    )

    result = preflight.validate_manifest(manifest)
    assert result["status"] == "FAIL"
    assert any("RIFF size" in error or "chunk exceeds" in error for error in result["errors"])

    good = write_wav(tmp_path / "good.wav", sample_rate=48_000)
    good_manifest = write_manifest(
        tmp_path / "mismatch.json",
        replace_manifest(
            {"track_id": "good", "wav": good.name, "expected_sample_rate": 44_100}
        ),
    )
    mismatch = preflight.validate_manifest(good_manifest)
    assert mismatch["status"] == "FAIL"
    assert any("does not match WAV" in error for error in mismatch["errors"])


def test_cli_reads_manifest_under_unicode_and_spaced_directory(tmp_path):
    folder = tmp_path / "trabalho áudio com espaços"
    write_wav(folder / "som.wav")
    manifest = write_manifest(
        folder / "importação.json",
        replace_manifest({"track_id": "track-1", "wav": "som.wav"}),
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--manifest", str(manifest)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "PASS"


def test_duplicate_json_keys_are_rejected(tmp_path):
    manifest = tmp_path / "duplicate-key.json"
    manifest.write_text(
        '{"version":1,"version":1,"operation":"replace","entries":[]}',
        encoding="utf-8",
    )

    result = preflight.validate_manifest(manifest)

    assert result["status"] == "ERROR"
    assert any("duplicate JSON key" in error for error in result["errors"])
