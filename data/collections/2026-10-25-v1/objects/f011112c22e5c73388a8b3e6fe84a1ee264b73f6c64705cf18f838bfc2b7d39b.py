import math
import numpy as np


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


def compute_grip_force(mass_kg, peak_acc=1.0):
    """
    2 * mu * N >= safety * m * (g + a)
    With mu = 0.60 and safety = 1.95:
    """
    g = 9.81
    mu = 0.60
    safety = 1.95
    n_req = (safety * mass_kg * (g + peak_acc)) / (2.0 * mu)
    return clamp(n_req + 45.0, 120.0, 900.0)


def build_posture_targets(joint_names, waist_pitch=None, hip_pitch_delta=None, ankle_pitch_delta=None, current_q=None):
    """
    Safely build a posture dict matching only joint names present on the robot.
    """
    targets = {}
    name_set = set(joint_names)
    q_map = {}
    if current_q is not None and len(current_q) == len(joint_names):
        q_map = dict(zip(joint_names, [float(v) for v in current_q]))

    if waist_pitch is not None:
        for cand in ("waist_pitch_joint", "waist_pitch", "torso_pitch_joint", "torso_pitch", "back_pitch"):
            if cand in name_set:
                targets[cand] = float(waist_pitch)

    if hip_pitch_delta is not None and q_map:
        for cand in ("left_hip_pitch_joint", "right_hip_pitch_joint", "left_hip_pitch", "right_hip_pitch"):
            if cand in q_map:
                targets[cand] = q_map[cand] + float(hip_pitch_delta)

    if ankle_pitch_delta is not None and q_map:
        for cand in ("left_ankle_pitch_joint", "right_ankle_pitch_joint", "left_ankle_pitch", "right_ankle_pitch"):
            if cand in q_map:
                targets[cand] = q_map[cand] + float(ankle_pitch_delta)

    return targets


def run(robot):
    m = float(robot.box_mass_kg)
    # Smooth normalized mass schedule alpha in [0.0, 1.0] across 5..40 kg
    alpha = clamp((m - 5.0) / 35.0, 0.0, 1.0)

    joint_names = list(robot.joint_names())
    box_pos_init, _ = robot.box_pose()
    box_x0, box_y0, box_z0 = float(box_pos_init[0]), float(box_pos_init[1]), float(box_pos_init[2])
    bx_depth, by_width, bz_height = (
        float(robot.box_size[0]),
        float(robot.box_size[1]),
        float(robot.box_size[2]),
    )

    # ------------------------------------------------------------------
    # Phase 1: Squat down and pre-position hands wide around the box
    # ------------------------------------------------------------------
    robot.phase("1_approach_squat")

    # Deeper squat for heavier masses to share load across knees and hips
    squat_depth = 0.22 + 0.04 * alpha
    squat_dur = 1.5 + 0.8 * alpha
    robot.squat(squat_depth, squat_dur)

    # Read box center in the current pelvis frame after squatting
    box_pos_crouch, _ = robot.box_pose()
    box_in_pelvis = robot.world_to_pelvis_frame(box_pos_crouch)
    bx_p, by_p, bz_p = float(box_in_pelvis[0]), float(box_in_pelvis[1]), float(box_in_pelvis[2])

    # Target slightly below box vertical CoM for stable grasp
    grasp_z = bz_p - 0.015
    grasp_x = clamp(bx_p, 0.16, 0.34)

    # Pre-position palms outside the box width before closing in
    half_w_pre = 0.5 * by_width + 0.05
    left_pre = [grasp_x, by_p + half_w_pre, grasp_z + 0.025]
    right_pre = [grasp_x, by_p - half_w_pre, grasp_z + 0.025]
    robot.hands_to(left_pre, right_pre, 0.9 + 0.35 * alpha)

    # ------------------------------------------------------------------
    # Phase 2: Align palms flush with box sides and make contact
    # ------------------------------------------------------------------
    robot.phase("2_grasp_align")

    box_pos_crouch, _ = robot.box_pose()
    box_in_pelvis = robot.world_to_pelvis_frame(box_pos_crouch)
    bx_p, by_p, bz_p = float(box_in_pelvis[0]), float(box_in_pelvis[1]), float(box_in_pelvis[2])

    grasp_x = clamp(bx_p, 0.16, 0.34)
    grasp_z = bz_p - 0.015
    # Slight inward bias so palms press squarely against the box walls
    half_w_contact = max(0.075, 0.5 * by_width - 0.014)

    left_grasp = [grasp_x, by_p + half_w_contact, grasp_z]
    right_grasp = [grasp_x, by_p - half_w_contact, grasp_z]
    robot.hands_to(left_grasp, right_grasp, 0.75 + 0.30 * alpha)

    # ------------------------------------------------------------------
    # Phase 3: Squeeze preload before liftoff
    # ------------------------------------------------------------------
    robot.phase("3_squeeze_preload")

    lift_total_dur = 2.2 + 3.2 * alpha
    peak_acc_est = clamp(4.0 / (lift_total_dur ** 2), 0.25, 1.2)
    grip_force = compute_grip_force(m, peak_acc=peak_acc_est)

    # Two-stage squeeze ramp to build normal force cleanly before vertical motion
    robot.squeeze(0.65 * grip_force)
    robot.wait(0.20)
    robot.squeeze(grip_force)
    robot.wait(0.25)

    # ------------------------------------------------------------------
    # Phase 4: Staged Lift & CoM Retraction
    # ------------------------------------------------------------------
    # Stage 4a: Liftoff and immediate retraction toward torso to shrink moment arm
    robot.phase("4a_liftoff_retract")

    stage1_dur = 0.45 * lift_total_dur
    stage2_dur = 0.55 * lift_total_dur

    # Pull box much closer to pelvis as mass increases to keep CoM inside support polygon
    retract_x_mid = clamp(grasp_x - (0.05 + 0.04 * alpha), 0.15, 0.22 - 0.04 * alpha)
    lift_z_mid = grasp_z + 0.16
    half_w_hold = max(0.07, 0.5 * by_width - 0.018)

    left_mid = [retract_x_mid, by_p + half_w_hold, lift_z_mid]
    right_mid = [retract_x_mid, by_p - half_w_hold, lift_z_mid]
    robot.hands_to(left_mid, right_mid, stage1_dur * 0.65)

    # Apply subtle backward waist/hip posture adjustment for heavier loads if joints exist
    posture_mid = build_posture_targets(
        joint_names,
        waist_pitch=-0.08 * alpha,
        current_q=robot.q(),
    )
    if posture_mid:
        robot.set_posture(posture_mid, 0.35 + 0.25 * alpha)

    # Rise to a partial squat depth first while load is close to body
    mid_squat_depth = 0.08 + 0.02 * alpha
    robot.squat(mid_squat_depth, stage1_dur)

    if robot.hand_box_slip() > 0.008:
        grip_force = clamp(grip_force * 1.20, 140.0, 900.0)
        robot.squeeze(grip_force)

    # Stage 4b: Stand up fully and raise box to target hold height (>= +0.45 m)
    robot.phase("4b_stand_and_raise")

    robot.squat(0.0, stage2_dur)

    # Apply standing counter-lean via waist/hip pitch for heavy boxes to keep CoM centered
    posture_stand = build_posture_targets(
        joint_names,
        waist_pitch=-0.11 * alpha,
        current_q=robot.q(),
    )
    if posture_stand:
        robot.set_posture(posture_stand, 0.40 + 0.30 * alpha)

    # Measure current box rise and command final arm height to comfortably exceed 0.45 m
    box_pos_now, _ = robot.box_pose()
    current_lift = float(box_pos_now[2]) - box_z0
    target_total_lift = 0.53  # 0.08 m safety margin above 0.45 m threshold
    extra_z_needed = max(0.08, target_total_lift - current_lift)

    retract_x_final = clamp(0.19 - 0.05 * alpha, 0.14, 0.20)
    lift_z_final = clamp(lift_z_mid + extra_z_needed, 0.08, 0.28)

    left_final = [retract_x_final, by_p + half_w_hold, lift_z_final]
    right_final = [retract_x_final, by_p - half_w_hold, lift_z_final]
    robot.hands_to(left_final, right_final, 0.90 + 0.65 * alpha)

    # Check slip and height once more before entering the 3+ second hold
    if robot.hand_box_slip() > 0.008:
        grip_force = clamp(grip_force * 1.18, 150.0, 900.0)
        robot.squeeze(grip_force)

    box_pos_check, _ = robot.box_pose()
    if (float(box_pos_check[2]) - box_z0) < 0.48:
        boost_z = clamp(lift_z_final + 0.06, 0.10, 0.32)
        robot.hands_to(
            [retract_x_final, by_p + half_w_hold, boost_z],
            [retract_x_final, by_p - half_w_hold, boost_z],
            0.70 + 0.30 * alpha,
        )

    # ------------------------------------------------------------------
    # Phase 5: Hold steady for >= 3.5 s while monitoring slip
    # ------------------------------------------------------------------
    robot.phase("5_hold")

    hold_duration = 3.8
    step_dt = 0.25
    elapsed = 0.0

    while elapsed < hold_duration:
        if robot.hand_box_slip() > 0.010:
            grip_force = clamp(grip_force * 1.15, 150.0, 900.0)
            robot.squeeze(grip_force)
        robot.wait(step_dt)
        elapsed += step_dt
