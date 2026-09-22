"""Pinned single-actor Laurence (3400850) combat adapter."""
from __future__ import annotations
import hashlib,re
from dataclasses import dataclass
from typing import Mapping
from .boss_canary import event_blocks,parse_events
from .model import Archetype,Swap
from .scaling import plan_scaling
from .boss_contracts import CLERIC_ARENA
LAURENCE=3400850; CLERIC=2410800
PINS={0:"3772e9c2957d38bcdbc984631dab0033deaef57c1d092a8c77005cdd4d7c1d55",13404852:"a55956b498c3908a0febf99daf2013e6d59eea5885a5ac837a3735f09d356470",13404853:"6d373eb2995d299bd4008cbc5c7fa72a0d77823ed62129af6916a4ad0235ce7a",13404854:"67283d0f1600a008235ffc109219ab98ee5028814738d45724c397bf4519430f",13404870:"237a55077776ca3b72ea95aee40b8da9655bf8f93d15315400b3d1f1eb8471be",13404875:"e5fb7120dd1c7759f763c39f7c04a1b01ba966dcb2ce48f9bc4f5e1331a57822",13401851:"c9bb7c19e16ebdc391bc1552e9328dd41d25bdc968701b2e1182506f940f255d"}
@dataclass(frozen=True)
class LaurenceIds: limbs:int; hitmask:int
def _rep(src,edits):
 lines=src.splitlines()
 for e in reversed(parse_events(src)):
  if e.event_id in edits: lines[e.first_line-1:e.last_line]=edits[e.event_id].splitlines()
 return "\n".join(lines)+"\n"
def patch_laurence_at_cleric(dest,donor,ids):
 d,s=event_blocks(dest),event_blocks(donor)
 from .maria_contract import _verify
 _verify(d, CLERIC_ARENA.expected, 'Cleric arena')
 for i,h in PINS.items():
  if hashlib.sha256(s[i].encode()).hexdigest()!=h: raise ValueError(f"unsupported Laurence source event {i}")
 if len({ids.limbs,ids.hitmask})!=2 or min(ids.limbs,ids.hitmask)<=0 or any(x in {int(n) for n in re.findall(r"(?<![\w])-?\d+(?![\w])",dest)} for x in (ids.limbs,ids.hitmask)): raise ValueError("Laurence allocation collides")
 calls=[x for x in s[0].splitlines() if re.search(r"\$InitializeEvent\([^,]+,\s*13404870,",x)]
 if len(calls)!=5 or s[0].count("$InitializeEvent(0, 13404875);")!=1: raise ValueError("Laurence Event0 initializer witness drift")
 init=d[0].replace("    $InitializeEvent(0, 12414708);","    $InitializeEvent(0, 12414708);\n"+"\n".join(x.replace("13404870",str(ids.limbs),1) for x in calls)+f"\n    $InitializeEvent(0, {ids.hitmask});",1)
 activation=d[12411702].replace('ForceAnimationPlayback(2410800, 3028, false, false, false);','ForceAnimationPlayback(2410800, 3029, false, false, false);',1)
 health=d[12414702].replace("500000","450000",1)
 music=d[12414703].replace("CharacterHasEventMessage(2410800, 100)","CharacterHasEventMessage(2410800, 400)",1)
 camera=s[13404854].replace("3400850","2410800").replace("13401850","12411700").replace("SetLockcamSlotNumber(34, 0,","SetLockcamSlotNumber(24, 1,").replace("$Event(13404854,","$Event(12414704,")
 rem=lambda b,old,new: re.sub(r"(?<![\w])-?\d+(?![\w])",lambda m:str({LAURENCE:CLERIC,13401850:12411700,old:new}.get(int(m[0]),int(m[0]))),b).replace(f"$Event({old},",f"$Event({new},")
 def no(b):
  h=b[:b.index('{')]
  h=re.sub(r'function\(([^)]*)\)',lambda m:'function('+', '.join('unused_'+x.strip() for x in m.group(1).split(',') if x.strip())+')',h)
  return h+'{\n    EndEvent();\n});'
 out=_rep(dest,{0:init,12411702:activation,12414702:health,12414703:music,12414704:camera,12414707:no(d[12414707]),12414708:no(d[12414708]),12414710:no(d[12414710]),12414720:no(d[12414720])}).rstrip()+"\n\n"+rem(s[13404870],13404870,ids.limbs)+"\n\n"+rem(s[13404875],13404875,ids.hitmask)+"\n"
 if event_blocks(out)[12411700]!=d[12411700]: raise ValueError("destination terminal changed")
 return out


def native_plan_laurence_at_cleric(slots,npcs,effects,ids,seed):
 cleric=[x for x in slots if x.entity_id==CLERIC and x.archetype==Archetype('c5000',500241,500241,0)]
 donor=[x for x in slots if x.entity_id==LAURENCE and x.archetype==Archetype('c4500',450000,450000,0)]
 if len(cleric)!=3 or len(donor)!=1 or any(x.talk_id or x.archetype.chara_init_id for x in cleric): raise ValueError('requires three exact Cleric states and Laurence3400850')
 if {x.map_name for x in cleric}!={'m24_01_00_00','m24_01_00_01','m24_01_00_11'} or donor[0].map_name!='m34_00_00_00': raise ValueError('Laurence map-state provenance differs')
 a,d=cleric[0],donor[0];sw=Swap(a.logical_key,[x.key for x in cleric],{x.key:x.archetype for x in cleric},a.archetype,d.archetype,destinations={x.key:{'map_name':x.map_name,'entity_id':x.entity_id,'x':x.x,'y':x.y,'z':x.z} for x in cleric});c,k=plan_scaling([sw],cleric,dict(npcs),dict(effects), boss_tiers=True)
 binds=[{'source_map':d.map_name,'source_part':d.part_name,'source_entity_id':d.entity_id,'source_archetype':{'model_name':'c4500','npc_param_id':450000,'think_param_id':450000,'chara_init_id':0},'source_talk_id':d.talk_id,'destination_map':x.map_name,'destination_part':x.part_name,'destination_entity_id':x.entity_id,'required_native_fields':['talk_id','unk_t18','init_anim_id','damage_anim_id','provenance']} for x in cleric]
 return {'format':'bb-enemizer-plan-v2','dry_run':True,'seed':seed,'swap_count':1,'swaps':[sw.json()],'boss_contract':{'format':'bb-laurence-contract-v1','arena':'cleric-beast','donor':'laurence','event_ids':{'limbs':ids.limbs,'hitmask':ids.hitmask},'arena_hash_pins':CLERIC_ARENA.expected,'donor_hash_pins':PINS},'primary_init_source_bindings':binds,'scaling':{'enabled':bool(c),'mechanism':'inferred_static_npc_clone_sp_effect','change_count':len(c),'changes':[x.json() for x in c],'skip_count':len(k),'skips':k}}
