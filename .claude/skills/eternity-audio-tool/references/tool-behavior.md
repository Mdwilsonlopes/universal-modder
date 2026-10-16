# Eternity Audio Tool 1.0beta1: static behavior reference

## Evidence boundary

These notes reflect a prior **static source review** of the Qt interface and `eternity_common` for Eternity Audio Tool 1.0beta1. The program and game were not run. The source snapshot's commit/hash and per-file line references were not retained in this handoff; treat each item as a version-bounded finding to re-check against a hashed copy before relying on a later release or publishing a claim. No source code, executable, game file, or extracted asset belongs in this repository.

## Container and codec routing

| Input/operation | Static finding | Operational rule |
|---|---|---|
| ACB | Can use an internal AWB or an external AWB; the external companion is sought by the same base name. | Inventory and copy both files together. Verify exact pairing before opening or saving. |
| CSB | The workflow uses a CPK. | Keep the required CPK in the disposable working set; do not infer support from a `.csb` filename alone. |
| UAsset | Requires an ACB and an internal AWB. | Treat missing dependencies as unresolved; do not substitute a guessed bank. |
| Track codecs | HCA, ADX, AAX, and CWAV are recognized; unrecognized entries may be shown as BIN. | BIN is an unknown classification, not a conversion target. Do not replace unknown entries. |
| WAV import | Input is expected to be uncompressed PCM or IEEE float. | Preflight the WAV container and encoding. Compressed audio in a WAV wrapper is not equivalent. |

## Editing and save hazards

- The Save path removes existing ACB/AWB files before renaming temporary outputs. Always work from a copy and use **Save As** to a fresh, separate destination. The successful static walk-through of this code path does not establish crash safety or atomicity.
- A malformed loop WAV can be repaired by saving back to the selected source path. Run repair only on a duplicate; never select the only copy of a source recording.
- Replace appears to check channel count more reliably than full sample-rate compatibility. Do not infer that matching channels guarantees import correctness. A high sample rate may be truncated in ACB metadata; use conservative, measured values and verify the saved bank.
- Automatic HCA cipher inference is indeterminate for mixed cipher inputs or `CIPH=56`; the observed fallback is cipher 0. Do not accept that fallback as evidence of the intended cipher. Preserve/derive the setting from a known compatible bank or stop and resolve it.
- CWAV cannot be replaced through the observed replacement path.
- The loop editor has limits, and the inspected FFmpeg backend does not expose loop markers. Avoid loop editing unless a separate round-trip proves the exact markers survive.
- Combining tracks is limited to 2–8 inputs with exactly the same sample-frame count, sample rate, and channel count. A suspected loop issue in combined HCA output remains unverified; require a round trip before use.
- Batch import can collide or abort when mappings are duplicated or incomplete. Add-track sequencing was fragile in the inspected workflow. Do not automate either path until the mapping/sequence is proven on copies.

## Confidence and verification still owed

| Claim group | Basis | What is not established |
|---|---|---|
| File routing, supported codec labels, import/replace rules | Static UI/controller and common-library review | Runtime behavior on Windows, actual bank compatibility, exact versions beyond 1.0beta1 |
| Destructive save/repair effects and fragile batch paths | Static control-flow review | Behavior on filesystem errors, interrupted writes, permissions, or every container variation |
| Loop/cipher/metadata caveats | Static implementation paths | Actual audible output or game interpretation |
| Any successful mod | None | No tool round trip, decoded output comparison, or in-game test has been performed |

Use isolated copies and record tool build, source/bank hashes, input WAV hashes, exact target IDs, output hashes, and test outcome. A metadata/preflight pass is not a bank round trip; a bank round trip is not proof of in-game playback.
