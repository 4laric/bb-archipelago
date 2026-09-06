# Hemwick access gate

Status: statically mapped and covered by writer/lifecycle CI; live geometry and
collision acceptance remain outstanding.

New seeds place the synthetic progression item **Hemwick Access**. The client
delivers it through AP-owned event flag `12201898`, which has no reference in
the committed Bloodborne EMEVD corpus. Older request files have no
`hemwick_gate` member, so the launcher leaves both vanilla controllers intact.

The Cathedral-side boundary is object `2401995`, SFX `2403995`. In the
CUSA03173 01.09 MSB it is part `o240305_0001`, model `o240305`, described as
`霧壁_墓地街方面トンネル` (fog wall, Hemwick-direction tunnel), at
`(-29.97, 13.57, 323.72)`, rotation `(0, -20, 0)`, collision
`h000100_0000`. The source MSB SHA-256 is
`b3424d5134d239f04033f218f1023bfce2b9f92f5b2388361da0edcbdee11d6d`.
Its constructor initializes common event `7600` in slot 24.

The reciprocal Hemwick pair is object `2201999`, SFX `2203999`, part
`o220902`, at `(-152.91724, -15.007299, 469.61713)`, rotation
`(0, -45, 0)`. It is the map's sole common-event `7600` boundary initializer.

For a gated seed, the writer replaces only those two initializers with
map-local restart events. A wall is active while the access flag is off or
while the game is connecting/in multiplayer. It disappears immediately when
the flag becomes set in solo play, and reappears for normal multiplayer
confinement. Each state transition restarts the controller, so map reload,
death and Dream travel recompute from durable flag and multiplayer state.

The source mapping and the emitted instruction sequence do not prove that the
object's collision blocks every route. Live acceptance must still approach
from both sides, test edges, receive the item while loaded, reload/travel, and
exercise multiplayer connect/disconnect before this behavior is called
validated.
