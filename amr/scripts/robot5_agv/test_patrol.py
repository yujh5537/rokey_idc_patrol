import math
import unittest
import yaml
from patrol import (
    CONFIG,
    EXPECTED_ROBOT5_ROUTE,
    build_route,
    run_patrol,
    ensure_undocked,
    REQUIRED_NODES,
    visit_rack,
    angle_difference,
)


class PatrolTests(unittest.TestCase):
    def setUp(self):
        with CONFIG.open() as f:
            self.config = yaml.safe_load(f)
        self.route = build_route(self.config) + [('return_start', .4, .33, 0)]

    def test_robot5_assignment_and_exact_rack_order(self):
        self.assertEqual(self.config['robot_zones']['robot5'], ['Z3', 'Z4'])
        self.assertEqual(
            self.config['patrol_routes']['robot5'],
            EXPECTED_ROBOT5_ROUTE,
        )

        names = [p[0] for p in self.route]
        self.assertEqual(
            [n for n in names if n.startswith('R')],
            EXPECTED_ROBOT5_ROUTE,
        )

    def test_route_uses_map02_coordinates_directly(self):
        names = [p[0] for p in self.route]
        self.assertEqual(self.route[0][1:], (0.27, 2.625, math.pi / 2))
        self.assertEqual(self.route[1][1:], (1.4, 2.8, 0.0))
        self.assertEqual(self.route[names.index('Z4_entry')][1:], (1.4, 0.7, 0.0))
        self.assertEqual(self.route[names.index('R56')][1:], (2.135, 0.7, -1.5708))
        self.assertEqual(self.route[names.index('R50')][1:], (3.229, 0.7, -1.3072))
        self.assertEqual(self.route[names.index('R43')][1:], (3.229, 0.7, 1.3072))
        self.assertEqual(self.route[names.index('Z3_entry')][1:], (1.4, 2.1, 0.0))
        self.assertEqual(self.route[names.index('R42')][1:], (2.135, 2.1, -1.5708))
        self.assertEqual(self.route[names.index('R35')][1:], (2.135, 2.1, 1.5708))

    def test_no_robot5_z1_z2_racks_in_route(self):
        racks = {r['rack_id']: r for r in self.config['racks']}
        patrol_racks = [p[0] for p in self.route if p[0].startswith('R')]
        self.assertEqual(
            {racks[rid]['zone_id'] for rid in patrol_racks},
            {'Z3', 'Z4'},
        )

    def test_zone_transition_and_return(self):
        names = [p[0] for p in self.route]
        i = names.index('R49')
        self.assertEqual(
            names[i:i + 4],
            ['R49', 'Z4_exit', 'Z3_entry', 'R42'],
        )
        self.assertEqual(
            names[-5:],
            ['R35', 'Z3_exit', 'return_mid_wall_crossing',
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
        self.assertEqual(calls[-1], 'R56')
        self.assertFalse(
            run_patrol(
                lambda _: True,
                lambda _: True,
                lambda: False,
                self.route,
            )
        )

    def test_undock_sequence_and_failures(self):
        events = []
        self.assertTrue(ensure_undocked(
            True, lambda: events.append('undock') or True,
            lambda: events.append('confirm') or True))
        self.assertEqual(events, ['undock', 'confirm'])
        self.assertFalse(ensure_undocked(None, lambda: self.fail(), lambda: self.fail()))
        self.assertFalse(ensure_undocked(True, lambda: False, lambda: self.fail()))
        self.assertFalse(ensure_undocked(True, lambda: True, lambda: False))
        self.assertTrue(ensure_undocked(False, lambda: self.fail(), lambda: True))

    def test_velocity_and_recovery_nodes_are_required(self):
        self.assertTrue({'behavior_server', 'velocity_smoother', 'collision_monitor'}
                        <= set(REQUIRED_NODES))

    def test_rack_travel_then_face(self):
        events = []
        self.assertTrue(visit_rack(
            ('R55', 2.345, 0.7, -math.pi / 2),
            lambda: (2.135, 0.7, -math.pi / 2),
            lambda name, yaw: events.append((name, yaw)) or True,
            lambda goal: events.append(goal) or True))
        self.assertEqual(events[0], ('R55:TURN_TO_TRAVEL', 0.0))
        self.assertEqual(events[1], ('R55:MOVE', 2.345, 0.7, 0.0))
        self.assertEqual(events[2], ('R55:FACE_RACK', -math.pi / 2))

    def test_shared_or_nearby_pose_only_turns(self):
        for actual_x in (3.229, 3.185):
            events = []
            self.assertTrue(visit_rack(
                ('R43', 3.229, 0.7, 1.3072),
                lambda: (actual_x, 0.7, -1.3072),
                lambda name, yaw: events.append(name) or True,
                lambda goal: self.fail('unnecessary tiny move')))
            self.assertEqual(events, ['R43:FACE_RACK'])

    def test_stage_failure_blocks_dwell_and_docking(self):
        for failed in ('TURN_TO_TRAVEL', 'MOVE', 'FACE_RACK'):
            events = []

            def turn(name, yaw):
                events.append(name)
                return not name.endswith(failed)

            def move(goal):
                events.append(goal[0])
                return failed != 'MOVE'

            self.assertFalse(run_patrol(
                lambda goal: visit_rack(goal, lambda: (1.4, 0.7, 0), turn, move),
                lambda name: self.fail('dwell after failed stage'),
                lambda: self.fail('dock after failed stage'),
                [('R56', 2.135, 0.7, -math.pi / 2)]))
            self.assertTrue(events[-1].endswith(failed))

    def test_missing_pose_and_angle_wrap(self):
        self.assertFalse(visit_rack(
            ('R56', 2.135, 0.7, -1.5708), lambda: None,
            lambda *args: self.fail(), lambda *args: self.fail()))
        self.assertAlmostEqual(angle_difference(math.radians(-179), math.radians(179)), math.radians(2))

    def test_profile_reduces_adjacent_rack_skip_without_disabling_collision(self):
        with CONFIG.parents[3].joinpath('scripts/robot5_agv/nav2_patrol.yaml').open() as f:
            profile = yaml.safe_load(f)
        c = profile['controller_server']['ros__parameters']
        self.assertLess(2 * c['general_goal_checker']['xy_goal_tolerance'], .21)
        self.assertEqual(c['FollowPath']['xy_goal_tolerance'], c['general_goal_checker']['xy_goal_tolerance'])
        self.assertTrue(profile['collision_monitor']['ros__parameters']['scan']['enabled'])


if __name__ == '__main__':
    unittest.main()
