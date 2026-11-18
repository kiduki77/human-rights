import json
import unittest

import helpers
from runtime.config import DEFAULTS
from runtime.routing.router import apply_route, route

AXES = ("ambiguity", "scope", "architecture", "risk", "verification", "dependency")


def axes(**scores):
    return {k: {"score": scores.get(k, 0), "basis": "test", "confirmed": True, "confidence": "high"} for k in AXES}


class RouterTest(unittest.TestCase):
    def test_trivial_request_is_l0_without_gates(self):
        r = route(axes(), [], DEFAULTS)
        self.assertEqual(r["mode"], "L0")
        self.assertEqual(r["gates"], [])

    def test_one_high_axis_is_not_averaged_away(self):
        self.assertEqual(route(axes(risk=3), [], DEFAULTS)["mode"], "L3")

    def test_unconfirmed_low_confidence_is_bumped(self):
        a = axes()
        a["risk"] = {"score": 1, "basis": "guess", "confirmed": False, "confidence": "low"}
        self.assertEqual(route(a, [], DEFAULTS)["effective_scores"]["risk"], 2)

    def test_vehicle_command_forces_l3_and_both_gates(self):
        r = route(axes(scope=1), ["vehicle_command"], DEFAULTS)
        self.assertEqual(r["mode"], "L3")
        self.assertEqual({g["gate"] for g in r["gates"] if g["sticky"]}, {"design", "final"})

    def test_auth_forces_at_least_l2_with_approval(self):
        r = route(axes(), ["auth"], DEFAULTS)
        self.assertEqual(r["mode"], "L2")
        self.assertTrue(any(g["gate"] == "final" for g in r["gates"]))

    def test_basis_is_required(self):
        a = axes()
        a["scope"]["basis"] = ""
        with self.assertRaises(Exception):
            route(a, [], DEFAULTS)

    def test_safety_gate_survives_downgrade(self):
        st = {"gate_reasons": [], "mode": None}
        apply_route(st, route(axes(), ["physical_safety"], DEFAULTS), "t0")
        notes = apply_route(st, route(axes(), [], DEFAULTS), "t1")
        self.assertEqual(st["mode"], "L3")
        self.assertTrue(st["required_gates"]["design"] and st["required_gates"]["final"])
        self.assertTrue(any("L3" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
