# Bloodborne shadPS4 Runtime Research Baseline

Status: initial evidence record  
Target: `CUSA00900`, AppVer `01.09`  
Recorded: 2026-08-16

## Project boundary

This project does not reuse or adapt the existing Bloodborne randomizer. Its code,
binaries, extracted datasets, address tables, patches, and generated artifacts are
out of scope. Runtime research is derived independently from user-owned game files,
shadPS4, Ghidra, Cheat Engine, original probes, and separately published cheat or
emulator-patch evidence with attribution.

## Confirmed published runtime evidence

The published shadPS4 cheat corpus at
`ps4_cheats/CHEATS/CUSA00900_01.09.json`, attributed to Shiningami and bloo,
contains detours into a code cave. Reading the displaced machine instructions gives
the following game-structure offsets and hook sites:

| Observation | Hook site (`eboot` +) | Displaced/original instruction | Candidate structure offset |
| --- | ---: | --- | ---: |
| HP | `0x1BFC5F7` | `mov edx,[rdi+0xF8]` | `+0xF8` |
| Blood Echoes | `0x190029B` | `mov [rdx+0x94],ecx` | `+0x94` |
| Stamina | `0x18F78DB` | `mov eax,[rax+0x134]` | `+0x134` / `+0x138` |
| Frenzy/lucidity | `0x1901FB4` | `mov esi,[rbx+0x84]` | `+0x84` |
| Consumable quantity | `0x14D9556` | `mov r12d,eax; mov [rbx+8],r12d` | `+0x08` |

The consumable-quantity hook is the nearest published evidence of an inventory
seam. The source JSON's original bytes are `41 89 C4 44 89 63 08`: `mov r12d,eax`
followed by `mov [rbx+0x08],r12d`. Its cave replaces the source value with 20 in
`r12d` and writes that value to `[rbx+0x08]`. This corrects an earlier transcription
as `esp`; the JSON itself provides strong evidence that `+0x08` is the quantity
field for the structure reaching this hook. Which inventory structures and item
classes reach it still requires runtime validation.

## Known code-cave evidence

Two independent patch sources demonstrate apparently usable executable space:

- GoldHEN cheats place payloads in `0x50DB800`–`0x50DB889`.
- shadPS4's Performance Patch uses:
  - `0x00400170`–`0x004001F0` for NOP-padded trampolines ending in `FFE0`.
  - `0x00463190`–`0x00466816` for replacement function bodies ending in `C3`.

These ranges are evidence for the known `CUSA00900` 01.09 image, not a guarantee
that the space is safe across other serials, versions, patch combinations, or
future shadPS4 builds.

## Important correction: no version-independent corpus exists

The `mask` and `mask_jump32` mechanisms may support version-robust patches, but the
published Bloodborne corpus does not use them.

A complete review of `PATCHES/Bloodborne.xml` found:

- 25 patches.
- 1,019 patch lines.
- Zero `mask` patches.
- Zero `mask_jump32` patches.
- Every patch uses hardcoded addresses.
- Every patch targets AppVer `01.09`.

No published Bloodborne AOB signature has been identified. Creating and validating
such signatures would be original project work.

## Important correction: published shadPS4 patches do not expose game state

The Bloodborne patch XML concerns graphics, framerate, and crash fixes. Searches for
item, inventory, flag, save, progression, and boss found only incidental substrings.
No published patch in that file is evidence for event flags, inventory state,
location completion, progression, or item acquisition.

## Honest starting position

For `CUSA00900` 01.09, the currently recorded evidence consists of approximately:

- Five candidate structure offsets.
- Six known hook sites.
- Three known code-cave ranges/groups.

All are hard-bound to one serial and application version until independently
validated elsewhere.

Converting known hook sites into candidate signatures is straightforward in form:
capture surrounding bytes and wildcard relocations or varying displacements. It is
not complete until each signature is shown to be unique, resolves to the intended
instruction, and is tested across another executable build.

Everything beyond the small published corpus remains unexplored project work,
including:

- Event-flag manager/table location and representation.
- Mapping game events to Archipelago locations.
- Stable Bloodborne item identifiers and inventory semantics.
- Item-acquisition/grant function and calling convention.
- Persistence and save/reload behavior.
- Safe reconciliation after reconnect or restart.
- Cross-serial and cross-version support.

## Validated player HP structure behavior

On 2026-08-17, runtime breakpoint captures on `CUSA03173` 01.09 reproduced a
session-specific player structure in `RDI` at the published HP hook
`eboot + 0x1BFC5F7`. The pointer changed across emulator processes, as expected
for heap memory.

The following fields were exercised through guarded, expected-value-checked
writes with immediate read-back verification:

| Structure offset | Observed behavior | Evidence status |
| ---: | --- | --- |
| `+0xF8` | Current HP. Changed visibly from 486 to 500, restored to 486, and independently tracked damage/healing. | validated |
| `+0xFC` | Maximum-HP-related derived/cache field. A direct 594-to-590 write did not change the displayed maximum and was recalculated. | observed |
| `+0x100` | Candidate authoritative/effective maximum input. A 594-to-590 write eventually propagated 590 across all three maximum-related fields. | observed |
| `+0x104` | Previous/cached maximum used during HP reconciliation. Writing 594 to 590 left displayed maximum at 594, increased current HP by exactly four, and was then restored to 594 by the game. | validated behavior; semantic name inferred |

The controlled sequence ended with current HP 494 and all maximum-related fields
at 594. No address was frozen. BBLauncher automatic save backups were disabled
during the experiment.

## Live inventory quantity observation

On 2026-08-17, a Cheat Engine exact-value scan restricted to the observed
Bloodborne guest-memory range reduced the Quicksilver Bullet quantity from
73,087 initial matches to one candidate. The same address followed two ordinary
game decrements and one guarded write:

| Session address | Sequence | Evidence status |
| ---: | --- | --- |
| `0x208067BD8` | 19 → 18 (shot), 18 → 17 (shot), 17 → 18 (guarded write); the HUD displayed 18 after the write | observed live bullet quantity |

This is a session address, not yet a portable offset or pointer chain. Persistence
across emulator restart, save/reload behavior, surrounding inventory structure,
and applicability to other consumables remain unvalidated.

A data-write breakpoint on the bullet quantity captured the published consumable
hook at runtime `0x8014D955D`, with `RBX = 0x208067BD0`, the quantity at `RBX+8`,
and the post-decrement value 16 in `R12D`. A read-only neighborhood dump then
showed fixed-size 16-byte records:

| Entry | `+0` | `+4` item identifier | `+8` quantity | Interpretation |
| ---: | ---: | ---: | ---: | --- |
| `0x208067BD0` | `0xB0000384` | `0x40000384` | 16 | Quicksilver Bullets; validated by use and write |
| `0x208067BF0` | `0xB00003E8` | `0x400003E8` | 5 | Blood Vials; identity inferred from the known count |

Other populated records occur at 16-byte intervals. Their final dword varies and
is not yet semantically identified. The absent zero-count Pebble record supports
the concern that a 1-to-0 transition can remove or deactivate an entry rather
than provide a stable quantity address.

The dedicated inventory harness subsequently captured the live record pointer at
the exact quantity-write instruction `0x8014D9559`. Using that captured record as
an alignment anchor, a 16-byte-stride search resolved Bullets by item ID at
quantity 12 and Blood Vials by item ID at quantity 5 without hardcoded record
addresses. Its guarded command path then verified a Blood Vial write from 5 to 6.
This establishes dynamic lookup within the already-populated inventory block for
the current executable build; it does not yet implement insertion of absent items.

A direct call to the native inventory routine at `0x8014DA0A0` successfully added
one Blood Vial but crashed after returning because Cheat Engine invoked it on a
temporary remote thread; the write did not persist after restart. The same routine
was then queued through an in-image code cave at `0x8050DB800` and invoked at the
consumable updater's return point on Bloodborne's own gameplay thread. A guarded
existing-item test added one Vial (6 to 7), the triggering Bullet decremented
normally, and the game remained stable. This validates the native call and the
game-thread execution mechanism; absent-record insertion is the next test.

An initial absent-item test incorrectly inferred Goods ID `0x400007D0` (raw
descriptor `0xB00007D0`) to be Pebble. Runtime inspection of the inventory screen
showed that this ID is actually Augur of Ebrietas. The native insertion mechanism
worked and the game remained stable, but the semantic item-ID label was wrong;
Pebble remained at quantity one. This invalidates the earlier Pebble-insertion
claim and reinforces that item IDs must be captured from observed game behavior,
not inferred from numeric conventions. Pebble's actual ID remains to be captured.

A subsequent write-breakpoint capture while throwing the final Pebble observed
normalized item ID `0x400004CE` at quantity one. The earlier structure dump at the
same 16-byte-aligned record showed raw descriptor `0xB00004CE`, establishing the
raw/normalized pair directly. These are the corrected Pebble IDs.

Using that corrected descriptor, the game-thread native grant restored Pebble from
zero to one. The triggering Bullet decremented normally and the game remained
stable. Together with the earlier Augur of Ebrietas insertion, this validates both
an absent stackable consumable and an absent unique tool through the same native
item-grant path. The mistaken Augur label was an item-map error, not a failure of
the insertion mechanism.

After fully closing and relaunching shadPS4, both the granted Pebble and the
granted Augur of Ebrietas remained in inventory. This validates save persistence
for one absent stackable consumable and one absent unique tool granted through the
native game-thread path. The injected runtime hook itself is process-local and is
not expected to survive restart; the resulting inventory state did persist.

A reusable file-command harness was then installed in a fresh emulator process.
It accepted `GRANT raw-id normalized-id quantity expected-before tag`, queued the descriptor in the
validated in-image cave, retained the command until native completion, and logged
the result. A generic Pebble command changed the persisted quantity from one to
two; its trigger Bullet decremented normally, the game stayed stable, the native
routine returned slot/index value 79, and the command file was cleared only after
completion. The current version still requires a consumable action as its safe
game-thread trigger and does not yet eliminate the crash window between a native
grant and durable external acknowledgement.

An automatic heartbeat experiment showed that calling the native add routine
directly from an idle HUD callback returned `-1` even though the cached inventory
pointer was valid. Thread probes established that the HUD and consumable updater
both ran on the same OS thread, so the restriction was phase/re-entrancy related,
not thread identity. The working bridge has the idle heartbeat invoke a zero-delta
update on the existing Bullet slot. That enters the ordinary consumable updater;
at its validated return hook, the queued native grant executes in the accepted
context. A no-input Pebble test changed quantity two to three, did not consume a
Bullet, returned native slot/index 79, and left the game stable. After one
consumable use per emulator launch to cache the inventory pointer, later grants
therefore require no gameplay input.

Follow-up testing corrected the existing-stack strategy. The routine at
`0x8014D94A0` receives the expected inventory pointer, native slot, signed delta,
overflow pointer, and an item-metadata pointer in `R8`; genuine Bullet and Pebble
consumption passed delta `-1`. Positive delta calls returned without increasing the
stack, both re-entrantly and from a separate stamina callback. The `R8` pointer is
metadata (the Pebble target contained value 170), not the quantity address.

For an existing stack, the inventory-array scan resolves the actual record's
`+0x8` quantity field. A guarded direct Pebble write from one to two was immediately
visible in the inventory and remained two after a normal save and full emulator
restart. The consolidated harness therefore uses native `ItemGrant` only for an
absent record; for an existing record it verifies the expected-before quantity,
writes the exact wanted quantity, rereads it, and clears the durable command only
after successful verification. This is validated for Pebble but still needs broader
item-class and cap/overflow testing.

## First cross-serial reproduction: CUSA03173 01.09

## shadPS4 v0.18.0 regression

On 2026-08-18, BBLauncher updated the emulator from shadPS4 v0.17.0 to the
official v0.18.0 release while retaining v0.17.0 as a rollback build. The
installed `CUSA03173` 01.09 `eboot.bin` remained byte-identical (SHA-256
`d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9`).

With every BBLauncher patch disabled and Cheat Engine closed, a fresh character
still crashed immediately when struck by the Iosefka clinic wolf, reproducing
the v0.17.0 failure. Enabling only the Intel SFX workaround and fully restarting
the game made the same damage test stable. shadPS4 v0.18.0's experimental
Windows red-zone protection therefore does not replace that Bloodborne-specific
workaround on this machine.

`tables/SAFE-READ-ONLY-shad-0.18-regression.CT` records the next compatibility
layer without installing hooks: established guest hook prefixes, native routine
entries, and the three in-image cave/data regions used by the grant harness.

The first probe incorrectly treated `0x400000` as a fixed eboot address and could
not read the HP site. The live shad log showed that Windows had instead mapped
`eboot.bin` at `0x05700000` (process 28392). After changing the probe to resolve
the latest eboot `base_virtual_addr` from `shad_log.txt`, every checked site
matched its v0.17-relative bytes: HP, inventory quantity write, consumable return,
native item grant, native slot updater, idle heartbeat, and stamina. The three
established eboot-relative cave/data regions were also still readable and zeroed.
The complete capture is `work/shad-0.18-regression.txt`.

This establishes that the tested Bloodborne 01.09 RVAs and instruction signatures
survived the emulator update. What changed is shadPS4's guest placement contract:
v0.18 loads the eboot below 4 GiB at a launch-dependent address. Future tables and
the live backend must resolve the base for each process and add version-independent
Bloodborne RVAs; v0.17 absolute addresses such as `0x8014DA0A0` are no longer a
portable runtime binding.

The first relocated absent-Pebble grant exposed a second compatibility boundary.
Both the automatic idle trigger and a genuine Bullet-consumption trigger reached
native `ItemGrant`, but it returned `-1`; the cached inventory pointer and the
four descriptor words were correct. Windows guest red-zone static protection was
disabled, excluding that experimental mode. Under v0.17 the descriptor had lived
in the eboot cave above 4 GiB. Under v0.18 the relocated cave—and therefore the
descriptor pointer—was below 4 GiB. Rebuilding the identical descriptor on the
game thread stack made the next Bullet-triggered call succeed: the native result
was slot/index 79, Pebbles changed from zero to one, the game remained stable,
and the durable command was acknowledged and removed. The consolidated harness
now keeps request/result state in the relocatable cave but materializes the
descriptor on the stack for `ItemGrant`.

The existing-stack branch was then exercised in the same v0.18 process. A guarded
Pebble command required quantity one, resolved the canonical inventory record,
wrote quantity two at `0x208067C08`, reread two, acknowledged the command, and
removed it. Thus both delivery branches—native insertion for an absent record and
guarded quantity adjustment for an existing record—passed under v0.18.
After a full shadPS4 shutdown and relaunch of the same save, the inventory still
contained two Pebbles. This confirms durable save persistence for the combined
absent-then-existing delivery sequence on v0.18, not merely live-memory success.

On 2026-08-16, shadPS4 0.17.0 mapped the European `CUSA03173` 01.09 eboot at
`0x800000000`. Read-only process-memory inspection reproduced all six published
`CUSA00900` hook-site sequences at the same eboot-relative offsets. Sixteen bytes
were read at each site; the leading published original bytes and their observed
instruction tails matched.

This validates the recorded hook offsets across `CUSA00900` 01.09 and `CUSA03173`
01.09. It does not yet establish compatibility with other application versions or
all regional serials. The reproducible reader is `tools/read_hook_sites.ps1`; the
initial CE table is deliberately read-only.

## First validation sequence

1. Archive the exact source JSON/XML revisions and record their hashes and licenses.
2. Resolve shadPS4's exported `g_eboot_address` and verify the runtime image base.
3. Reproduce HP and Blood Echo observations at the published hook sites.
4. Inspect the full consumable detour before naming any inventory field.
5. Capture sufficient bytes around every hook and generate candidate AOB patterns.
6. Prove uniqueness within `CUSA00900` 01.09.
7. Test against a second serial or executable version before claiming portability.
8. Only then begin original event-flag and item-acquisition discovery.

## Evidence discipline

Every future address or semantic claim should be labelled as one of:

- `published`: reproduced from an attributed third-party source.
- `observed`: reproduced locally at runtime.
- `inferred`: supported by disassembly or structural analogy but not exercised.
- `validated`: reproduced across restart and the explicitly named builds.
- `hypothesis`: a lead requiring a falsifiable probe.

Do not promote a hook-site observation into a structure contract, or a hardcoded
address into a portable signature, without recording the validation evidence.
