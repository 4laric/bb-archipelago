# Bloodborne vertical slice

The slice now has one generation contract across all three pieces.

1. Generate a Bloodborne player with Archipelago. The world writes the usual
   multidata plus `*.bbenemizer.json`; both contain the same `enemizer_seed`.
2. Turn that request into the deterministic enemy plan:

   `python -m tools.bb_enemizer.cli --ap-request <request> --output work/enemizer/ap-plan.json`
3. Apply the plan with the guarded writer as documented in `ENEMIZER.md` and
   install its package-shaped map output.
4. Load `tables/Bloodborne-native-item-grant-auto-v2.CT`, then launch the
   Bloodborne Client installed with the apworld. It queues received items into
   the harness one at a time and advances its durable receipt only after the
   harness reports completion. The bridge uses the harness's `AUTO` expected
   count mode; the durable receipt remains the replay guard.
5. The six pickup acquisition-flag IDs are statically mapped, but the live
   flag-manager accessor is not yet validated, so checks remain manual. Use
   `/check <exact location name>` in the client; `/missing` lists the names.
   Successful manual checks are appended to `manual-checks.jsonl` in the client
   work directory with their UTC time, resolved name and ID, and world version.
   Misspelled names receive up to three nearby suggestions.

The manual check boundary is deliberate. Static flag IDs alone do not reveal
their live memory state. Generation, delivery, reconnect-safe receipts, and
enemizer seed identity are exercised end to end without inventing an accessor.
