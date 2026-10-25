import math

DEPTH, LEAN, WAIST, HIP_BACK = 0.25, 0.5, 0.45, 0.10


def run(robot):
    m = robot.box_mass_kg
    bx, by, bz = robot.box_pose()["pos"]
    half_w = robot.box_size[1] / 2

    robot.phase("reach")
    robot.hands_to((0.30, 0.32, -0.10), (0.30, -0.32, -0.10), 0.8)
    robot.set_posture({"waist_pitch": WAIST}, 0.4)
    robot.squat(DEPTH, 1.5, torso_pitch=LEAN, hip_back=HIP_BACK)
    robot.wait(0.3)

    robot.phase("grasp")
    grab = lambda dy: robot.world_to_pelvis_frame((bx, by + dy, bz + 0.06))
    robot.hands_to(grab(half_w + 0.10), grab(-half_w - 0.10), 0.6)
    robot.hands_to(grab(half_w - 0.005), grab(-half_w + 0.005), 0.6)
    # grip force from baseline palm preload + mass-proportional sizing formula
    mu, n, S, a = 0.8, 2, 2.0, 1.0
    grip_force = min(550.0, 100.0 + m * (9.81 + a) * S / (mu * n))
    robot.squeeze(grip_force)
    robot.wait(0.4)

    robot.phase("lift")
    # stand up slowly; pull the tote in to the belly; trunk goes upright then slightly back
    steps = 10
    x0, z0 = 0.36, -0.16
    z_final = 0.12 + 0.025 * (m / 40.0)
    back = min(1.0, max(0.35, m / 30.0))
    for k in range(1, steps + 1):
        s = k / steps
        # heavier tote -> sit the hips further back and lean the trunk back more (counterweight)
        robot.squat(
            DEPTH * (1 - s) + 0.04 * back * s,
            0.45,
            torso_pitch=LEAN * (1 - s) - 0.15 * back * s,
            hip_back=HIP_BACK + 0.05 * back * s,
        )
        robot.set_posture({"waist_pitch": WAIST * (1 - s) - 0.30 * back * s}, 0.05)
        x = x0 + (0.26 - x0) * s
        z = z0 + (z_final - z0) * s
        robot.hands_to((x, half_w - 0.005, z), (x, -half_w + 0.005, z), 0.05)

    robot.phase("hold")
    robot.wait(3.6)
