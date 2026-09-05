#!/usr/bin/env python3
"""Add the table-driven category-8 token bridge to common.emevd (#214)."""

from __future__ import annotations

from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS


EVENT_ID = 98_000_000
MARKER = "// AP category-8 award bridge (#214)"


def patch(source: bytes) -> bytes:
    text = source.decode("utf-8-sig")
    if MARKER in text:
        raise ValueError("category-8 award bridge is already present")
    event_zero = "$Event(0, Default, function() {"
    if text.count(event_zero) != 1:
        raise ValueError("common constructor is absent or ambiguous")
    initializers = "\n".join(
        f"    $InitializeEvent(0, {EVENT_ID + index}, {row.token_goods_id}, "
        f"{row.item_lot_id}, {row.ack_flag});"
        for index, row in enumerate(CATEGORY8_AWARDS)
    )
    text = text.replace(event_zero, f"{event_zero}\n    {MARKER}\n{initializers}", 1)
    bodies = []
    for index, _row in enumerate(CATEGORY8_AWARDS):
        bodies.append(f'''$Event({EVENT_ID + index}, Restart, function(itemId, itemLotId, eventFlagId) {{
    SetNetworkSyncState(Disabled);
    // The token may have been routed to the storage box (#342), so look
    // there too; a boxed token must still fire this event.
    WaitFor(PlayerHasItemIncludingBBox(ItemType.Goods, itemId));
    // Ack flags persist in the save. Clear a previous seed's acknowledgement
    // only after this delivery's token is visible, then publish the new ack
    // after the token has been consumed and the lot awarded.
    SetEventFlag(eventFlagId, OFF);
    WaitFixedTimeSeconds(1);
L0:
    // Consume every copy of the token before awarding once: a re-granted
    // duplicate must not become a duplicate rune. If removal cannot reach
    // the box this spins without awarding until the player withdraws it.
    RemoveItemFromPlayer(ItemType.Goods, itemId, 1);
    WaitFixedTimeSeconds(1);
    GotoIf(L0, PlayerHasItemIncludingBBox(ItemType.Goods, itemId));
    AwardItemLot(itemLotId);
    SetEventFlag(eventFlagId, ON);
    RestartEvent();
}});''')
    return (text.rstrip() + f"\n\n{MARKER}\n" + "\n\n".join(bodies) + "\n").encode("utf-8-sig")
