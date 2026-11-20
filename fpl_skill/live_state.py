"""Fail-closed live-state provenance, freshness, chip and lineup contracts."""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Iterable, Mapping, Optional, Sequence

class ExecutionDenied(RuntimeError):
    """Raised whenever an account mutation is attempted while execution is held."""

class FixtureStatus(str, Enum):
    FIXTURE_NOT_PUBLISHED="FIXTURE_NOT_PUBLISHED"
    BLANK="BLANK"
    FIXTURE_MISSING="FIXTURE_MISSING"
    POSTPONED="POSTPONED"
    UNKNOWN="UNKNOWN"
    CONFLICTED="CONFLICTED"

@dataclass(frozen=True)
class RetrievalRecord:
    event_id:int
    team_id:int
    endpoint:str
    retrieved_at:Optional[datetime]
    observed_at:datetime
    payload:bytes
    source:str
    upstream:str="fpl-api"
    @property
    def payload_hash(self)->str:
        return sha256(self.payload).hexdigest()

@dataclass(frozen=True)
class FixtureSchedule:
    event_id:int
    team_id:int
    fixtures:Sequence[Mapping[str,Any]]
    published:bool
    complete:bool
    retrieval:RetrievalRecord
    postponed:bool=False
    conflicted:bool=False

def classify_fixture_schedule(s:FixtureSchedule)->FixtureStatus:
    if s.conflicted: return FixtureStatus.CONFLICTED
    if not s.published: return FixtureStatus.FIXTURE_NOT_PUBLISHED
    ids=[x.get("id") for x in s.fixtures]
    if not s.complete or any(x is None for x in ids): return FixtureStatus.FIXTURE_MISSING
    if len(ids)!=len(set(ids)): return FixtureStatus.UNKNOWN
    if s.postponed: return FixtureStatus.POSTPONED
    if not s.fixtures: return FixtureStatus.BLANK
    return FixtureStatus.UNKNOWN

def retrieval_state(record:RetrievalRecord,*,now:datetime,live_gameweek:bool)->str:
    if record.retrieved_at is None: raise ValueError("retrieved_at is required")
    ttl=300 if live_gameweek else 3600
    age=(now-record.retrieved_at).total_seconds()
    if age<0 or age>ttl:return "STALE"
    return "VERIFIED_CURRENT"

def providers_are_independent(source_a:str,source_b:str,upstream_a:str,upstream_b:Optional[str]=None)->bool:
    upb=upstream_b if upstream_b is not None else upstream_a
    if source_a==source_b or upstream_a==upb:return False
    return True

@dataclass(frozen=True)
class ChipState:
    available_h1:set[str]
    available_h2:set[str]
    used_h1:set[str]
    h2_activated_gw:int=20

@dataclass(frozen=True)
class FreeHitRestoration:
    squad:tuple[int,...]
    bank:int
    free_transfers:int

def reconcile_free_hit(*,pre_squad:Sequence[int],temporary_squad:Sequence[int],pre_bank:int,
                       pre_sell_values:Mapping[int,int],post_sell_values:Mapping[int,int],
                       saved_free_transfers:int)->FreeHitRestoration:
    # Return pre-Free-Hit squad identities; adjust bank by official sale-value deltas.
    adj=sum(int(post_sell_values.get(pid,pre_sell_values[pid]))-int(pre_sell_values[pid])
            for pid in pre_squad if pid in pre_sell_values)
    return FreeHitRestoration(tuple(pre_squad),int(pre_bank)+adj,int(saved_free_transfers))

def validate_chip_use(chip:str,*,gw:int,chips_already_used:int=0,
                      previous_chip:Optional[str]=None,previous_gw:Optional[int]=None)->None:
    if chips_already_used>=1: raise ValueError("one chip per Gameweek")
    if chip.lower()=="free_hit" and previous_chip and previous_chip.lower()=="free_hit" and previous_gw is not None and gw==previous_gw+1:
        raise ValueError("Free Hit cannot be used in consecutive Gameweeks")
    if gw<=19 and chip.lower() not in {"wildcard","free_hit"}: raise ValueError("invalid H1 chip")
    if gw>=20 and chip.lower() not in {"wildcard","free_hit"}: raise ValueError("invalid H2 chip")

def validate_lineup(squad:Sequence[Mapping[str,Any]],xi:Sequence[int],bench:Sequence[int])->bool:
    ids=[int(p.get("id",p.get("element_id",-1))) for p in squad]
    xi=list(map(int,xi)); bench=list(map(int,bench))
    if len(ids)!=15 or len(set(ids))!=15:return False
    if len(xi)!=11 or len(bench)!=4:return False
    if set(xi)&set(bench) or set(xi)|set(bench)!=set(ids):return False
    byid={int(p.get("id",p.get("element_id",-1))):p for p in squad}
    players=[byid[i] for i in xi]
    pos=[p.get("position",p.get("pos")) for p in players]
    if pos.count("GK")+pos.count("GKP")!=1:return False
    d=pos.count("DEF");m=pos.count("MID");f=pos.count("FWD")
    if not(3<=d<=5 and 2<=m<=5 and 1<=f<=3):return False
    return all(p.get("chance_of_playing_next_round")!=0 for p in players)
