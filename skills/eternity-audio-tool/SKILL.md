---
name: eternity-audio-tool
description: Prepare, replace, combine, and verify audio for PES/eFootball mods with Eternity Audio Tool 1.0beta1. Use when editing ACB/AWB, CSB/CPK, UAsset audio, WAV imports, HCA/ADX/AAX/CWAV tracks, or batch audio replacements; includes preflight checks and safe-save rules.
---

# Eternity Audio Tool

Use this skill for the statically inspected **Eternity Audio Tool 1.0beta1** workflow. Treat its format and UI behavior as version-specific; do not assume a later build behaves the same. The tool and game have not yet been runtime-verified by this project. Read [`references/tool-behavior.md`](references/tool-behavior.md) before touching a bank.

## Workflow

1. **Resolve the target.** Record the exact PES/eFootball edition, platform/build, audio container, intended track(s), and whether the test will be offline. Work only on a game the user owns and within the existing modding rules. Do not use an online/anti-cheat-protected client.
2. **Make a disposable copy first.** Inventory the original bank and its companion files, record hashes, then copy the complete set to a separate working directory. Never point Save, Repair WAV, or any write action at the source. The inspected Save path can remove the existing ACB/AWB before promoting temporary outputs; use a fresh **Save As** destination, preserve the original, and do not overwrite an existing output.
3. **Classify the container and dependencies.** For ACB, locate its internal AWB or the external AWB with the same base name. CSB workflows require the associated CPK. UAsset workflows require an ACB and internal AWB. Identify each track's codec; unknown/BIN entries are not permission to convert or replace them. See the behavior reference for the supported codecs and limitations.
4. **Create an explicit, one-to-one track map.** Use stable bank entry IDs/names, not list position alone. Resolve every input WAV to exactly one intended target. Stop on missing, duplicate, or ambiguous mappings; do not run a batch or add-track operation until the mapping is unambiguous. Start with one replacement and retain the mapping in `MODLOG.md`.
5. **Preflight WAVs and the manifest.** Use uncompressed PCM or IEEE-float WAV only. Put the manifest and its input WAVs in a dedicated working folder, with paths relative to that folder. Resolve `<skill-dir>` as the directory containing this `SKILL.md`, then run the bundled read-only checker:
   - Linux/macOS: `python3 "<skill-dir>/scripts/preflight_manifest.py" --manifest "<manifest-folder>/audio-imports.json"`
   - Windows PowerShell: `py -3 "<skill-dir>\scripts\preflight_manifest.py" --manifest "<manifest-folder>\audio-imports.json"`

   The checker validates RIFF/WAVE structure, PCM/float encoding, unique track IDs and input files, and any explicit expected channel/rate/frame values. For `operation: "combine"`, it also enforces 2–8 inputs with identical sample-frame count, sample rate, and channel count. A PASS is **only a WAV/manifest preflight**: it does not parse ACB metadata, prove Eternity will accept a file, or prove in-game playback. Set expected values only from inspected target metadata or a measured reference; do not invent them.
6. **Use a narrow edit.** Replace one track first. Treat HCA cipher/key detection as unresolved for mixed-key banks or `CIPH=56`; do not trust the automatic fallback to cipher 0. HCA encoding requires `hcaenctool0.exe` and `hcaenc_lite.dll` in the expected tool environment. Do not fetch unknown binaries, include proprietary tool files in the repository, or guess a cipher. Do not replace CWAV. Avoid loop edits unless their markers can be independently preserved and verified; the inspected FFmpeg path does not expose loop markers. A combined HCA track with loop data needs a round trip before it can be trusted. Treat batch import and add-track as fragile and test each change on copies.
7. **Save and verify in layers.** Save As to a new, empty output directory. Reopen the saved bank and confirm the intended entry, codec, channel/rate/duration metadata, and companion-file pairing. Decode or listen to the replacement and check for clipping, silence, wrong language/content, and unwanted leading/trailing audio. Record results separately as `preflight`, `tool round-trip`, and `game runtime` evidence.
8. **Test in the real game only when authorized.** Use a backed-up offline/profile copy of the user's own game. Verify the changed event/scene and listen for timing, looping, channel, and mix behavior. A successful import or reopened bank is not proof of game compatibility. If the game is online/anti-cheat-protected, do not launch or modify that client.
9. **Journal and report.** In `MODLOG.md`, record tool version, source/output paths, hashes, bank/track IDs, manifest, parameters, exact failures, and which verification layer passed. Leave all source files untouched. Report unverified properties explicitly.

## Manifest format

`templates/audio-import-manifest.json` is a starting point. Every manifest has `version: 1`, `operation: "replace"` or `"combine"`, and an `entries` array. Each entry has a unique `track_id` and a relative `wav` path. Optional `expected_channels`, `expected_sample_rate`, and `expected_frames` compare against values you already know. `combine` also requires `output_track_id` and exactly 2–8 source entries; the script checks their actual frame count, rate, and channels. The checker is read-only and never edits or repairs WAVs.

Do not represent fragile **add-track** work as a replacement manifest; that workflow is not covered by the checker.

## Stop or ask only when it changes the outcome

Proceed without interrupting the user for routine, reversible preparation and deterministic checks. Pause only if the game/build or target bank is ambiguous, the mapping is not one-to-one, the HCA cipher cannot be established, the operation needs an unsupported codec/loop/CWAV replacement, Save/Repair targets the source or an existing output, or a required offline/runtime test would cross an authorization or anti-cheat boundary. If the same failure repeats three times, stop, preserve the work copy, and change approach instead of retrying blindly.
