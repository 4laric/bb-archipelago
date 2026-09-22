"""Pinned Rom combat package in Ebrietas' Upper Cathedral Ward arena.

This is an offline construction contract.  It preserves Ebrietas' terminal,
fog and co-op progression while transplanting Rom's core, thirty spiders and
two warp regions.  Runtime arena fit and combat behavior remain unobserved.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .boss_canary import event_blocks
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
ROM_SOURCE = "event/m32_00_00_00.emevd.dcx.js"
EBRIETAS_SOURCE = "event/m24_02_00_00.emevd.dcx.js"
ROM_STATES = ("m32_00_00_00", "m32_00_00_01")
EBRIETAS_STATES = ("m24_02_00_00", "m24_02_00_01")

ROM = 3200800
EBRIETAS = 2420800
EBRIETAS_OWNER = 2420801
ROM_ARCHETYPE = Archetype("c5100", 510000, 510000, 334233600)
EBRIETAS_ARCHETYPE = Archetype("c2510", 251000, 251000, 0)
SPIDER_ARCHETYPE = Archetype("c1400", 140010, 140010, 334233600)
OWNER_ARCHETYPE = Archetype("c9010", 251001, 1, 0)

PROJECT_EVENT_MIN, PROJECT_EVENT_MAX = 12991900, 12991999
SPIDER_ENTITIES = tuple(range(980100, 980130))
WARP_ENTITIES = (980130, 980131)

DONOR_HASHES = {
    0: "06d52948a0106e003bcf803c001e678e5eb87fc4be1c04a7ed2721522f2e54c7",
    13201800: "9cd2500de447eb5c5a4b5c7487e0f073653fb8f5e7f72ed3de3f00f148dd1fbf",
    13201802: "9ac690a52a2c21af5b5469de792caab012a501463ae8728261636b49e34fc444",
    13204000: "b656b38c1a7222ecff6418a0b44657163c08c99f3cbc0cd32ab533fc67729b89",
    13204050: "bf2e3255853fc04a81010a965c23afa2843084a47da2baebc46ef8f797d19bc4",
    13204730: "629b97cb1ad7b9f3f34d347c149aae14af0f0262aa779eee5172a16eec96f4eb",
    13204802: "5ad2891179d1d835dcce0749eb93e20077cea36fd218e2bc126265912499c61e",
    13204803: "5ef611fa7eea1582d3d5395d2f8507075aecc92fde3c1c23edcc77c092d9901d",
    13204804: "d4de375d4f13ffe206a977798943064e6b6069f5bf9f44743d87780ecb9bad9c",
    13204807: "a92a7d98eea9d8351bc1886c7d57d1f42b289965d4feaa907a78180bf6de5205",
    13204808: "002b06f501a776d5c0e4a15d0bb577f241c5a767eac73e44caf6ee990be850a6",
    13204809: "2a4be9a13d8f76efbeab63430ed9533767d15e47b33a05444d1c542c24ecd819",
    13204810: "da8c045a4a0e2c24443b6230d1175733c430174b85e9166c08860e0722b5e2c7",
}

# The installed CUSA03173 01.09 EMEVD has the same constructor and combat
# closure but a richer spider wake controller: gravity is disabled during the
# wait, white phantoms get a bounded timeout, rotation interpolates, and
# gravity is restored.  Keep the bundled research pin canonical and admit this
# exact source-witnessed body as an alternate.
DONOR_ALTERNATES = {
    13204000: "394560350b212592398f9a7173b3c2ecae548e334d9563b786179b2be3057b40",
}

ARENA_HASHES = {
    0: "cda0f114ad3f96b4b93fda3b81ac6d6ed5808bdb0be3f6d16e8225733e729dde",
    12421800: "7cb7c78833c5ef60a5599d35c22964e87b75f980c3165e139d7c28fc8a1bd34b",
    12421801: "2b01b305ae68b5d9e67407c316ed1a902f182124022987b9e258b527fb67f97f",
    12421802: "9bc79c8e55c2a2c9793a90070de1f76c35a46ebd98c2c79176b2fcc02ae8adc4",
    12421803: "dcbbafd95ebeebce5ddd63d637fc07b93bff8f52c33b77665e0ca21e6d649152",
    12424802: "effdc8bf4ca63c0371f209afbd388d0c682793bc2efaf258675e871bcae21ad2",
    12424803: "a487e349f0a416298a26fb93c87c0c57fd7211e7da3da8938d37b6e909130966",
    12424804: "9324596b40c1d5a8ec57a11c71eab66105a1550a81cdcacd4432a86ec366ea74",
    12424805: "e5cd1832606baf9b45afa6e5acb1f12c3e34cb52c26a86a687a0d65022f152eb",
    12424810: "593b24830019a78d0d17d10df4808d26d50b2ab3c2a0b07bff678974b28d5729",
    12424811: "2c98ff8ebff5a7fc0c83dcd11e62cd255e587b9de534d2868d3ef08047987618",
    12424870: "4fac0ea46041effd27d59b41752ef9758ba1c6021647ef9831f87de11e5564ba",
    12424871: "50091165e085e178edd4641859d7af08032e2dc4c1be99e7d3631ecbaa07abbc",
    12424980: "cebf5265578c05b598b8c2f9d2c524c852a32e48facb4856db1426185f098cb1",
    12424990: "0b8bf3929d610e3938673ca58072126cbde658e3aa75911c958a1b7e7f43a700",
}


@dataclass(frozen=True)
class RomEbrietasIds:
    phase: int = 12991900
    limb_part2: int = 12991901
    limb_part3: int = 12991902
    limb_part1: int = 12991903
    wave_enable: int = 12991904
    wave_cleanup: int = 12991905
    spider_target: int = 12991906
    owner_cleanup: int = 12991907
    wave_two_flag: int = 12991908
    wave_three_flag: int = 12991909
    evidence: str = (
        "Rom/Ebrietas allocation v1; full original EMEVD and MSB entity scan"
    )

    def values(self) -> tuple[int, ...]:
        return tuple(
            asdict(self)[name]
            for name in (
                "phase",
                "limb_part2",
                "limb_part3",
                "limb_part1",
                "wave_enable",
                "wave_cleanup",
                "spider_target",
                "owner_cleanup",
                "wave_two_flag",
                "wave_three_flag",
            )
        )

    def added_events(self) -> tuple[int, ...]:
        return self.values()[:8]


DEFAULT_IDS = RomEbrietasIds()


def _verify(
    text: str,
    pins: Mapping[int, str],
    role: str,
    alternates: Mapping[int, str] | None = None,
) -> dict[int, str]:
    blocks = event_blocks(text)
    for event_id, digest in pins.items():
        body = blocks.get(event_id)
        actual = "" if body is None else hashlib.sha256(body.encode()).hexdigest()
        allowed = {digest}
        alternate = (alternates or {}).get(event_id)
        if alternate is not None:
            allowed.add(alternate)
        if actual not in allowed:
            raise ValueError(f"unsupported original {role} event {event_id}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Rom/Ebrietas expected one {label}")
    return text.replace(old, new, 1)


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])", lambda m: str(values.get(int(m[0]), int(m[0]))), text
    )


def _end_event(block: str) -> str:
    header = block.splitlines()[0]
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda m: "function("
        + ", ".join("unused_" + x.strip() for x in m[1].split(",") if x.strip())
        + ")",
        header,
    )
    return header + "\n    EndEvent();\n});"


@cache
def _original_ids() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
        )
    rows = (
        read_prefix(BUNDLE, "mined/")
        .get("mined/msb_enemies.tsv", b"")
        .decode("utf-8-sig")
        .splitlines()[1:]
    )
    for row in rows:
        columns = row.split("\t")
        if len(columns) > 3 and columns[3].lstrip("-").isdigit():
            values.add(int(columns[3]))
    return values


def _validate_ids(ids: RomEbrietasIds, destination: str = "") -> None:
    values = ids.values()
    entities = SPIDER_ENTITIES + WARP_ENTITIES
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    original = _original_ids()
    if (
        len(set(values)) != len(values)
        or any(not PROJECT_EVENT_MIN <= value <= PROJECT_EVENT_MAX for value in values)
        or not ids.evidence.strip()
        or set(values).intersection(local | original)
        or len(set(entities)) != len(entities)
        or set(entities).intersection(local | original)
    ):
        raise ValueError(
            "Rom/Ebrietas IDs must be collision-free project-owned 129919xx/9801xx values"
        )


def _mapping(ids: RomEbrietasIds) -> dict[int, int]:
    result = {
        ROM: EBRIETAS,
        13201800: 12421800,
        13201802: 12421802,
        13204800: 12424800,
        13204801: 12424801,
        13204802: 12424802,
        13204803: 12424803,
        13204804: 12424804,
        13204807: ids.phase,
        13204808: ids.limb_part2,
        13204809: ids.limb_part3,
        13204810: ids.limb_part1,
        13204000: ids.wave_enable,
        13204050: ids.wave_cleanup,
        13204730: ids.spider_target,
        13204811: ids.wave_two_flag,
        13204812: ids.wave_three_flag,
        3202806: WARP_ENTITIES[0],
        3202807: WARP_ENTITIES[1],
        3203802: 2423802,
        3203803: 2423803,
        3202801: 2422802,
        3200010: 2420010,
    }
    result.update({3200200 + i: SPIDER_ENTITIES[i] for i in range(30)})
    return result


def _source_initializers(
    event_zero: str, event_ids: set[int], mapping: Mapping[int, int]
) -> list[str]:
    rows = [
        line
        for line in event_zero.splitlines()
        if any(
            re.search(r"\$InitializeEvent\([^,]+,\s*" + str(event) + r"(?:,|\))", line)
            for event in event_ids
        )
    ]
    expected = {
        13204807: 1,
        13204808: 1,
        13204809: 1,
        13204810: 1,
        13204000: 30,
        13204050: 30,
        13204730: 30,
    }
    for event, count in expected.items():
        actual = sum(
            bool(
                re.search(
                    r"\$InitializeEvent\([^,]+,\s*" + str(event) + r"(?:,|\))", row
                )
            )
            for row in rows
        )
        if actual != count:
            raise ValueError(
                f"Rom Event(0) lacks exact initializer closure for {event}"
            )
    return [_remap(row, mapping) for row in rows]


def patch_rom_at_ebrietas(
    destination: str, donor_source: str, ids: RomEbrietasIds = DEFAULT_IDS
) -> str:
    """Install the pinned Rom event closure while preserving Ebrietas progression."""
    donor = _verify(donor_source, DONOR_HASHES, "Rom donor", DONOR_ALTERNATES)
    original = _verify(destination, ARENA_HASHES, "Ebrietas arena")
    _validate_ids(ids, destination)
    mapping = _mapping(ids)

    activation = original[12421802]
    for line, label in (
        (
            "    ForceAnimationPlayback(2420800, 7001, true, false, false);\n",
            "Ebrietas sleep animation",
        ),
        (
            "    SetCharacterImmortality(2420800, Enabled);\n",
            "Ebrietas activation immortality",
        ),
        ("    SetSpEffect(2420800, 5647, false);\n", "Ebrietas activation effect"),
        (
            "    ForceAnimationPlayback(2420800, 7000, false, true, false);\n",
            "Ebrietas wake animation",
        ),
        (
            "    SetCharacterImmortality(2420800, Disabled);\n",
            "Ebrietas immortality release",
        ),
        ("    ClearSpEffect(2420800, 5647);\n", "Ebrietas effect release"),
    ):
        activation = _replace_once(activation, line, "", label)
    activation = _replace_once(
        activation,
        "            && CharacterType(10000, TargetType.Alive)\n            && HasDamageType(2420800, 10000, DamageType.Unspecified));",
        "            && CharacterType(10000, TargetType.Alive)\n            && HasDamageType(2420800, -1, DamageType.Unspecified));",
        "source-witnessed damage activation",
    )

    health = _remap(donor[13204802], mapping)
    health = _replace_once(
        health, "CreatePlaylog(124);", "CreatePlaylog(104);", "destination playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(2420010, 62, Enabled);",
        "StartTimeMeasurement(2420010, 40, Enabled);",
        "destination measurement",
    )
    music = _remap(donor[13204803], mapping)
    camera = _remap(donor[13204804], mapping).replace(
        "SetLockcamSlotNumber(32, 0,", "SetLockcamSlotNumber(24, 2,"
    )
    if camera.count("SetLockcamSlotNumber(24, 2,") != 2:
        raise ValueError("Rom/Ebrietas camera remap lost its two lockcam writes")
    phase = _remap(donor[13204807], mapping)

    limbs = []
    for event in (13204808, 13204809, 13204810):
        body = donor[event]
        if event in (13204808, 13204809):
            body = _replace_once(
                body,
                "    RequestCharacterAIReplan(2420800);\n",
                "",
                f"foreign replan literal in {event}",
            )
        limbs.append(_remap(body, mapping))
    wave_enable = _remap(donor[13204000], mapping)
    wave_cleanup = _remap(donor[13204050], mapping)
    wave_cleanup = _replace_once(
        wave_cleanup,
        "    WaitFor(EventFlag(eventFlagId) && CharacterDead(2420800));",
        "    WaitFor((EventFlag(eventFlagId) && CharacterDead(2420800)) || EventFlag(12421800));",
        "terminal-safe spider cleanup",
    )
    target = _remap(donor[13204730], mapping)

    calls = _source_initializers(
        donor[0],
        {13204807, 13204808, 13204809, 13204810, 13204000, 13204050, 13204730},
        mapping,
    )
    calls.append(f"    $InitializeEvent(0, {ids.owner_cleanup});")
    constructor = _replace_once(
        original[0],
        "    CreateBulletOwner(2420801);\n",
        "",
        "destination bullet owner initializer",
    )
    constructor = _replace_once(
        constructor,
        "    $InitializeEvent(0, 12424990);",
        "    $InitializeEvent(0, 12424990);\n" + "\n".join(calls),
        "constructor insertion anchor",
    )

    owner_cleanup = f"""$Event({ids.owner_cleanup}, Default, function() {{
    ChangeCharacterEnableState(2420801, Disabled);
    SetCharacterAIState(2420801, Disabled);
    SetCharacterHPBarDisplay(2420801, Disabled);
    WaitFor(EventFlag(12421800));
    ForceCharacterDeath(2420801, false);
}});"""
    edits = {
        0: constructor,
        12421802: activation,
        12424802: health,
        12424803: music,
        12424804: camera,
        12424870: _end_event(original[12424870]),
        12424871: _end_event(original[12424871]),
        12424980: _end_event(original[12424980]),
        12424990: _end_event(original[12424990]),
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join([phase, *limbs, wave_enable, wave_cleanup, target, owner_cleanup])
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(original).union(ids.added_events()):
        raise ValueError("Rom/Ebrietas patch changed event identities")
    for event_id, body in original.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Rom/Ebrietas patch changed unrelated event {event_id}")
    for event_id in (12421800, 12421801, 12421803, 12424805, 12424810, 12424811):
        if output[event_id] != original[event_id]:
            raise ValueError(
                f"Rom/Ebrietas changed protected progression event {event_id}"
            )
    copied = "\n".join(
        output[event]
        for event in (12424802, 12424803, 12424804, *ids.added_events()[:-1])
    )
    if re.search(r"(?<!\d)(?:132\d{5}|320(?:0[0-9]{3}|[1238][0-9]{3}))(?!\d)", copied):
        raise ValueError("Rom/Ebrietas copied combat body retains a donor-map literal")
    return result


ROM_CORE_PINS = {
    "m32_00_00_00": "29f3c43cd5ac4c5eafae8eaac6c2c600cb9d6f3aca95672bfd9d6bbff89249ac",
    "m32_00_00_01": "292a3d9644928b7fbbd5720fa41a53d0ae45e4ca5d92f1eadfbaecf91e770bcf",
}

ROM_SPIDER_PINS = {
    "m32_00_00_00": (
        "b1cc351822d32bf770f11cde996619a7ebf7d4de86cf6d566c90548ed206fe3c",
        "532741f598f0e9914e7f459c2e9eff91c718a2f2af36cdfc3f3f082d6ecc41d8",
        "2068ce091485e5cf2eaee9af8fd7b9f69545844704c72ee031ff3ca19aa6948c",
        "209a5b02a404322e088a653bee33c4db3f7cf19a8d90f6518a2e717ad3f8bdcc",
        "5e94afa859340cef2d29601c5a9b11365e232487391b2aa5a3ac720202ecc19f",
        "9fb73754ef455426d73b067b6ecb146a0a0d56c785358be944e0f7ba8d6879a0",
        "77cafa59a247c582bc4f704a57ef927ecddffb9ce360c928e60f802ffe73017c",
        "5037f40eb482148c422f925e89c868042d80cf30b23f761f913d7afb5e38e6b8",
        "34bd43d2da9202fe090aa08bac226ecc7055f0fe3a04201412fa9f4acb6927b0",
        "c56a9333f14bac353c5defccb0f25483ca3f00f304aff404735126ee80c76793",
        "1efd5a50e99ef69712baa1f947afdbdeb821c6248d5efe0f6206d5e28d38d89f",
        "407c05a2813ee3392b37c2fdc1dd10f1b47c6846fb26eec99a436c6ae4d87aed",
        "3fb45395c1a0bcef8584f14c139453422b7e15359bc0790eb5dab373f155b58c",
        "7a36394ecfa64b1b2e44166ec6cc86e2a3a47c426da1dbcaeac974994f45a03f",
        "d3dbce7d4f19f6293f0c1a2845c2e2688cdc2178e0d783c92f0b82612fc21e95",
        "a6867e5d2c8ee9c8c09aa03ea9c822315496b87498342b8b52187e17145ef38a",
        "550bc2ab163a4e13cdd02115fa05c98a6ec1f79ea08d3063f23ccdec0a28b684",
        "68bf63ec17f9c14d5fa0d90874058e5e8f65b2aa0cf3e56eb7fd80edef78362a",
        "f95fabc55431355c55de098fc80d36de3dad6f0b3731c1f258e6b772fcc55de3",
        "c46bd8f9cc6603e2e5e9312baf62bc59fcd0efe4a9208a0a7b8f09b0aa25bcde",
        "1c9e423c11ebd6080df92ee2868a3d0fe874435cbf9279cf50328cada0add579",
        "6039934e2d35c6bf993c449d6026504edf6f6066b23c54d07d74ac9dbed25e76",
        "3c2f019a62724d5a9a753213c77c8984b835d30da3dcb15534b071250f6280b7",
        "1d38359116f1192e735a2a9010546cb4b82269dfd0f6f8c621da8b049d5514d3",
        "481902648cfd00666f31961814974dd2419860485e99f424fe612989d826d308",
        "07b9a453486622ead6f71267c6616e383350a66c6375b59213928137c7641668",
        "bf0df3c2d983f62f452e949c721c16a823a6486becec99c558d1e001fc665941",
        "f8bb9fb86c5476411b7693e53674f3709db0261d03e0aae5bf03eb59d2d8c9aa",
        "9159a32c9b0890f10ce9dcc54f1550dc41d74249d5fa60f32b4449ae84cc3870",
        "6c731d18c11dc0b3dd9e914c3e6bfcce8236b579950a9219722b3ead45944592",
    ),
    "m32_00_00_01": (
        "0382cda786b97bb3dc294ab2c6f38212875a295928a1c1822256a63bdfd6b75a",
        "1e274331d44a73d7101e0b54de2ec67843887b07809da25d067ce000dea1bdd6",
        "82b7fd9210655e668ff52888a27eade8229131b6f0d4624fda8b0c6ddbef6838",
        "d4fd71c952904558cc98ee7d12f5efe3dbf53a03dda5d893c518997bd763318f",
        "3ededcdb1cd6fb166fcdfc4dd33344a2a26014ed47fa4f441f595e959997bcb9",
        "029754da54c7815b05b658cd68c599bdbaa23689e83a5e63c5bacff3a1d84efc",
        "eae83300fa75d2c198aa91171c8d13a8fbb1fee87136a6dcac81bbec628d76ff",
        "4243036794c6aebd6bbd7f26206ed9bc9dde8e57eede5eefea933f83dcf107dd",
        "89bc5c01b2f252161496f95a64e930af390734891d74aa3db2308521e837141f",
        "a3770d6b52593195e283ea29ac385041de6d4a7377912d1b113a240cf7233c6f",
        "c9c347772431b5f51f5805af79d9c8f93e979efd8e6bc399b9193a4053d65b1a",
        "e6f7df3de47d058f625b4f2eb3a9db3d94e2f06f5e5b3a7c6088bd82df8fbc9a",
        "9fd57538eb570068c9960ad8a2b0c9c3a74a35fe9cbe210545ce6cf986709e38",
        "10ad5d84fa2e0779718ea14ae766fab20d50c2d35b0b0a91d75219f5360464b0",
        "8e00b7a0ecb7ea0ada6b045437db80bf7aeccf434efbbd1652b66ba71fa00f73",
        "bff00737b51c73b69d898464c3f62f6732f33bc7b9e9999efed0dee84015d928",
        "558a7b72db1e553c0973e74e31f0c3ed181789e49cd7d6ebc05d654b422e83c1",
        "f3cd2b8f82b56bbe2a19c014d33e58301f4f17422028ed4606004ae4789cd01b",
        "c2704103fec909405a911b063ca4aa54e66e5abb370ae7c7b011d5cf8fd31017",
        "570b6b451245717014a33aca7acc288808707e3abc350390f5ba17adb15cec37",
        "ab15e0e018a08a879d69d0b5a03827492c20a998cd9c642c0186e089bbb74a60",
        "4e6b2fac8654f9139109b2df944f4bc36a1b1ee0a4a35bd6bbeb0f38206d8d70",
        "1d15cb4614a5d586927124c76dd4e58db15a5a019ccc94adc0e234c2b334b339",
        "bc9075601649538b5979d898e30cf10aae17dc63efe83f719b4645b803bc71f0",
        "291b861454035d9296b041fbf14d26dc19969e0ac1a958d8d4fc25eba7b6cfe5",
        "6efa6defd27c62b12e86a015dbe1a89c8fb7b6538c44b8bbba4b3ba2a7cb12d2",
        "dfa9b3d378ad52002ce68a2cfc481100977a6566ab6fa54fa0d25cfc754ad778",
        "c6d17c98ffdd482fb4ff598abee4d8bb1a74c2ad07b6608131495e0e0c292b4c",
        "cb21fd239c587545cfe39570304dd2dcbc8948b80063e096f8013aaaa11fb205",
        "4b7e09abc33d3270e050b8c6048abaf3795c1d6ad44d890f59dd54f0770ee8a1",
    ),
}

EBRIETAS_CORE_PINS = {
    "m24_02_00_00": "5f6ed3a557a24f54151a77bc3de15ce5f8d8645d6ad5cafc94fe4449b91ce5c2",
    "m24_02_00_01": "6e96e026cb750d840a621e27ec07658b9953c62b061c79ca8d5b95227c87dcbb",
}

EBRIETAS_OWNER_PINS = {
    "m24_02_00_00": "516a294ddc2d9dc00cb19bd820009708a0806839d9bbac2bb414c891f37c2700",
    "m24_02_00_01": "e217f5765025f189b9e252aed414b0e7f9981be85c337bc311b9daecf2c89108",
}

ROM_REGION_PINS = {
    "m32_00_00_00": (
        "dc415d225ad8b2614e88283cfc477228b7be19f88fe3502f6542749f81979401",
        "9cf570ef5c69c08610b30243dc82620aa618f62c2cdc4f506559ecc5bb3a75e2",
    ),
    "m32_00_00_01": (
        "afb4c5278c9290f51e175d089fd007d82abdc26cb175f1cd00d89048e23fd713",
        "af5073aecd6c4c1c202aa73e86804e2f1a15c9b8ec15818ca02f48651c06e838",
    ),
}


def _pin(sha256: str, *, anchor_sha256: str | None = None) -> dict:
    values = (sha256,) if anchor_sha256 is None else (sha256, anchor_sha256)
    if any(len(value) != 64 or re.search(r"[^0-9a-f]", value) for value in values):
        raise ValueError("Rom/Ebrietas native pins require lowercase SHA256 values")
    result = {"format": "bb-boss-actor-pin-v1", "part_sha256": sha256}
    if anchor_sha256 is not None:
        result["anchor_sha256"] = anchor_sha256
    return result


def _initialization() -> dict:
    return {"talk_id": 0, "unk_t18": -1, "init_anim_id": -1, "damage_anim_id": -1}


def _require(slots: Sequence[Slot], entity: int, archetype: Archetype) -> list[Slot]:
    rows = sorted(
        (slot for slot in slots if slot.entity_id == entity), key=lambda slot: slot.key
    )
    if not rows or any(
        slot.dummy or slot.talk_id or slot.archetype != archetype for slot in rows
    ):
        raise ValueError(f"unsupported Rom/Ebrietas placement provenance for {entity}")
    return rows


def native_plan_rom_at_ebrietas(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: RomEbrietasIds = DEFAULT_IDS,
) -> dict:
    """Return the two-state primary swap, 60 spider clones and four warp regions."""
    _verify(
        read_blob(BUNDLE, ROM_SOURCE).decode("utf-8-sig"),
        DONOR_HASHES,
        "Rom donor",
        DONOR_ALTERNATES,
    )
    bundled_arena = read_blob(BUNDLE, EBRIETAS_SOURCE).decode("utf-8-sig")
    _verify(bundled_arena, ARENA_HASHES, "Ebrietas arena")
    _validate_ids(ids, bundled_arena)

    destinations = _require(slots, EBRIETAS, EBRIETAS_ARCHETYPE)
    owners = _require(slots, EBRIETAS_OWNER, OWNER_ARCHETYPE)
    cores = _require(slots, ROM, ROM_ARCHETYPE)
    spiders = {
        3200200 + i: _require(slots, 3200200 + i, SPIDER_ARCHETYPE) for i in range(30)
    }
    if (
        len(destinations) != 2
        or {x.map_name for x in destinations} != set(EBRIETAS_STATES)
        or len(owners) != 2
        or {x.map_name for x in owners} != set(EBRIETAS_STATES)
        or len(cores) != 2
        or {x.map_name for x in cores} != set(ROM_STATES)
        or any(
            len(rows) != 2 or {x.map_name for x in rows} != set(ROM_STATES)
            for rows in spiders.values()
        )
    ):
        raise ValueError(
            "Rom/Ebrietas requires the exact two-state 31-actor donor and destination owner roster"
        )

    destination_by_state = {slot.map_name: slot for slot in destinations}
    core_by_state = {slot.map_name: slot for slot in cores}
    source = core_by_state[ROM_STATES[0]]
    swap = Swap(
        destinations[0].logical_key,
        [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations},
        EBRIETAS_ARCHETYPE,
        ROM_ARCHETYPE,
        warnings=[
            "experimental Rom-at-Ebrietas contract; runtime arena, warp and AP behavior require validation"
        ],
        destinations={
            slot.key: {
                "map_name": slot.map_name,
                "entity_id": slot.entity_id,
                "x": slot.x,
                "y": slot.y,
                "z": slot.z,
            }
            for slot in destinations
        },
    )
    changes, skips = plan_scaling(
        [swap], list(destinations), dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError(
            "Rom/Ebrietas primary swap has an ambiguous normalization plan"
        )

    additions: list[dict] = []
    bindings: list[dict] = []
    regions: list[dict] = []
    for destination_state in EBRIETAS_STATES:
        source_state = ROM_STATES[EBRIETAS_STATES.index(destination_state)]
        destination = destination_by_state[destination_state]
        core = core_by_state[source_state]
        bindings.append(
            {
                "source_map": source_state,
                "source_part": core.part_name,
                "source_entity_id": ROM,
                "source_archetype": asdict(ROM_ARCHETYPE),
                "source_provenance": _pin(ROM_CORE_PINS[source_state]),
                "source_initialization": _initialization(),
                "destination_map": destination_state,
                "destination_part": destination.part_name,
                "destination_entity_id": EBRIETAS,
            }
        )
        source_spiders = {
            row.entity_id: row
            for rows in spiders.values()
            for row in rows
            if row.map_name == source_state
        }
        for index in range(30):
            source_entity = 3200200 + index
            source_spider = source_spiders[source_entity]
            additions.append(
                {
                    "source_map": source_state,
                    "source_part": source_spider.part_name,
                    "source_anchor_part": core.part_name,
                    "source_entity_id": source_entity,
                    "source_archetype": asdict(SPIDER_ARCHETYPE),
                    "source_part_kind": "enemy",
                    "source_provenance": _pin(
                        ROM_SPIDER_PINS[source_state][index],
                        anchor_sha256=ROM_CORE_PINS[source_state],
                    ),
                    "source_initialization": _initialization(),
                    "destination_map": destination_state,
                    "destination_anchor_part": destination.part_name,
                    "destination_part": f"ap_rom_spider_{index:02d}",
                    "destination_entity_id": SPIDER_ENTITIES[index],
                    "allocation_evidence": ids.evidence,
                }
            )
        for index, (source_region, destination_region, entity) in enumerate(
            zip(
                ("Event_白痴の蜘蛛_ワープ先00", "Event_白痴の蜘蛛_ワープ先01"),
                ("ap_rom_warp_00", "ap_rom_warp_01"),
                WARP_ENTITIES,
            )
        ):
            regions.append(
                {
                    "source_map": source_state,
                    "source_region": source_region,
                    "source_entity_id": 3202806 + index,
                    "source_provenance": {
                        "format": "bb-boss-region-pin-v1",
                        "region_sha256": ROM_REGION_PINS[source_state][index],
                    },
                    "source_anchor_part": core.part_name,
                    "source_anchor_provenance": _pin(ROM_CORE_PINS[source_state]),
                    "destination_map": destination_state,
                    "destination_region": destination_region,
                    "destination_entity_id": entity,
                    "destination_anchor_part": destination.part_name,
                    "destination_anchor_provenance": _pin(
                        EBRIETAS_CORE_PINS[destination_state]
                    ),
                }
            )

    retained = []
    for owner in owners:
        retained.append(
            {
                "map": owner.map_name,
                "part": owner.part_name,
                "entity_id": owner.entity_id,
                "archetype": asdict(owner.archetype),
                "source_provenance": _pin(EBRIETAS_OWNER_PINS[owner.map_name]),
                "source_initialization": _initialization(),
                "policy": "retain_native_part_disabled_alive_until_destination_completion",
            }
        )
    requirements = [
        {
            "destination_map": row["destination_map"],
            "destination_part": row["destination_part"],
            "parent_logical_key": swap.logical_key,
            "source_npc_param_id": SPIDER_ARCHETYPE.npc_param_id,
            "strategy": "allocate_distinct_verified_helper_clone",
        }
        for row in additions
    ]

    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "ebrietas<-rom"},
        "boss_contract": {
            "format": "bb-rom-ebrietas-contract-v1",
            "arena": "ebrietas",
            "donor": "rom",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(DONOR_HASHES),
            "source_hash_alternates": dict(DONOR_ALTERNATES),
            "arena_hash_pins": dict(ARENA_HASHES),
            "preserved_destination_events": [
                12421800,
                12421801,
                12421803,
                12424805,
                12424810,
                12424811,
            ],
            "retained_destination_helpers": retained,
            "source_roster": {
                "core": ROM,
                "spiders": list(range(3200200, 3200230)),
                "map_states": list(ROM_STATES),
                "generators": [],
            },
            "source_actor_event_closure": {
                "13201802": "damage activation semantics adapted into destination activation",
                "13204802": "health, co-op scaling and combat start copied",
                "13204803": "music controller copied onto destination sounds and region",
                "13204804": "camera controller copied onto destination lockcam",
                "13204807": "two HP phase warps copied with pinned regions",
                "13204808": "Part2 controller copied; foreign destination replan removed",
                "13204809": "Part3 controller copied verbatim except foreign destination replan",
                "13204810": "Part1 controller copied",
                "13204000": "all thirty parameterized spider activation slots copied",
                "13204050": "all thirty cleanup slots copied with destination-terminal escape",
                "13204730": "all thirty target bindings copied",
            },
            "foreign_literal_policy": {
                "literal": 2420800,
                "events": [13204808, 13204809],
                "evidence": "entity absent from both pinned Rom source maps",
                "action": "remove exact RequestCharacterAIReplan calls before remapping",
            },
            "region_transform_policy": "native anchor-relative transform; MSBB yaw is degrees",
        },
        "boss_actor_additions": additions,
        "boss_region_additions": regions,
        "primary_init_source_bindings": bindings,
        "boss_actor_scaling_requirements": requirements,
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }


def rom_helper_scaling_parents(plan: Mapping) -> dict[tuple[str, str], str]:
    """Shape Rom spider requirements for allocate_actor_scaling after combining."""
    rows = plan.get("boss_actor_scaling_requirements", ())
    result = {
        (row["destination_map"], row["destination_part"]): row["parent_logical_key"]
        for row in rows
    }
    if len(result) != len(rows):
        raise ValueError("duplicate Rom helper scaling destination")
    return result


# The shorter spelling matches the earlier standalone helper contracts; keep
# both public names so builder integration can use the donor-specific one.
helper_scaling_parents = rom_helper_scaling_parents
