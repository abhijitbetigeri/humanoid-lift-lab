"""Textbook baseline: stoop lift (bend at the waist, legs nearly straight), grip force from the
gripper sizing formula F = m (g + a) S / (mu n) with S = 2, fixed-speed lift."""


def run(robot):
    m = robot.box_mass_kg
    bx, by, bz = robot.box_pose()["pos"]
    half_w = robot.box_size[1] / 2

    robot.phase("reach")
    robot.hands_to((0.30, 0.32, -0.10), (0.30, -0.32, -0.10), 0.8)
    robot.set_posture({"waist_pitch": 0.5}, 0.4)
    robot.squat(0.04, 1.2, torso_pitch=1.3)          # stoop: bend at the hips, knees almost straight
    robot.wait(0.3)

    robot.phase("grasp")
    grab = lambda dy: robot.world_to_pelvis_frame((bx, by + dy, bz + 0.06))
    robot.hands_to(grab(half_w + 0.10), grab(-half_w - 0.10), 0.6)
    robot.hands_to(grab(half_w - 0.005), grab(-half_w + 0.005), 0.6)
    mu, n, S, a = 0.8, 2, 2.0, 0.0
    robot.squeeze(m * (9.81 + a) * S / (mu * n))
    robot.wait(0.3)

    robot.phase("lift")
    # straighten the back at a fixed speed, arms stay where they are
    robot.set_posture({"left_hip_pitch": 0.0, "right_hip_pitch": 0.0, "left_knee": 0.0, "right_knee": 0.0,
                       "left_ankle_pitch": 0.0, "right_ankle_pitch": 0.0, "waist_pitch": 0.0},
                      1.5, profile="linear")
    robot.hands_to((0.30, half_w - 0.005, 0.0), (0.30, -half_w + 0.005, 0.0), 0.8)

    robot.phase("hold")
    robot.wait(3.6)
