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
        f"    $InitializeEvent({index}, {EVENT_ID}, {row.token_goods_id}, "
        f"{row.item_lot_id}, {row.ack_flag});"
        for index, row in enumerate(CATEGORY8_AWARDS)
    )
    text = text.replace(event_zero, f"{event_zero}\n    {MARKER}\n{initializers}", 1)
    body = f'''\n\n{MARKER}\n$Event({EVENT_ID}, Restart, function(itemId, itemLotId, eventFlagId) {{
    SetNetworkSyncState(Disabled);
    WaitFor(PlayerHasItem(ItemType.Goods, itemId));
    // Ack flags persist in the save. Clear a previous seed's acknowledgement
    // only after this delivery's token is visible, then publish the new ack
    // after the token has been consumed and the lot awarded.
    SetEventFlag(eventFlagId, OFF);
    WaitFixedTimeSeconds(1);
    RemoveItemFromPlayer(ItemType.Goods, itemId, 1);
    AwardItemLot(itemLotId);
    SetEventFlag(eventFlagId, ON);
    RestartEvent();
}});
'''
    return (text.rstrip() + body).encode("utf-8-sig")
