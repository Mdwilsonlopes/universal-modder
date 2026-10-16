---
kind: technique
title: "Eternity Audio Tool: safe audio-bank editing and verification"
tags: [eternity-audio-tool, PES, eFootball, audio, ACB, AWB, CSB, CPK, UAsset, HCA, ADX, AAX, CWAV, WAV, static-analysis, verification, backups]
date: 2026-10-16
agents: ["Cue (model not disclosed)"]
humans: ["@Mdwilsonlopes"]
links: []
status: in-progress
---

# Eternity Audio Tool: safe audio-bank editing and verification

> These are version-bounded static findings for Eternity Audio Tool 1.0beta1, not a claim that an edited bank or game has been tested. The operational Skill and detailed behavior register are in [`skills/eternity-audio-tool/`](../../skills/eternity-audio-tool/SKILL.md).

## Evidence boundary

The findings came from a static review of the Qt UI and `eternity_common` source for 1.0beta1. The source tree's exact commit/hash and per-file line references were not retained in this handoff. The program and game were not executed; no bank round trip, audio playback, or in-game validation is claimed. Reconfirm the source identity and findings before applying them to another release. No source code, proprietary binaries, game files, or extracted assets are included here.

## When to use it

Use this note when preparing PES/eFootball audio-bank edits with the Eternity Audio Tool. Treat the UI's file routing and safeguards as observations to verify on disposable copies, not as a supported-format guarantee.

## How

1. Record game/build, bank path, companion files, target track IDs, and intended operation.
2. Hash and copy the full bank set to a new working directory. Never use the original as a Save or Repair WAV target. The inspected Save flow removes existing ACB/AWB files before promoting temporary outputs; use Save As to an empty destination.
3. Pair ACB with its internal AWB or same-base-name external AWB. CSB expects CPK; UAsset expects ACB plus internal AWB. Recognized codecs include HCA, ADX, AAX, and CWAV; unknown entries may appear as BIN.
4. Map each WAV to one unique bank entry and test a single replacement first. Batch imports may collide or abort when mappings are duplicated or missing. Add-track behavior is fragile; do not automate it without separate testing.
5. Preflight WAVs as uncompressed PCM/IEEE float. Replace appears to validate channels more reliably than full sample-rate compatibility, and high-rate values may be truncated in ACB metadata. Do not infer import safety from channel count alone.
6. HCA auto cipher inference is ambiguous for mixed keys or `CIPH=56` and falls back to 0. Do not rely on that default. HCA encoding requires `hcaenctool0.exe` and `hcaenc_lite.dll`; keep these tools and any proprietary dependencies out of the repository.
7. Do not replace CWAV. Loop editing is limited; the inspected FFmpeg path does not expose loop markers. Combining tracks supports 2–8 sources only when sample-frame count, rate, and channel count match; a suspected loop issue in combined HCA remains unverified.
8. Save As, reopen the new bank, compare expected metadata and listen to the track, then test in an authorized offline game profile. Report each verification layer separately.

## Gotchas

1. **The output replaces the original bank.** **Cause:** the inspected Save path deletes existing ACB/AWB before renaming temporary files. **Fix:** hash/copy the full bank set and Save As to a new, empty directory.
2. **WAV repair changes the selected source.** **Cause:** the malformed-loop repair path can save to the same source path. **Fix:** repair a duplicate, never the only source copy.
3. **A WAV imports but its bank metadata is wrong.** **Cause:** Replace's observed validation is not a full sample-rate compatibility check; high rates may truncate in metadata. **Fix:** use known conservative settings, reopen the bank, and verify in game.
4. **The wrong HCA cipher is selected automatically.** **Cause:** mixed inputs or `CIPH=56` leave inference ambiguous and the fallback is 0. **Fix:** establish the cipher from a known compatible source or stop; do not guess.
5. **Looped audio loses or shifts its loop.** **Cause:** the FFmpeg backend does not expose markers, and HCA combination has a suspected loop issue. **Fix:** avoid loop edits or require a round trip plus in-game playback before use.
6. **A batch maps or imports the wrong tracks.** **Cause:** missing/duplicate mappings and add-track sequencing are fragile. **Fix:** use explicit unique IDs, preflight the manifest, and prove one replacement before expanding.

## Verification still owed

- Re-capture the source identity (version, commit/hash, and precise file/line evidence) for a reproducible report.
- On copies, exercise Save As and malformed-WAV repair while comparing source/output hashes.
- Run one-track round trips for each claimed codec/container route; inspect decoded audio and bank metadata.
- Test HCA cipher cases, loop retention, combine boundaries, and duplicate/missing batch mappings.
- Verify the final mod in a backed-up, authorized offline game profile.

Until those steps are completed, mark this knowledge as **in progress** and distinguish the static review from runtime proof.
