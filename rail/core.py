"""Railway signal game core (implementation A).

The game models a small rail yard as a set of track sections connected
through routes. A logical clock drives trains through the network while
signals, route locking, platform capacity, alarms and JSON save/restore
must each satisfy an invariant.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Set


class RailSignalGame:
    """Event-driven rail signal simulation.

    Every mutation goes through the methods below so that the eight
    timing invariants are enforced in one place.
    """

    def __init__(self):
        self.sections: Dict[str, dict] = {}     # name -> {occupied, locked, red}
        self.platforms: Dict[str, dict] = {}    # name -> {capacity, trains}
        self.routes: Dict[str, dict] = {}       # rid -> {sections, priority, active}
        self.trains: Dict[str, dict] = {}       # tid -> {section, completed}
        self.clock: int = 0
        self.alarms: Set[str] = set()
        self.event_log: List[str] = []
        self._seen_events: Set[str] = set()

    # -- configuration -------------------------------------------------
    def add_section(self, name: str, red: bool = False) -> "RailSignalGame":
        self.sections[name] = {"occupied": False, "locked": False, "red": red}
        return self

    def add_platform(self, section_name: str, capacity: int) -> "RailSignalGame":
        self.platforms[section_name] = {"capacity": capacity, "trains": []}
        return self

    def add_route(self, rid: str, sections: List[str], priority: int) -> "RailSignalGame":
        self.routes[rid] = {"sections": list(sections), "priority": priority, "active": False}
        return self

    def add_train(self, tid: str) -> "RailSignalGame":
        self.trains[tid] = {"section": None, "completed": False}
        return self

    # -- occupancy -----------------------------------------------------
    def enter_section(self, tid: str, name: str) -> bool:
        """Move a train into a section, respecting signals, locks and capacity."""
        section = self.sections[name]
        if section["red"]:
            return False                       # invariant 3: red signal blocks crossing
        if section["locked"]:
            return False
        if section["occupied"]:
            return False
        platform = self.platforms.get(name)
        if platform is not None and len(platform["trains"]) >= platform["capacity"]:
            return False                       # invariant 4: strict platform capacity
        # Leave the previous section and release its occupancy.
        prev = self.trains[tid]["section"]
        if prev is not None:
            self.leave_section(tid, prev)
        section["occupied"] = True
        self.trains[tid]["section"] = name
        if platform is not None:
            platform["trains"].append(tid)
        self._log(f"train {tid} enters {name}")
        return True

    def leave_section(self, tid: str, name: str) -> None:
        """Release a section after a train has passed through it."""
        section = self.sections[name]
        if section["occupied"]:
            section["occupied"] = False        # invariant 1: release occupancy after pass
        platform = self.platforms.get(name)
        if platform is not None and tid in platform["trains"]:
            platform["trains"].remove(tid)
        if self.trains[tid]["section"] == name:
            self.trains[tid]["section"] = None
        self._log(f"train {tid} leaves {name}")

    # -- routes --------------------------------------------------------
    def select_route(self, candidate_ids: List[str]) -> Optional[str]:
        """Choose the highest-priority route among simultaneous candidates."""
        available = [rid for rid in candidate_ids if rid in self.routes and not self.routes[rid]["active"]]
        if not available:
            return None
        # invariant 2: same-time routes resolved by priority, not input order
        return max(available, key=lambda rid: self.routes[rid]["priority"])

    def lock_route(self, rid: str) -> bool:
        route = self.routes[rid]
        if route["active"]:
            return False
        for name in route["sections"]:
            section = self.sections[name]
            if section["locked"] or section["occupied"]:
                return False
        for name in route["sections"]:
            self.sections[name]["locked"] = True
        route["active"] = True
        self._log(f"route {rid} locked")
        return True

    def cancel_route(self, rid: str) -> None:
        """Cancel a route and release every lock it held."""
        route = self.routes[rid]
        if not route["active"]:
            return
        for name in route["sections"]:
            self.sections[name]["locked"] = False   # invariant 5: cancel releases locks
        route["active"] = False
        self._log(f"route {rid} cancelled")

    def is_locked(self, name: str) -> bool:
        return self.sections[name]["locked"]

    # -- signals -------------------------------------------------------
    def set_signal(self, name: str, red: bool) -> None:
        self.sections[name]["red"] = red

    # -- alarms & faults ----------------------------------------------
    def raise_alarm(self, key: str) -> None:
        self.alarms.add(key)
        self._log(f"alarm {key} raised")

    def clear_fault(self, key: str) -> None:
        """Resolve the underlying fault WITHOUT clearing the alarm."""
        # invariant 6: recovering a fault must not clear the alarm early;
        # the alarm stays until it is explicitly acknowledged.
        self._log(f"fault {key} cleared (alarm retained)")

    def acknowledge_alarm(self, key: str) -> None:
        self.alarms.discard(key)
        self._log(f"alarm {key} acknowledged")

    def has_alarm(self, key: str) -> bool:
        return key in self.alarms

    # -- schedule / rollback ------------------------------------------
    def complete_train(self, tid: str) -> None:
        self.trains[tid]["completed"] = True
        self._log(f"train {tid} completed")

    def rollback(self, previous_state: dict) -> None:
        """Restore a saved state but keep completed trains where they are."""
        completed_positions = {
            tid: self.trains[tid]["section"]
            for tid, train in self.trains.items() if train["completed"]
        }
        self.restore(previous_state)
        for tid, section in completed_positions.items():
            if tid in self.trains:
                self.trains[tid]["section"] = section
                self.trains[tid]["completed"] = True
        # invariant 7: rollback does not move completed trains

    # -- persistence ---------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "clock": self.clock,
            "sections": {k: dict(v) for k, v in self.sections.items()},
            "platforms": {k: {"capacity": v["capacity"], "trains": list(v["trains"])} for k, v in self.platforms.items()},
            "routes": {k: dict(v) for k, v in self.routes.items()},
            "trains": {k: dict(v) for k, v in self.trains.items()},
            "alarms": sorted(self.alarms),
            "event_log": list(self.event_log),
            "seen_events": sorted(self._seen_events),
        }

    def restore(self, state: dict) -> None:
        self.clock = state["clock"]
        self.sections = {k: dict(v) for k, v in state["sections"].items()}
        self.platforms = {k: {"capacity": v["capacity"], "trains": list(v["trains"])} for k, v in state["platforms"].items()}
        self.routes = {k: dict(v) for k, v in state["routes"].items()}
        self.trains = {k: dict(v) for k, v in state["trains"].items()}
        self.alarms = set(state.get("alarms", []))
        self.event_log = list(state.get("event_log", []))
        self._seen_events = set(state.get("seen_events", []))

    def record_event(self, key: str) -> bool:
        """Record an event, returning False when it is a duplicate."""
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
