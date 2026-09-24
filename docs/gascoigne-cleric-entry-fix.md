# Gascoigne at Cleric Beast: grounded entry

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

The fix removes the leap-origin warp and guessed replacement animation, keeping
the native combat placement. The 110-frame leap delay becomes one frame.
Entry triggers, enable/gravity restoration, encounter flags, and progression
remain unchanged. Neither form's combat, health link, nor terminal is changed.

Validation:

- Six Gascoigne contract tests pass, including a regression asserting the exact
  entry-only changes and preservation of trigger/restoration order.
- An original-input native build passes across all three Central Yharnam map
  states, with ten output files verified and no missing AI goals.
- A staged repair for the user's existing seed changes only event 12411702;
  all other 257 binary event fingerprints remain exact. The repair is not
  activated, and no save or running-game files were changed.

Installed input EMEVD SHA-256:
`5c2d08ae940c9571438bbb9ded6f9668570e1d23cc416d5b03f3e6c5ba6d3923`

Staged repaired EMEVD SHA-256:
`f453ff32e87f5f529f40789c7a39db0f66afd4c5235ae970f3608e830e858a34`

An in-game retest is still required. The installed launcher package reports
revision dcd0ef36f170662d34edeab45847281fbcc129a3 with a dirty worktree; the
diagnosis uses its generated binary rather than assuming it equals that Git
revision or the newer boss-shuffle draft.
