# Passive held-inventory bootstrap

Status: live bootstrap, delivery, and cold-restart validation on 2026-09-22
Target: CUSA03173 AppVer 01.09, original `eboot.bin`
SHA-256: `d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9`

The native client can locate held inventory and deliver items without a
consumable action. This record covers the pointer source, guarded heartbeat,
and live delivery evidence for the supported build.

## Static source

For this SELF, an eboot RVA maps to file offset `RVA + 0x28EB0`. The following
instructions were disassembled from the original file:

| File offset | eboot RVA | Relevant instructions |
| ---: | ---: | --- |
| `0x17F47D2` | `+0x17CB922` | `lea rax,[rip+...]` to file `0x5563FE0`; `mov rax,[rax]`; `mov rbx,[rax+0x8]` |
| `0x17F4A08` | `+0x17CBB58` | `lea rdi,[rbx+0x328]` before a game inventory routine |

The global itself is file `0x5563FE0`, or eboot `+0x553B130`. The resulting
candidate chain is:

```text
root      = read_u64(eboot_base + 0x553B130)
player    = read_u64(root + 0x08)
inventory = player + 0x328
```

The global load and `+0x328` inventory argument establish the chain in the
target build. They do not by themselves establish that every game phase has a
live player or a readable held-inventory block.

## Live read-only evidence

In the user session, reading that corrected chain without a consumable action
produced inventory `0x208067778`. It passed the held-mode check
`inventory[0x8C] == 0`, had `split == 64` and `last == 90`, and its Bullet
record was slot 79 with quantity 17, matching the game HUD. No inventory page
was written and no item was consumed.

The 190-byte heartbeat payload was then installed with the existing suspended
thread protocol. Its live bytes matched the assembler. Before any player
consumption, the cache held `0x208067778`; clearing that eboot cache cell caused
the next heartbeat to reacquire the same inventory automatically.

An existing-stack request with delta zero completed with Bullet quantity
remaining 17. An absent-stack Pebble request then completed at native slot 91;
read-back confirmed one Pebble, 17 Bullets, and no Blood Vial record. No player
consumption was used to start either request. Only the Pebble test intentionally
added an item; the bootstrap itself changed no inventory quantities.

The user confirmed the Pebble in-game, restarted shadPS4, and confirmed it
persisted. The fresh process relocated eboot from `0x57C0000` to `0x5820000`;
both source signature checks passed. With no consumption in the new process,
the heartbeat reacquired held inventory and an existing-stack grant increased
Pebbles from one to two. Read-back again showed 17 Bullets and no Blood Vial
record, with the request retired and native completion witnessed.

## Bootstrap contract and limits

The bootstrap path runs on the existing game-thread heartbeat. Each heartbeat
re-derives the candidate from the static player source, then accepts it only
when it is present, held mode is zero, and the normal inventory geometry is
valid. When the heartbeat runs, it clears the cache if the chain is absent,
storage-mode, or geometrically invalid. This both avoids a stale character pointer and lets
ordinary client polling distinguish initialization from a delivery failure.

The heartbeat does not mutate an inventory record and does not call an item
grant or quantity routine to discover the pointer. It needs no additional
hook or ABI. The only state it updates is the existing eboot cache cell, which
is in the executable image rather than a protection-tracked inventory page.

Once a request is queued, the heartbeat calls the quantity routine with slot
`0xFFFFFFFF` and delta zero. Its unsigned bounds check immediately returns
through the existing consume hook, where delivery runs. This requires neither
a Bullet record nor another consumable. The native function's real bytes were
executed in Unicorn against the hash-matched executable: empty and populated
inventory bounds all reached the consume hook in 22 instructions, with no
inventory writes or nested calls. Reproduce this without redistributing game
code using `python -m tools.check_bootstrap_native_cpu <local-eboot.bin>`.

Remaining validation limits:

1. Verify the selected object across loading, menu transitions, death, and
   character/save reload, including cache clearing and reacquisition.
2. The live checks used the native developer harness, not a connected AP
   multiworld. Ledger/retry behavior is covered by client tests; a full
   end-to-end AP session is still a useful release check.

CI should pin the source metadata and exercise null root/player, storage mode,
invalid geometry, and a valid held chain. It should assert that rejected
candidates clear or leave the cache unusable and that no inventory-page write
is attempted.
