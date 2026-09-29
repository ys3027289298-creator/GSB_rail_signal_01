"""Regression tests for the eight rail signal timing invariants."""

import unittest

from rail.core import RailSignalGame


def make_game():
    game = RailSignalGame()
    for name in ("s1", "s2", "s3"):
        game.add_section(name)
    game.add_platform("s2", 1)  # capacity one
    return game


class TestOccupancyRelease(unittest.TestCase):
    def test_train_passes_releases_previous_section(self):
        game = make_game()
        game.add_train("T1")
        self.assertTrue(game.enter_section("T1", "s1"))
        self.assertTrue(game.sections["s1"]["occupied"])
        self.assertTrue(game.enter_section("T1", "s2"))
        self.assertFalse(game.sections["s1"]["occupied"], "passing train must release the section behind it")
        self.assertTrue(game.sections["s2"]["occupied"])


class TestRoutePriority(unittest.TestCase):
    def test_same_time_routes_resolved_by_priority(self):
        game = make_game()
        game.add_route("r-low", ["s1", "s2"], 1)
        game.add_route("r-mid", ["s1", "s2"], 3)
        game.add_route("r-high", ["s1", "s2"], 5)
        self.assertEqual(game.select_route(["r-low", "r-mid", "r-high"]), "r-high")


class TestRedSignal(unittest.TestCase):
    def test_red_signal_blocks_crossing(self):
        game = make_game()
        game.set_signal("s2", True)
        game.add_train("T1")
        self.assertFalse(game.enter_section("T1", "s2"))
        self.assertFalse(game.sections["s2"]["occupied"])


class TestPlatformCapacity(unittest.TestCase):
    def test_platform_capacity_boundary(self):
        game = make_game()
        game.add_train("T1")
        game.add_train("T2")
        self.assertTrue(game.enter_section("T1", "s2"))
        self.assertFalse(game.enter_section("T2", "s2"), "second train must not exceed platform capacity")


class TestCancelRoute(unittest.TestCase):
    def test_cancel_route_releases_locks(self):
        game = make_game()
        game.add_route("r1", ["s1", "s2"], 1)
        self.assertTrue(game.lock_route("r1"))
        self.assertTrue(game.is_locked("s1"))
        game.cancel_route("r1")
        self.assertFalse(game.is_locked("s1"))
        self.assertFalse(game.is_locked("s2"))


class TestFaultRecoveryAlarm(unittest.TestCase):
    def test_recovery_does_not_clear_alarm_early(self):
        game = make_game()
        game.raise_alarm("signal-fault")
        game.clear_fault("signal-fault")
        self.assertTrue(game.has_alarm("signal-fault"), "clearing a fault must not clear the alarm")
        game.acknowledge_alarm("signal-fault")
        self.assertFalse(game.has_alarm("signal-fault"))


class TestRollbackCompletedTrain(unittest.TestCase):
    def test_rollback_preserves_completed_train_position(self):
        game = make_game()
        game.add_train("T1")
        game.add_train("T2")
        game.enter_section("T1", "s1")
        game.enter_section("T1", "s2")
        game.enter_section("T1", "s3")
        game.complete_train("T1")
        before = game.snapshot()
        game.enter_section("T2", "s1")
        game.rollback(before)
        self.assertEqual(game.trains["T1"]["section"], "s3")
        self.assertTrue(game.trains["T1"]["completed"])


class TestSaveRestoreDedup(unittest.TestCase):
    def test_restore_does_not_replay_events(self):
        game = make_game()
        self.assertTrue(game.record_event("arrive-T1"))
        state = game.snapshot()
        restored = RailSignalGame()
        restored.restore(state)
        self.assertFalse(restored.record_event("arrive-T1"), "restored game must not replay an executed event")


class TestSimultaneousArrivalBoundary(unittest.TestCase):
    def test_two_trains_arrive_at_same_time_on_capacity_one(self):
        game = make_game()
        game.add_train("T1")
        game.add_train("T2")
        self.assertTrue(game.enter_section("T1", "s2"))
        self.assertFalse(game.enter_section("T2", "s2"))
        self.assertEqual(game.platforms["s2"]["trains"], ["T1"])


if __name__ == "__main__":
    unittest.main()
