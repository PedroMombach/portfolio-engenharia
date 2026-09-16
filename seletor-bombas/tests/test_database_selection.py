from pathlib import Path
import unittest

from pump_selector import PumpDatabase, SelectionMode, load_cases, select_pumps


ROOT = Path(__file__).resolve().parents[1]


class DatabaseSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = PumpDatabase.from_xlsx(ROOT / "DB" / "PumpDatabase.xlsx")
        cls.cases = load_cases(ROOT / "ExampleInputs.xlsx")

    def test_synthetic_database_correspondence_and_bep(self):
        self.assertEqual(len(self.database.pump_ids), 21)
        self.assertEqual(set(self.database.curves["ID"]), set(self.database.pump_ids))
        self.assertTrue((self.database.metadata["baseFreq"] == 60).all())
        self.assertTrue(self.database.metadata[["Qbep", "Hbep", "Eta1bep"]].notna().all().all())
        self.assertEqual(self.database.metadata["NPSHbep"].isna().sum(), 2)

    def test_all_selection_modes_use_exact_unique_ids(self):
        for case in self.cases:
            with self.subTest(mode=case.mode):
                result = select_pumps(
                    self.database,
                    case.request(),
                    case.mode,
                    manual_ids=case.manual_ids,
                )
                identifiers = [item.pump_id for item in result.selected]
                self.assertEqual(len(identifiers), 3)
                self.assertEqual(len(identifiers), len(set(identifiers)))
                self.assertTrue(set(identifiers).issubset(self.database.pump_ids))

    def test_missing_npsh_policy_is_explicit(self):
        manual = self.cases[2]
        result = select_pumps(
            self.database,
            manual.request(),
            SelectionMode.MANUAL,
            manual_ids=manual.manual_ids,
        )
        first = result.selected[0]
        self.assertEqual(first.pump_id, "AN-002")
        self.assertTrue(any("did not provide" in message for message in first.warnings))


if __name__ == "__main__":
    unittest.main()
