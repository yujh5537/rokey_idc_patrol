import unittest
import yaml
from patrol import CONFIG, build_route, run_patrol, pose_matches


class PatrolTests(unittest.TestCase):
    def setUp(self):
        with CONFIG.open() as f:
            self.config = yaml.safe_load(f)
        self.route = build_route(self.config) + [('return_start', .4, 4.9, 0)]

    def test_robot11_assignment_and_exact_rack_order(self):
        self.assertEqual(self.config['robot_zones']['robot11'], ['Z1', 'Z2'])
        names = [p[0] for p in self.route]
        self.assertEqual(
            [n for n in names if n.startswith('R')],
            self.config['patrol_routes']['robot11'],
        )
        self.assertEqual(
            self.config['patrol_routes']['robot11'][:7],
            ['R07', 'R06', 'R05', 'R04', 'R03', 'R02', 'R01'],
        )
        self.assertEqual(
            self.config['patrol_routes']['robot11'][14:21],
            ['R21', 'R20', 'R19', 'R18', 'R17', 'R16', 'R15'],
        )

    def test_route_uses_map02_coordinates_directly(self):
        names = [p[0] for p in self.route]
        self.assertEqual(self.route[0][1:], (0.27, 2.625, -1.5707963267948966))
        self.assertEqual(self.route[1][1:], (1.4, 2.8, 0.0))
        self.assertEqual(self.route[names.index('Z1_entry')][1:], (1.4, 4.9, 0.0))
        self.assertEqual(self.route[names.index('R07')][1:], (2.135, 4.9, 1.5708))
        self.assertEqual(self.route[names.index('R01')][1:], (3.229, 4.9, 1.3072))
        self.assertEqual(self.route[names.index('Z2_entry')][1:], (1.4, 3.5, 0.0))
        self.assertEqual(self.route[names.index('R21')][1:], (2.135, 3.5, 1.5708))
        self.assertEqual(self.route[names.index('R28')][1:], (2.135, 3.5, -1.5708))

    def test_zone_transition_and_return(self):
        names = [p[0] for p in self.route]
        i = names.index('R14')
        self.assertEqual(
            names[i:i + 4],
            ['R14', 'Z1_exit', 'Z2_entry', 'R21'],
        )
        self.assertEqual(
            names[-5:],
            ['R28', 'Z2_exit', 'return_z2_z3_midpoint',
             'return_dock_midpoint', 'return_start'],
        )

    def test_complete_sequence_and_one_dock(self):
        events = []
        self.assertTrue(
            run_patrol(
                lambda p: events.append(('go', p[0])) or True,
                lambda n: events.append(('inspect', n)) or True,
                lambda: events.append(('dock', '')) or True,
                self.route,
            )
        )
        self.assertEqual(sum(e[0] == 'inspect' for e in events), 28)
        self.assertEqual(events[-2:], [('go', 'return_start'), ('dock', '')])
        for i, event in enumerate(events):
            if event[0] == 'inspect':
                self.assertEqual(events[i - 1], ('go', event[1]))

    def test_navigation_failure_blocks_later_goals_and_dock(self):
        for index in range(len(self.route)):
            calls, docks = [], []

            def navigate(p):
                calls.append(p)
                return len(calls) <= index

            self.assertFalse(
                run_patrol(
                    navigate,
                    lambda _: True,
                    lambda: docks.append(True) or True,
                    self.route,
                )
            )
            self.assertEqual(calls, self.route[:index + 1])
            self.assertEqual(docks, [])

    def test_interrupted_inspection_and_dock_failure(self):
        calls = []
        self.assertFalse(
            run_patrol(
                lambda p: calls.append(p[0]) or True,
                lambda _: False,
                lambda: self.fail('dock called'),
                self.route,
            )
        )
        self.assertEqual(calls[-1], 'R07')
        self.assertFalse(
            run_patrol(
                lambda _: True,
                lambda _: True,
                lambda: False,
                self.route,
            )
        )

    def test_alignment_rejects_adjacent_rack_and_wrong_heading(self):
        self.assertFalse(
            pose_matches(
                (2.345, 4.9, 1.5708),
                (2.135, 4.9, 1.5708),
            )
        )
        self.assertFalse(
            pose_matches(
                (2.135, 4.9, -1.5708),
                (2.135, 4.9, 1.5708),
            )
        )
        self.assertTrue(
            pose_matches(
                (2.135, 4.9, 1.5708),
                (2.135, 4.9, 1.5708),
            )
        )


if __name__ == '__main__':
    unittest.main()
