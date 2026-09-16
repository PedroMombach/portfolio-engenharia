import math
import unittest

import numpy as np

from pump_selector import Pump, PumpCurve, PumpMetadata, SystemCurve


def make_pump(npsh=True):
    metadata = PumpMetadata(
        pump_id="TEST-001",
        manufacturer="Synthetic",
        model="Test",
        poles=4,
        base_speed_rpm=1750,
        base_frequency_hz=60,
        motor_efficiency=0.9,
        motor_power_kw=15,
        minimum_submergence_mm=300,
        impeller_axis_mm=150,
        voltage_v=380,
        mass_kg=100,
        q_bep_lps=10,
        head_bep_m=20,
        efficiency_bep=0.8,
        npshr_bep_m=2 if npsh else None,
    )
    curve = PumpCurve(
        60,
        np.array([0.0, 10.0, 20.0]),
        np.array([30.0, 20.0, 0.0]),
        np.array([0.1, 0.8, 0.1]),
        np.array([1.0, 2.0, 4.0]) if npsh else np.full(3, np.nan),
    )
    return Pump(metadata, curve)


class PumpModelTests(unittest.TestCase):
    def test_base_curve_is_created_and_cannot_be_deleted(self):
        pump = make_pump()
        self.assertEqual(list(pump.curves), [60.0])
        with self.assertRaisesRegex(ValueError, "cannot be deleted"):
            pump.remove_curve(60)

    def test_affinity_laws_and_sarbu_borza_efficiency(self):
        pump = make_pump()
        frequency = 45.0
        ratio = pump.speed_ratio_for_frequency(frequency)
        curve = pump.curve_at(frequency)
        np.testing.assert_allclose(curve.q_lps, pump.base_curve.q_lps * ratio)
        np.testing.assert_allclose(curve.head_m, pump.base_curve.head_m * ratio**2)
        expected = 1 - (1 - 0.8) * ratio**-0.1
        self.assertAlmostEqual(curve.efficiency[1], expected)
        self.assertIs(pump.curves[frequency], curve)

    def test_system_curve_includes_static_head(self):
        system = SystemCurve("test", 10, 25, 5)
        self.assertEqual(system.head(0), 5)
        self.assertEqual(system.head(10), 25)
        self.assertEqual(system.resistance, 0.2)

    def test_exact_intersection(self):
        pump = make_pump()
        system = SystemCurve("system", 10, 20, 0)
        result = pump.intersect(system)
        self.assertTrue(result.found)
        self.assertAlmostEqual(result.q_lps, 10.0, places=8)
        self.assertAlmostEqual(result.head_m, 20.0, places=8)

    def test_missing_npsh_remains_unknown(self):
        pump = make_pump(npsh=False)
        operation = pump.set_op("duty", altitude_m=0, q_lps=10, head_m=20)
        self.assertIsNone(operation.npsh.required_m)
        self.assertEqual(operation.npsh.status(), "not_available")
        self.assertTrue(math.isfinite(operation.npsh.available_m))


if __name__ == "__main__":
    unittest.main()
