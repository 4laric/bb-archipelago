"""Pinned removal of Winter Lantern frenzy helpers and donor-specific AI switches."""
import hashlib
from .boss_canary import event_blocks

CALLEES = {'m26_00_00_00': {12605200: '358745e3546d38436d8fed5e843f06c3f37a4e83279e85659b69225d6080ab42'},
 'm33_00_00_00': {13305030: 'b76dc3d726752614a75c5692ef3d6ec954970e2572494502644a9f99e5147e27'},
 'm36_00_00_00': {13605600: 'bde3ca42df69901045a76f0360f3bc4a27ca521c1d37a894fc1fe37d586f7aa5',
                  13605540: '626bff0f919d46415b1694124454730acdf896c79f55f6c70749d895efadbd7d'}}
INITIALIZERS = {'m26_00_00_00': ['$InitializeEvent(0, 12605200, 2600300, 2600310);',
                  '$InitializeEvent(1, 12605200, 2600301, 2600311);',
                  '$InitializeEvent(2, 12605200, 2600302, 2600312);',
                  '$InitializeEvent(3, 12605200, 2600303, 2600313);'],
 'm33_00_00_00': ['$InitializeEvent(0, 13305030, 3300500, 3300520);',
                  '$InitializeEvent(1, 13305030, 3300501, 3300521);',
                  '$InitializeEvent(2, 13305030, 3300502, 3300522);'],
 'm36_00_00_00': ['$InitializeEvent(0, 13605600, 3600500, 3600510);',
                  '$InitializeEvent(1, 13605600, 3600501, 3600511);',
                  '$InitializeEvent(2, 13605540, 3600500, 3602470, 4, 256901, 256900);',
                  '$InitializeEvent(3, 13605540, 3600501, 3602470, 4, 256901, 256900);']}
HELPERS = {'m26_00_00_00': [2600310, 2600311, 2600312, 2600313],
 'm33_00_00_00': [3300520, 3300521, 3300522],
 'm36_00_00_00': [3600510, 3600511]}


def patch_winter_lanterns(map_name: str, source: str) -> str:
    source = source.replace("\r\n", "\n")
    blocks = event_blocks(source)
    for event_id, digest in CALLEES[map_name].items():
        if hashlib.sha256(blocks.get(event_id, "").encode()).hexdigest() != digest:
            raise ValueError(f"unsupported Winter Lantern helper event {event_id}")
    zero = blocks[0]
    disables = "".join(f"    ChangeCharacterEnableState({helper}, Disabled);\n"
                       f"    SetCharacterBackreadState({helper}, true);\n"
                       for helper in HELPERS[map_name])
    for index, initializer in enumerate(INITIALIZERS[map_name]):
        line = "    " + initializer + "\n"
        if zero.count(line) != 1:
            raise ValueError(f"Winter Lantern initializer differs: {initializer}")
        # Keep helper teardown at its own constructor site, away from boss
        # readiness resets and donor initialization insertions.
        zero = zero.replace(line, disables if index == 0 else "")
    return source.replace(blocks[0], zero, 1)
