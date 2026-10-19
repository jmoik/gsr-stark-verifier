# Port to jmoik/bitcoin `gsr`

The `bitcoin` submodule tracks `jmoik/bitcoin` branch `gsr` (`ad6c16f`) instead of `gsr-full` (`d279905`). The
`gsr` branch uses the gsr-net opcode set.

| | `gsr-full` | `gsr` |
|---|---|---|
| `OP_TX` | 0xbd | 0xbf |
| Functions | `OP_DEFINE` 0xbb / `OP_INVOKE` 0xbc | reusable macros: `OP_MACRO` 0xd0 declarations open the script; `OP_CALLMACRO` 0xd1 `<CompactSize index>` |
| `OP_MULTI` 0xbf | yes | no |
| Deployment | `script_restoration` | `tapleaf_0xc2` |
| `bitcoin-util evalscript` sigversion | `tapscript_v2` | `tapleaf_0xc2` |

The OP_TX selector format (six bytes, versioned) is unchanged.

## Results (regtest, `gsr` @ `ad6c16f`)

| | `gsr-full` (cited) | `gsr` | `gsr`, compressed |
|---|---:|---:|---:|
| RISC Zero verifier script, fixed statement | 158,572 B | 160,600 B | 91,550 B |
| Covenant spend with the committed receipt | 388,641 WU | 390,661 WU | **321,301 WU** |
| Rollup settlement leaf | 159,265 B | 161,252 B | 92,023 B |
| Rollup settlement, one join-split | 392,001 WU | ≈ 394,000 WU (est.) | ≈ 324,800 WU (est.) |

- **Port (+2 kB).** Expanding `OP_MULTI` costs about 2 kB (mostly `<6> OP_MULTI OP_ADD` at 514 sites); macro
  declarations and calls are slightly smaller than `OP_DEFINE`/`OP_INVOKE`. The uncompressed verifier is
  byte-identical to the gsr-full script converted by an independent converter whose output was mined on gsr-net.
- **Compression (−69 kB).** About three quarters of the main script is stack routing (depth pushes, `PICK`, `ROLL`)
  in short patterns that recur hundreds of times. `gsr compress` from
  [gsr-tooling](https://github.com/bitcoin-gsr/gsr-tooling), pinned in `risc0-succinct/tools/gsr_tooling.py`, moves
  them into nested macros; the unrolled script (3,361,215 B, 84% of the 4 MB limit) is unchanged. Varops rise by the
  unrolling charge (1.767B → 1.829B for the fixed statement), about 57% of the budget.
- **Same verifier.** `gsr compress` returns only scripts that unroll byte for byte to its input, and under the
  reusable-macros BIP a script and its unrolled form give the same result except for what reads the script bytes,
  the budget and the unrolling charge. `gsr_tooling.compress` also rejects any result in which `gsr check` finds a
  consensus error, such as an OP_SUCCESSx or a malformed macro; the compressed verifiers have none, nor warnings
  or lints. The verifiers read nothing that depends on their script bytes (the covenant's only `OP_TX` reads the
  outputs). The rollup leaf reads its own script to splice in the next root, so its root push and prologue stay
  literal (`gsr compress --protect`) and its splice offsets add the declarations' length.
- **Real proof.** The covenant receipt's journal is the spending transaction's outputs, so it needs no re-proving:
  both the plain and the compressed spend are accepted under standard policy and mined; the same spend paying 1 sat
  less is rejected.
- **Rollup binding.** `privacy-rollup/tools/binding_check.py` mines a valid settlement shape (with the verifier
  replaced by a journal-digest comparison) and rejects a wrong journal digest, a redirected successor, a successor
  for another root and `nSequence = 0`. A compressed leaf spliced for a new root equals a freshly generated one.

The settlement estimates take the measured gsr-full settlement and swap in the new leaf; the rest of the witness is
unchanged. A full batch of 8 join-splits (≈ 410k WU before, estimated) should fit under 400k WU compressed.

## Reproduce

```sh
bash recursive-stwo/tools/build.sh                     # node, cli, util at ad6c16f
cargo install --locked --git https://github.com/bitcoin-gsr/gsr-tooling \
  --rev 04cda8374cef2ad05d9f90c67d7eb8e52ee47ba1       # gsr, for --compress and the covenants
python3 risc0-succinct/tools/generate.py [--compress]  # fixed-statement verifier
python3 -c 'import sys; sys.path.insert(0, "risc0-succinct/tools"); import json, covenant as c; \
  r = json.loads((c.ROOT / "fixtures/covenant-receipt.json").read_text()); \
  print(c.regtest(c.Covenant(r, (c.ROOT / "fixtures/covenant-seal.bin").read_bytes(), compressed=True)))'
python3 privacy-rollup/tools/binding_check.py          # writes build/binding-check.json
(cd recursive-stwo && bash tools/test.sh && cargo run --locked -- regtest-demo)  # Stwo verifier
```

## Meter

`gsr-meter` instruments the Tapleaf 0xC2 loop, which runs the unrolled script: `pc` is an unrolled offset and
`main_pc` the committed main-script instruction it belongs to; stage ends are translated the same way. Its
gsr-full fields `function_calls` and `invoked_body_bytes` became `macro_references` and `unrolled_bytes` (limit
4,000,000). The `gsr` budget deducts one signature check (500,000 varops) per Tapleaf 0xC2 input for its commitment
check; the tools' budget calculations follow, and the meter checks them against Core's. Its varops equal
`bitcoin-util evalscript`'s. A failing script is charged only its unrolling, since execution charges are deducted
when the script ends.

## Recursive Stwo verifier

Its lowering declares the same 128 shared fragments as macros instead of `OP_DEFINE` bodies, and calls them with
`OP_CALLMACRO`; the profile `profiles/bws-v1.json` is refrozen for `ad6c16f`. `tools/test.sh` passes (the profile
reproduces, the differential run succeeds, 397 malformed witnesses are rejected) and `regtest-demo` mines the spend.

| | `gsr-full` (README) | `gsr` |
|---|---:|---:|
| Script | 144,905 B | 139,129 B |
| Transaction weight | 370,387 WU | 364,611 WU |
| Varops | 1,399,895,948 | 1,306,473,856 |
| Size under the 4 MB limit: invoked bodies / unrolled script | 973,854 B | 1,054,095 B |
| Calls / macro references | 26,625 | 26,625 |

## Not yet ported

- A full rollup settlement on `gsr` needs new `apply_batch` receipts: the covenant's bytes, hence its address and
  every bound transaction, changed.
