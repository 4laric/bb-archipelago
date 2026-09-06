"""Audited Insight armor shop rows; see issue #377.

Only rows for attire present in the seed pool are removed. Row removal avoids
writing boss/quest/purchase flags or allocating a synthetic never-set flag.
"""
from .attire import ATTIRE_CATALOG

FAMILIES = (200000, 210000, 220000, 230000, 240000)
SETS = (
    (40, 5910, (130000, 131000, 132000, 133000)),
    (60, 5090, (40000, 41000, 42000, 43000)),
    (64, 5091, (210000, 211000, 212000, 213000)),
    (90, 6675, (370000, 371000, 372000, 373000)),
)

def build_insight_armor_suppression(pool_keys):
    eligible = {p.protector_id for p in ATTIRE_CATALOG if p.item_key in pool_keys}
    return [
        {"row_id": family + suffix + index, "equip_id": protector, "qwc_id": gate}
        for family in FAMILIES for suffix, gate, protectors in SETS
        for index, protector in enumerate(protectors) if protector in eligible
    ]
