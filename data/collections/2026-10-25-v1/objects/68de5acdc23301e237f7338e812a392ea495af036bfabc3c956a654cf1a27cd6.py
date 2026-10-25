import math

def run(robot):
    m = robot.box_mass_kg
    robot.phase("approach")
    robot.squat(0.25, 2.0)
    robot.hands_to((0.35, 0.2, -0.2), (0.35, -0.2, -0.2), 1.5)
    robot.phase("grip")
    robot.squeeze(1.8 * m * 9.81 / (2 * 0.6))
    robot.wait(0.5)
    robot.phase("lift")
    robot.squat(0.0, 3.0)
    robot.phase("hold")
    robot.wait(3.5)
