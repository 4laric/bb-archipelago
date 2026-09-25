# Undead Giant and Bloodletting donor evidence

These experimental donors are available only through the direct chalice recipe
path. They are outside the reviewed main-boss assignment pool. The receiving
arena owns fog, entry, health lifecycle, music objects, death, rewards, and
progression. Static contract tests are not gameplay validation.

## Original actor witnesses

Read-only source: `CUSA03173/dvdroot_ps4/map/mapstudio/<group>/<map>.msb.dcx`
in the local 01.09 install. `BBEnemizerWriter --boss-actor-pins` produced:

| Donor | Map / Part / Entity | Model / NPC / AI | Part SHA256 | Initialization (`talk`, `unkT18`, `initAnim`, `damageAnim`) |
| --- | --- | --- | --- | --- |
| Undead Giant | `m29_01_13_08 / c3130_0000 / 2900100` | `c3130 / 10313090 / 313090` | `806103d444e88845ab17c11cbfe40661e9bed8c401b698ac0e23a406f8fb4156` | `0, -1, -1, -1` |
| Bloodletting Beast | `m29_05_00_08 / c5090_0000 / 2900102` | `c5090 / 10509006 / 509000` | `8ccf48f5ac082efc5a8abd06dacb5b45c1850a626d7c8ed457942642362b0592` | `0, 0, -1, -1` |
| Headless Bloodletting Beast | `m29_05_00_11 / c5090_0000 / 2900127` | `c5090 / 10509010 / 509010` | `981c9d429dc058a870a46b5e9fb58f37b420e5672f46852335b8cfef76171680` | `0, 0, -1, -1` |

The corresponding map SHA256 values are `d0a66852...cbac`,
`73a99214...54d2`, and `8529cea3...0c71`; full values live in the adapter.
NpcParam row `10509011` is a separate parasite-head actor and is excluded.
The two Bloodletting variants share one donor family, so only one may occur in
a seed.

## Constructor bindings

Each source map's EMEVD contains one `Event(0)` dispatch table. The handlers
are in the bundled `research/bb_inputs.db` entry `event/m29.emevd.dcx.js`.
The following calls are decoded from the read-only per-map binary EMEVD with
SoulsFormats; slot and argument order are retained here so the adapter can be
reproduced without distributing game source files.

| Donor map | Constructor calls bound to primary |
| --- | --- |
| `m29_01_13_08` | `slot0 12906810(2900100,2902110,2903110,2903111,12901800,12905520,12905510)`; `slot0 12906806(2900100,313000,12901800,12905500,12905520)`; `slot0 12906818(2900100,12901800,4.0,6.0)`; `slot0 12901690(2900100,2901100,2903100,12901800)`; `slot0 12901701(2900100,2902100,12901800,12905500,12900500,12900100)` |
| `m29_05_00_08` | `slot0 12904890(2900102,2903055,2903044,509000,12900520,12901802,929220,2901028)`; `slot2 12904882(12901802,12900520,2903047,2903046,2903048,2900102)`; `slot0 12904888(2900102)`; five limb calls `12904898/12904901/12904904/12904907/12904910` with part groups `1..5`, part IDs `5..9`, HP `100/170/170/220/220`; five `12904914` display-mask calls for effects `480..484` and `490..494`; `slot0 12904915(2900102)` cloth response |
| `m29_05_00_11` | `slot0 12904881(2900127,2903054,2903048,509010,12900554,12901800,2901045)`; `slot0 12904882(12901800,12900554,2903052,2903051,2903053,2900127)`; `slot0 12901588(2900127,2901045,2903048,12901800,2901046,2903049)` |

The headless map also has a different `c5090` actor, entity `2900128`.
That actor receives the limb calls in this map; entity `2900127` does not.
Copying the normal variant's limbs onto headless would therefore contradict
the original constructor.

The generic m29 music handlers `12906810` and `12904882` both use actor event
message `500` for phase music. Original engUS `item.msgbnd.dcx` NPC-name FMG
(SHA256 `1ddebc69611f6b6af01bed1970f4127148e9e86342ec7ec26d51fc1ceb289439`)
contains name IDs `313000` = “Undead Giant”, `509000` and `509010` =
“Bloodletting Beast”. The adapter changes only the destination health-bar
name operand to the selected donor ID.

`SpEffectParam` rows `480..484` are boss limb damage and `490..494` are
recovery. The normal Bloodletting source calls these exact rows. All three
selected chalice NpcParam rows have `GameClearSpEffectID=-1`; the existing
static tier inference therefore reports an explicit scaling skip rather than
assigning an unproven arena multiplier. Character assets and their SHA256
values are pinned in the adapter; the shared experimental character-effect
helper records direct TAE roots and staged bank bytes separately. Runtime
bank precedence and recursive FXR closure remain unobserved.

Reproduction (read-only inputs): use `BBEnemizerWriter --boss-actor-pins`
on each original MSB; decode each map-specific EMEVD `Event(0)` instruction
bank `2000`, ID `0` with SoulsFormats; compare its actor arguments above; run
`python -m unittest tests.test_chalice_giant_bloodletting_donors`. The test
reads bundled source data and never touches a game installation.
