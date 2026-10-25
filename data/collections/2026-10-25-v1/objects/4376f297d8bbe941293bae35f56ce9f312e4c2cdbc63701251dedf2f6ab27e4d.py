import math
import numpy as np


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


def compute_grip_force(mass_kg, peak_acc=1.2):
    """
    2 * mu * N >= safety * m * (g + a)
    Assuming mu = 0.6, safety = 1.8 -> N = 1.5 * m * (g + a) + margin.
    """
    g = 9.81
    mu = 0.60
    safety = 1.85
    n_req = (safety * mass_kg * (g + peak_acc)) / (2.0 * mu)
    return clamp(n_req + 35.0, 110.0, 850.0)


def run(robot):
    m = float(robot.box_mass_kg)
    # Normalized mass factor alpha in [0.0, 1.0] for m in [5, 40] kg
    alpha = clamp((m - 5.0) / 35.0, 0.0, 1.0)

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

    # Deeper squat for heavier loads to keep torso more upright and share load on knees
    squat_depth = 0.21 + 0.03 * alpha
    squat_dur = 1.4 + 0.6 * alpha
    # Modest forward pitch at bottom of squat to reach the box without excessive stoop
    crouch_pitch = 0.10 - 0.02 * alpha

    robot.squat(depth_m=squat_depth, duration_s=squat_dur, torso_pitch=crouch_pitch)

    # Read box center in the current pelvis frame after squatting
    box_pos_crouch, _ = robot.box_pose()
    box_in_pelvis = robot.world_to_pelvis_frame(box_pos_crouch)
    bx_p, by_p, bz_p = float(box_in_pelvis[0]), float(box_in_pelvis[1]), float(box_in_pelvis[2])

    # Target slightly below box vertical CoM for secure lifting leverage
    grasp_z = bz_p - 0.015
    grasp_x = clamp(bx_p, 0.18, 0.36)

    # Pre-position palms just outside the box width
    half_w_pre = 0.5 * by_width + 0.055
    left_pre = [grasp_x, by_p + half_w_pre, grasp_z + 0.03]
    right_pre = [grasp_x, by_p - half_w_pre, grasp_z + 0.03]
    robot.hands_to(left_pre, right_pre, duration_s=0.9 + 0.3 * alpha)

    # ------------------------------------------------------------------
    # Phase 2: Align palms flush with box sides and contact
    # ------------------------------------------------------------------
    robot.phase("2_grasp_align")

    # Refresh box pose in pelvis frame
    box_pos_crouch, _ = robot.box_pose()
    box_in_pelvis = robot.world_to_pelvis_frame(box_pos_crouch)
    bx_p, by_p, bz_p = float(box_in_pelvis[0]), float(box_in_pelvis[1]), float(box_in_pelvis[2])

    grasp_x = clamp(bx_p, 0.18, 0.36)
    grasp_z = bz_p - 0.015
    # Slight inward penetration bias so IK drives palms firmly against the sides
    half_w_contact = max(0.08, 0.5 * by_width - 0.012)

    left_grasp = [grasp_x, by_p + half_w_contact, grasp_z]
    right_grasp = [grasp_x, by_p - half_w_contact, grasp_z]
    robot.hands_to(left_grasp, right_grasp, duration_s=0.75 + 0.25 * alpha)

    # ------------------------------------------------------------------
    # Phase 3: Squeeze preload before liftoff
    # ------------------------------------------------------------------
    robot.phase("3_squeeze_preload")

    # Estimate peak upward acceleration from planned lift duration
    lift_total_dur = 2.0 + 2.6 * alpha
    peak_acc_est = clamp(1.8 / (lift_total_dur ** 2) * 2.5, 0.4, 1.5)
    grip_force = compute_grip_force(m, peak_acc=peak_acc_est)

    # Ramp squeeze in two steps for heavier loads to avoid contact impulse
    robot.squeeze(0.65 * grip_force)
    robot.wait(0.20)
    robot.squeeze(grip_force)
    robot.wait(0.25)

    # ------------------------------------------------------------------
    # Phase 4: Staged Lift & CoM Retraction
    # ------------------------------------------------------------------
    # Stage 4a: Liftoff and pull box closer to pelvis to reduce moment arm
    robot.phase("4a_liftoff_retract")

    stage1_dur = 0.45 * lift_total_dur
    stage2_dur = 0.55 * lift_total_dur

    # Retract box toward body (smaller x in pelvis frame) and raise relative to pelvis
    # Target final box height needs >= +0.45 m above initial box_z0.
    # Standing recovers ~squat_depth (0.21-0.24 m), so arms raise the box an additional ~0.30-0.34 m.
    retract_x_mid = clamp(grasp_x - 0.045, 0.19, 0.26)
    lift_z_mid = grasp_z + 0.15

    # Inward y squeeze bias on IK targets to help maintain normal force as arms move
    half_w_hold = max(0.07, 0.5 * by_width - 0.018)

    left_mid = [retract_x_mid, by_p + half_w_hold, lift_z_mid]
    right_mid = [retract_x_mid, by_p - half_w_hold, lift_z_mid]
    robot.hands_to(left_mid, right_mid, duration_s=stage1_dur * 0.65)

    # Counter-pitch torso backward as mass increases to keep combined CoM over feet
    # Combined CoM shift ~ m * x_box / (m_robot + m)
    mid_squat_depth = 0.09 + 0.02 * alpha
    mid_pitch = 0.02 - 0.06 * alpha
    robot.squat(depth_m=mid_squat_depth, duration_s=stage1_dur, torso_pitch=mid_pitch)

    # Check slip after liftoff and boost grip if needed
    if robot.hand_box_slip() > 0.012:
        grip_force = clamp(grip_force * 1.20, 120.0, 900.0)
        robot.squeeze(grip_force)

    # Stage 4b: Stand up fully and bring box to high close-hold position
    robot.phase("4b_stand_and_raise")

    # Stand fully (depth=0.0) with planned backward counter-lean for heavy boxes
    stand_pitch = -0.01 - 0.085 * alpha
    robot.squat(depth_m=0.0, duration_s=stage2_dur, torso_pitch=stand_pitch)

    # Check actual box height and compute final hand Z in pelvis frame to guarantee > 0.45 m lift
    box_pos_now, _ = robot.box_pose()
    current_lift = float(box_pos_now[2]) - box_z0
    target_total_lift = 0.52  # 0.07 m margin above the 0.45 m requirement
    extra_z_needed = max(0.08, target_total_lift - current_lift)

    retract_x_final = clamp(retract_x_mid - 0.02, 0.18, 0.23)
    lift_z_final = clamp(lift_z_mid + extra_z_needed, 0.06, 0.26)

    left_final = [retract_x_final, by_p + half_w_hold, lift_z_final]
    right_final = [retract_x_final, by_p - half_w_hold, lift_z_final]
    robot.hands_to(left_final, right_final, duration_s=0.85 + 0.55 * alpha)

    # Verify height one more time; if slightly short, raise hands a bit further
    box_pos_check, _ = robot.box_pose()
    if (float(box_pos_check[2]) - box_z0) < 0.475:
        boost_z = clamp(lift_z_final + 0.06, 0.08, 0.30)
        robot.hands_to(
            [retract_x_final, by_p + half_w_hold, boost_z],
            [retract_x_final, by_p - half_w_hold, boost_z],
            duration_s=0.65,
        )

    # ------------------------------------------------------------------
    # Phase 5: Hold steady for >= 3.5 s while monitoring slip & CoM
    # ------------------------------------------------------------------
    robot.phase("5_hold")

    hold_duration = 3.8
    step_dt = 0.25
    elapsed = 0.0

    while elapsed < hold_duration:
        if robot.hand_box_slip() > 0.015:
            grip_force = clamp(grip_force * 1.15, 120.0, 900.0)
            robot.squeeze(grip_force)
        robot.wait(step_dt)
        elapsed += step_dt
