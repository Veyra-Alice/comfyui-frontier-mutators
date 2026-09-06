import importlib.util
import math
import pathlib
import sys
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).parents[1] / "nodes.py"
SPEC = importlib.util.spec_from_file_location("frontier_nodes", MODULE_PATH)
nodes = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = nodes
SPEC.loader.exec_module(nodes)


FLOAT_DEFAULTS = {
    "distribution": "gaussian",
    "centre": 7.0,
    "spread": 0.2,
    "clip_sigma": 2.0,
    "hard_min": 0.0,
    "hard_max": 20.0,
    "quantum": 0.01,
    "random_seed": 12345,
}


class FrontierFloatMutatorTests(unittest.TestCase):
    def test_locked_sample_is_deterministic_across_instances(self):
        first = nodes.FrontierFloatMutator().mutate(**FLOAT_DEFAULTS, lock_current=True)
        second = nodes.FrontierFloatMutator().mutate(**FLOAT_DEFAULTS, lock_current=True)
        self.assertEqual(first["result"], second["result"])

    def test_unlocked_sample_uses_and_reports_fresh_entropy(self):
        mutator = nodes.FrontierFloatMutator()
        with mock.patch.object(nodes.secrets, "randbits", side_effect=[11, 12]):
            first = mutator.mutate(**FLOAT_DEFAULTS, lock_current=False)
            second = mutator.mutate(**FLOAT_DEFAULTS, lock_current=False)
        self.assertEqual(first["result"][1], 11)
        self.assertEqual(second["result"][1], 12)
        self.assertNotEqual(first["result"][0], second["result"][0])

    def test_lock_transition_holds_the_most_recent_live_sample(self):
        mutator = nodes.FrontierFloatMutator()
        with mock.patch.object(nodes.secrets, "randbits", return_value=991):
            live = mutator.mutate(**FLOAT_DEFAULTS, lock_current=False)
        locked = mutator.mutate(**FLOAT_DEFAULTS, lock_current=True)
        self.assertEqual(live["result"], locked["result"])

    def test_gaussian_sample_obeys_sigma_clip_and_hard_bounds(self):
        result = nodes.FrontierFloatMutator().mutate(
            distribution="gaussian",
            centre=5.0,
            spread=2.0,
            clip_sigma=0.5,
            hard_min=4.25,
            hard_max=5.75,
            quantum=0.0,
            random_seed=17,
            lock_current=True,
        )["result"][0]
        self.assertGreaterEqual(result, 4.25)
        self.assertLessEqual(result, 5.75)

    def test_quantisation_is_applied(self):
        result = nodes.FrontierFloatMutator().mutate(
            distribution="fixed",
            centre=1.234,
            spread=0.0,
            clip_sigma=0.0,
            hard_min=0.0,
            hard_max=2.0,
            quantum=0.05,
            random_seed=0,
            lock_current=True,
        )["result"][0]
        self.assertTrue(math.isclose(result, 1.25))

    def test_decimal_quantisation_has_clean_serialisation(self):
        self.assertEqual(nodes._quantise(6.846, 0.01), 6.85)
        self.assertEqual(str(nodes._quantise(6.846, 0.01)), "6.85")

    def test_cache_fingerprint_is_stable_only_when_locked(self):
        locked_a = nodes.FrontierFloatMutator.IS_CHANGED(lock_current=True, **FLOAT_DEFAULTS)
        locked_b = nodes.FrontierFloatMutator.IS_CHANGED(lock_current=True, **FLOAT_DEFAULTS)
        unlocked = nodes.FrontierFloatMutator.IS_CHANGED(lock_current=False, **FLOAT_DEFAULTS)
        self.assertEqual(locked_a, locked_b)
        self.assertTrue(math.isnan(unlocked))


class FrontierIntegerMutatorTests(unittest.TestCase):
    def test_integer_node_returns_integer_and_honours_quantum(self):
        value, effective_seed = nodes.FrontierIntegerMutator().mutate(
            distribution="fixed",
            centre=103,
            spread=0.0,
            clip_sigma=0.0,
            hard_min=0,
            hard_max=1000,
            quantum=10,
            random_seed=55,
            lock_current=True,
        )["result"]
        self.assertEqual(value, 100)
        self.assertIsInstance(value, int)
        self.assertEqual(effective_seed, 55)

    def test_invalid_bounds_raise(self):
        with self.assertRaisesRegex(ValueError, "hard_min"):
            nodes.FrontierIntegerMutator().mutate(
                distribution="uniform",
                centre=5,
                spread=1.0,
                clip_sigma=0.0,
                hard_min=10,
                hard_max=0,
                quantum=1,
                random_seed=0,
                lock_current=True,
            )

    def test_large_fixed_seed_is_not_rounded_through_float(self):
        centre = nodes.U64_MAX - 123
        value = nodes.FrontierIntegerMutator().mutate(
            distribution="fixed",
            centre=centre,
            spread=0.0,
            clip_sigma=0.0,
            hard_min=0,
            hard_max=nodes.U64_MAX,
            quantum=1,
            random_seed=7,
            lock_current=True,
        )["result"][0]
        self.assertEqual(value, centre)

    def test_large_gaussian_seed_keeps_integer_centre_exact(self):
        centre = nodes.U64_MAX - 1000
        value = nodes.FrontierIntegerMutator().mutate(
            distribution="gaussian",
            centre=centre,
            spread=10.0,
            clip_sigma=3.0,
            hard_min=0,
            hard_max=nodes.U64_MAX,
            quantum=1,
            random_seed=81,
            lock_current=True,
        )["result"][0]
        self.assertLessEqual(abs(value - centre), 30)


if __name__ == "__main__":
    unittest.main()
