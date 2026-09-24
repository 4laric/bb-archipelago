# Gascoigne at Cleric Beast: grounded entry

## Defeat acknowledgement follow-up

The player subsequently reported killing the transformed beast with no defeat
banner and the fog still active. A read-only live probe found group 12990 absent:
the original phase flag 12990001 and terminal flag 12990004 cannot be stored.
The entry control 12411702 was true and completion 12411700 was false. This
explains why the terminal's wait on 12990004 cannot complete. Collision checks
and compilation had not tested runtime flag storage.

The four helper event IDs now use 12414780--12414783 in destination-native group
12414. All four resolved and read clear using the existing validated flag reader;
all are absent from original event operands and MSB actors. The adapter rejects
unsupported groups. See `gascoigne-flag-bank-readback.json` for the readback.
The session eboot base was 0x05630000, CUSA03173 01.09, shadPS4 0.18.0. No process
or save writes were used. Other experimental adapters using synthetic 1299x
flag groups require the same backing audit; this fix does not validate them.

The reported installed seed displayed an empty Father Gascoigne health bar with
no visible boss. Its compiled event 12411702 still warped actor 2410800 to
Cleric Beast's leap-origin region 2412831, then played Gascoigne animation 7001
instead of Cleric Beast animation 3028. The model-specific leap displacement
was lost while the leap-origin warp remained.

Original map evidence places the native combat actor at
(-123.5, -27.02, 65.7), while region 2412831 is approximately 18 units away at
(-107.49, -27.02, 73.6). This is a concrete entrance mismatch consistent with
the reported disappearance and rapid health loss; the precise runtime death
mechanism has not been observed.

The generated beast helper also inherited a source-arena offset: its position
was (-122.85982, -58.12, 68.91717), 31.1 units below the human. Its old phase
controller only disabled gravity, and its death could trigger the terminal even
before transformation. Ground-level placement and an explicit dormant lifecycle
remove this additional failure path.

The fix removes the leap-origin warp and guessed replacement animation, keeping
the native combat placement. The 110-frame leap delay becomes one frame.
Entry triggers, enable/gravity restoration, encounter flags, and progression
remain unchanged. The beast starts at the destination anchor, disabled with AI,
gravity and its health display off. Initialization protection is cleared before
the original referred-damage link is established, preserving forwarded combat
damage. Transformation warps it before enabling combat; phase-two reloads restore
it. Only an active beast phase can satisfy the beast-death terminal branch.

Validation:

- Eight Gascoigne contract tests pass, including regressions asserting the exact
  entry-only changes and preservation of trigger/restoration order.
- An original-input native build passes across all three Central Yharnam map
  states, with ten output files verified and no missing AI goals.
- The native writer harness passes, including 41 actor-transplant assertions.
  Destination-anchor placement is explicit; existing source-relative behavior
  remains the default, and unknown placement policies are rejected.
- The updated staged repair changes nine event bodies/IDs and
  the beast position in three map states. All other 249 binary event fingerprints
  and 6,172 other part fingerprints per map remain exact. The repair is not
  activated, and no save or running-game files were changed.

Installed input EMEVD SHA-256:
`5c2d08ae940c9571438bbb9ded6f9668570e1d23cc416d5b03f3e6c5ba6d3923`

Staged repaired EMEVD SHA-256:
`9ed97f11d78bff80534d788b9c8debf605224b8ee77df09b95dc8f3a1a7a452d`

An in-game retest is still required. The installed launcher package reports
revision dcd0ef36f170662d34edeab45847281fbcc129a3 with a dirty worktree; the
diagnosis uses its generated binary rather than assuming it equals that Git
revision or the newer boss-shuffle draft.
