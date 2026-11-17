import unittest
from readiness import classify


class QualificationTest(unittest.TestCase):
    def test_unproved_tie_is_not_optimal(self):
        self.assertEqual(classify(True, True, "timelimit", 12, 0), "cuts_active_incumbent_stagnant")

    def test_zero_callbacks_do_not_qualify_selector(self):
        self.assertEqual(classify(True, True, "timelimit", 0, 0), "no_cut_selection_opportunity")

    def test_budget_failure_not_used_as_advantage(self):
        self.assertEqual(classify(True, False, "timelimit", 25, 100), "invalid_or_overbudget")

    def test_exact_control_and_search_are_separate(self):
        self.assertEqual(classify(True, True, "optimal", 20, 2), "optimal_control_only")
        self.assertEqual(classify(True, True, "timelimit", 20, 2), "active_search_with_improvement")


if __name__ == "__main__":
    unittest.main()
