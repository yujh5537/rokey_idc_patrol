import unittest
import argparse
from route import ROUTE, run_route, positive


class RouteTests(unittest.TestCase):
    def test_success_visits_in_order(self):
        calls = []
        self.assertTrue(run_route(lambda p: calls.append(p) or True, lambda: True))
        self.assertEqual(calls, list(ROUTE))

    def test_failure_never_sends_next_goal(self):
        calls = []
        def navigate(p):
            calls.append(p)
            return len(calls) < 2
        self.assertFalse(run_route(navigate, lambda: True))
        self.assertEqual(calls, list(ROUTE[:2]))

    def test_interrupted_dwell_stops_route(self):
        calls = []
        self.assertFalse(run_route(lambda p: calls.append(p) or True, lambda: False))
        self.assertEqual(calls, [ROUTE[0]])

    def test_invalid_timeout(self):
        for value in ['0', '-1', 'nan', 'inf']:
            with self.assertRaises(argparse.ArgumentTypeError):
                positive(value)


if __name__ == '__main__':
    unittest.main()
