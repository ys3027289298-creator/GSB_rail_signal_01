"""Railway signal game core (implementation B).

Independent reimplementation of the same invariants using dataclasses
and explicit state objects rather than raw dictionaries. The public API
is identical to implementation A so both satisfy the same regression
tests.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class Section:
    name: str
    occupied: bool = False
    locked: bool = False
    red: bool = False

    def __getitem__(self, key: str):
        return getattr(self, key)


@dataclass
class Platform:
    name: str
    capacity: int
    trains: List[str] = field(default_factory=list)

    def __getitem__(self, key: str):
        return getattr(self, key)


@dataclass
class Route:
    rid: str
    sections: List[str]
    priority: int
    active: bool = False


@dataclass
class Train:
    tid: str
    section: Optional[str] = None
    completed: bool = False

    def __getitem__(self, key: str):
        return getattr(self, key)


class RailSignalGame:
    """Event-driven rail signal simulation using typed state objects."""

    def __init__(self):
        self.sections: Dict[str, Section] = {}
        self.platforms: Dict[str, Platform] = {}
        self.routes: Dict[str, Route] = {}
        self.trains: Dict[str, Train] = {}
        self.clock: int = 0
        self.alarms: Set[str] = set()
        self.event_log: List[str] = []
        self._seen_events: Set[str] = set()

    # -- configuration -------------------------------------------------
    def add_section(self, name: str, red: bool = False) -> "RailSignalGame":
        self.sections[name] = Section(name=name, red=red)
        return self

    def add_platform(self, section_name: str, capacity: int) -> "RailSignalGame":
        self.platforms[section_name] = Platform(name=section_name, capacity=capacity)
        return self

    def add_route(self, rid: str, sections: List[str], priority: int) -> "RailSignalGame":
        self.routes[rid] = Route(rid=rid, sections=list(sections), priority=priority)
        return self

    def add_train(self, tid: str) -> "RailSignalGame":
        self.trains[tid] = Train(tid=tid)
        return self

    # -- occupancy -----------------------------------------------------
    def enter_section(self, tid: str, name: str) -> bool:
        section = self.sections[name]
        if section.red or section.locked or section.occupied:
            return False                       # invariants 1/3: no double occupy, no red crossing
        platform = self.platforms.get(name)
        if platform is not None and len(platform.trains) >= platform.capacity:
            return False                       # invariant 4: strict platform capacity
        train = self.trains[tid]
        if train.section is not None:
            self.leave_section(tid, train.section)
        section.occupied = True
        train.section = name
        if platform is not None:
            platform.trains.append(tid)
        self._log(f"train {tid} enters {name}")
        return True

    def leave_section(self, tid: str, name: str) -> None:
        section = self.sections[name]
        section.occupied = False               # invariant 1: release occupancy after pass
        platform = self.platforms.get(name)
        if platform is not None and tid in platform.trains:
            platform.trains.remove(tid)
        train = self.trains[tid]
        if train.section == name:
            train.section = None
        self._log(f"train {tid} leaves {name}")

    # -- routes --------------------------------------------------------
    def select_route(self, candidate_ids: List[str]) -> Optional[str]:
        candidates = [
            self.routes[rid]
            for rid in candidate_ids
            if rid in self.routes and not self.routes[rid].active
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda route: route.priority, reverse=True)
        return candidates[0].rid             # invariant 2: priority, not input order

    def lock_route(self, rid: str) -> bool:
        route = self.routes[rid]
        if route.active:
            return False
        if any(self.sections[name].locked or self.sections[name].occupied for name in route.sections):
            return False
        for name in route.sections:
            self.sections[name].locked = True
        route.active = True
        self._log(f"route {rid} locked")
        return True

    def cancel_route(self, rid: str) -> None:
        route = self.routes[rid]
        if not route.active:
            return
        for name in route.sections:
            self.sections[name].locked = False   # invariant 5: cancel releases locks
        route.active = False
        self._log(f"route {rid} cancelled")

    def is_locked(self, name: str) -> bool:
        return self.sections[name].locked

    # -- signals -------------------------------------------------------
    def set_signal(self, name: str, red: bool) -> None:
        self.sections[name].red = red

    # -- alarms & faults ----------------------------------------------
    def raise_alarm(self, key: str) -> None:
        self.alarms.add(key)
        self._log(f"alarm {key} raised")

    def clear_fault(self, key: str) -> None:
        # invariant 6: recovering a fault must not clear the alarm early.
        self._log(f"fault {key} cleared (alarm retained)")

    def acknowledge_alarm(self, key: str) -> None:
        self.alarms.discard(key)
        self._log(f"alarm {key} acknowledged")

    def has_alarm(self, key: str) -> bool:
        return key in self.alarms

    # -- schedule / rollback ------------------------------------------
    def complete_train(self, tid: str) -> None:
        self.trains[tid].completed = True
        self._log(f"train {tid} completed")

    def rollback(self, previous_state: dict) -> None:
        completed_positions = {
            tid: train.section for tid, train in self.trains.items() if train.completed
        }
        self.restore(previous_state)
        for tid, section in completed_positions.items():
            if tid in self.trains:
                self.trains[tid].section = section
                self.trains[tid].completed = True
        # invariant 7: rollback does not move completed trains

    # -- persistence ---------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "clock": self.clock,
            "sections": {name: asdict(sec) for name, sec in self.sections.items()},
            "platforms": {name: asdict(plat) for name, plat in self.platforms.items()},
            "routes": {rid: asdict(route) for rid, route in self.routes.items()},
            "trains": {tid: asdict(train) for tid, train in self.trains.items()},
            "alarms": sorted(self.alarms),
            "event_log": list(self.event_log),
            "seen_events": sorted(self._seen_events),
        }

    def restore(self, state: dict) -> None:
        self.clock = state["clock"]
        self.sections = {name: Section(**data) for name, data in state["sections"].items()}
        self.platforms = {name: Platform(**data) for name, data in state["platforms"].items()}
        self.routes = {rid: Route(**data) for rid, data in state["routes"].items()}
        self.trains = {tid: Train(**data) for tid, data in state["trains"].items()}
        self.alarms = set(state.get("alarms", []))
        self.event_log = list(state.get("event_log", []))
        self._seen_events = set(state.get("seen_events", []))

    def record_event(self, key: str) -> bool:
        # invariant 8: after save/restore an event must not execute twice
        if key in self._seen_events:
            return False
        self._seen_events.add(key)
        self.event_log.append(key)
        return True

    def to_json(self) -> str:
        return json.dumps(self.snapshot(), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "RailSignalGame":
        game = cls()
        game.restore(json.loads(text))
        return game

    def _log(self, message: str) -> None:
        self.event_log.append(message)
