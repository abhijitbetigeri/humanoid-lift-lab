"""Generates the VISUAL SECTION of sim/g1/scene_lift.xml (W2). Re-run after editing:
    .venv/bin/python viz/assets/gen_scene_visual.py
Only the text between the VISUAL SECTION markers is replaced; the PHYSICS SECTION is untouched.
All decor geoms have contype=0 conaffinity=0 (never touch physics).
"""
import os
import re

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCENE = os.path.join(ROOT, "sim", "g1", "scene_lift.xml")
rng = np.random.default_rng(7)

D = 'contype="0" conaffinity="0" group="1"'
geoms = []


def box(pos, half, mat, euler=None, extra=""):
    e = f' euler="{euler[0]:.3f} {euler[1]:.3f} {euler[2]:.3f}"' if euler else ""
    geoms.append(f'<geom type="box" pos="{pos[0]:.3f} {pos[1]:.3f} {pos[2]:.3f}" '
                 f'size="{half[0]:.3f} {half[1]:.3f} {half[2]:.3f}" material="{mat}"{e} {D}{extra}/>')


def pallet(cx, cy, z0, yaw=0.0):
    """EUR-ish pallet 1.2 x 0.8 x 0.144, long axis along local x."""
    c, s = np.cos(yaw), np.sin(yaw)

    def P(lx, ly, lz):
        return (cx + c * lx - s * ly, cy + s * lx + c * ly, z0 + lz)

    eu = (0, 0, yaw)
    for ly in (-0.35, 0.0, 0.35):  # blocks + stringers
        for lx in (-0.53, 0.0, 0.53):
            box(P(lx, ly, 0.039), (0.07, 0.05, 0.039), "wood", eu)
        box(P(0, ly, 0.089), (0.6, 0.05, 0.011), "wood", eu)
    for lx in np.linspace(-0.55, 0.55, 7):  # top deck boards
        box(P(lx, 0, 0.133), (0.05, 0.4, 0.011), "wood", eu)
    return z0 + 0.144


def carton_stack(cx, cy, z0, yaw, layers, mat="cardboard", full=1.0):
    c, s = np.cos(yaw), np.sin(yaw)
    for k in range(layers):
        for i, lx in enumerate((-0.3, 0.3)):
            for j, ly in enumerate((-0.2, 0.2)):
                if rng.random() > full and k == layers - 1:
                    continue
                jit = rng.normal(0, 0.008, 2)
                h = 0.15
                x = cx + c * (lx + jit[0]) - s * (ly + jit[1])
                y = cy + s * (lx + jit[0]) + c * (ly + jit[1])
                box((x, y, z0 + h + 2 * h * k), (0.29, 0.19, h - 0.002), mat,
                    (0, 0, yaw + rng.normal(0, 0.02)))


def rack_run(x0, y0, length, depth, along, n_bays, levels=(0.12, 1.15, 2.2), height=3.1):
    """Selective pallet racking: blue uprights, orange beams. along='y' or 'x'."""
    bay = length / n_bays
    for b in range(n_bays + 1):
        a = -length / 2 + b * bay
        for dd in (-depth / 2, depth / 2):
            p = (x0 + dd, y0 + a, height / 2) if along == "y" else (x0 + a, y0 + dd, height / 2)
            box(p, (0.045, 0.045, height / 2), "rack_upright")
        # frame bracing
        for z in np.arange(0.4, height, 0.7):
            p = (x0, y0 + a, z) if along == "y" else (x0 + a, y0, z)
            h = (depth / 2, 0.012, 0.012) if along == "y" else (0.012, depth / 2, 0.012)
            box(p, h, "rack_upright")
    for b in range(n_bays):
        a = -length / 2 + (b + 0.5) * bay
        for lz in levels:
            for dd in (-depth / 2, depth / 2):
                p = (x0 + dd, y0 + a, lz + 0.06) if along == "y" else (x0 + a, y0 + dd, lz + 0.06)
                h = (0.03, bay / 2 - 0.05, 0.06) if along == "y" else (bay / 2 - 0.05, 0.03, 0.06)
                box(p, h, "rack_beam")
            r = rng.random()
            if r < 0.15 and lz > 0.5:
                continue  # empty slot
            yaw = np.pi / 2 if along == "x" else 0.0
            for off in ((-bay / 4,) if bay < 2.0 else (-bay / 4, bay / 4)):
                cxp, cyp = (x0, y0 + a + off) if along == "y" else (x0 + a + off, y0)
                top = pallet(cxp, cyp, lz + 0.12, yaw=yaw + np.pi / 2 if along == "y" else 0.0)
                layers = int(rng.integers(1, 3)) if lz < 2.0 else 2
                carton_stack(cxp, cyp, top, yaw + np.pi / 2 if along == "y" else 0.0, layers,
                             mat="wrap" if rng.random() < 0.3 else "cardboard", full=0.85)


# ---------- layout ----------
# back racking (behind the robot, -x) and side racking (+y)
rack_run(-3.5, 0.0, 7.2, 1.0, "y", 4)
rack_run(0.2, 3.6, 5.4, 1.0, "x", 3)
# floor pallet stacks outside the cell
top = pallet(1.9, 1.8, 0.0, yaw=0.3)
carton_stack(1.9, 1.8, top, 0.3, 3, full=0.7)
top = pallet(-1.7, -2.1, 0.0, yaw=-0.15)
carton_stack(-1.7, -2.1, top, -0.15, 2, mat="wrap")
top = pallet(-1.75, -2.1, 0.0 + 0.0, yaw=-0.15)
# empty pallets stacked
for k in range(4):
    pallet(2.6, -1.9, 0.144 * k, yaw=1.4 + rng.normal(0, 0.03))

# safety tape around the work cell
X0, X1, Y0, Y1, W = -0.85, 1.35, -1.15, 1.15, 0.05
tz = 0.0012
box(((X0 + X1) / 2, Y0, tz), ((X1 - X0) / 2 + W, W, 0.001), "hazard_x")
box(((X0 + X1) / 2, Y1, tz), ((X1 - X0) / 2 + W, W, 0.001), "hazard_x")
box((X0, 0, tz), (W, (Y1 - Y0) / 2 - W, 0.001), "hazard_y")
box((X1, 0, tz), (W, (Y1 - Y0) / 2 - W, 0.001), "hazard_y")
# white lane lines along the aisle
box((0.25, -2.6, tz), (4.5, 0.04, 0.001), "lane")
box((0.25, 2.35, tz), (3.0, 0.04, 0.001), "lane")

# building walls (no empty void in any view)
box((-4.6, 0, 3.5), (0.1, 8, 3.5), "wall")
box((0, 5.0, 3.5), (8, 0.1, 3.5), "wall")
box((0, -7.5, 3.5), (8, 0.1, 3.5), "wall")
box((7.5, 0, 3.5), (0.1, 8, 3.5), "wall")
box((-4.49, 0, 0.6), (0.01, 8, 0.6), "wall_band")
box((0, 4.89, 0.6), (8, 0.01, 0.6), "wall_band")
box((0, -7.39, 0.6), (8, 0.01, 0.6), "wall_band")
box((7.39, 0, 0.6), (0.01, 8, 0.6), "wall_band")
# ceiling + light fixtures
box((0, 0, 7.0), (8, 8, 0.05), "ceiling")
for x in (-2.5, 0.5, 3.5):
    for y in (-3.0, 0.0, 3.0):
        box((x, y, 6.9), (0.6, 0.12, 0.03), "lamp")

DECOR = "\n    ".join(geoms)

# tote decor: a mocap body that render.py snaps onto the box pose each frame (no physics)
hx, hy, hz = 0.15, 0.20, 0.15
td = []


def tbox(p, h, mat):
    td.append(f'<geom type="box" pos="{p[0]:.4f} {p[1]:.4f} {p[2]:.4f}" size="{h[0]:.4f} {h[1]:.4f} {h[2]:.4f}" '
              f'material="{mat}" {D}/>')


o = 0.004
# rolled top rim
tbox((0, hy + o, hz - 0.012), (hx + o, o, 0.012), "tote_rim")
tbox((0, -hy - o, hz - 0.012), (hx + o, o, 0.012), "tote_rim")
tbox((hx + o, 0, hz - 0.012), (o, hy + 2 * o, 0.012), "tote_rim")
tbox((-hx - o, 0, hz - 0.012), (o, hy + 2 * o, 0.012), "tote_rim")
# horizontal ribs on all faces
for z in (-0.09, -0.03):
    tbox((0, hy + 0.002, z), (hx - 0.01, 0.002, 0.006), "tote_rib")
    tbox((0, -hy - 0.002, z), (hx - 0.01, 0.002, 0.006), "tote_rib")
    tbox((hx + 0.002, 0, z), (0.002, hy - 0.01, 0.006), "tote_rib")
    tbox((-hx - 0.002, 0, z), (0.002, hy - 0.01, 0.006), "tote_rib")
# hand-hold slots on the short (x) faces, label plate on +x face
tbox((hx + 0.0015, 0, 0.085), (0.0015, 0.06, 0.018), "tote_slot")
tbox((-hx - 0.0015, 0, 0.085), (0.0015, 0.06, 0.018), "tote_slot")
tbox((hx + 0.0025, 0.0, 0.03), (0.001, 0.07, 0.022), "tote_label")
# open-top look: dark interior inset just under the top face
tbox((0, 0, hz + 0.0005), (hx - 0.012, hy - 0.012, 0.0005), "tote_inside")
TOTE = "\n      ".join(td)

SECTION = f"""<!-- ===== VISUAL SECTION (W2) ===== -->
  <!-- generated by viz/assets/gen_scene_visual.py; edit that script and re-run -->
  <statistic extent="4" center="0.3 0 0.8"/>
  <visual>
    <global offwidth="1920" offheight="1080" azimuth="150" elevation="-15" fovy="40"/>
    <quality shadowsize="8192" offsamples="8"/>
    <map fogstart="4" fogend="14" haze="0.4" znear="0.02" zfar="30" shadowclip="1.5" shadowscale="0.6"/>
    <rgba fog="0.62 0.63 0.65 1" haze="0.75 0.76 0.78 1"/>
    <headlight diffuse="0.08 0.08 0.08" ambient="0.17 0.17 0.18" specular="0.02 0.02 0.02"/>
  </visual>
  <asset>
    <texture type="skybox" builtin="gradient" rgb1="0.72 0.73 0.75" rgb2="0.45 0.46 0.48" width="512" height="3072"/>
    <texture name="concrete" type="2d" file="../../viz/assets/concrete.png"/>
    <texture name="hazard" type="2d" file="../../viz/assets/hazard.png"/>
    <texture name="wallt" type="2d" file="../../viz/assets/wall.png"/>
    <texture name="cardboard" type="2d" file="../../viz/assets/cardboard.png"/>
    <texture name="wood" type="2d" file="../../viz/assets/wood.png"/>
    <material name="floor" texture="concrete" rgba="0.62 0.62 0.62 1" texrepeat="0.25 0.25" texuniform="true" reflectance="0.03"
              specular="0.15" shininess="0.2"/>
    <material name="tote" rgba="0.10 0.36 0.70 1" specular="0.35" shininess="0.35"/>
    <material name="tote_rim" rgba="0.08 0.30 0.60 1" specular="0.35" shininess="0.35"/>
    <material name="tote_rib" rgba="0.095 0.345 0.68 1" specular="0.3" shininess="0.3"/>
    <material name="tote_slot" rgba="0.03 0.04 0.06 1" specular="0"/>
    <material name="tote_label" rgba="0.95 0.95 0.92 1" specular="0.1"/>
    <material name="tote_inside" rgba="0.05 0.13 0.26 1" specular="0.1"/>
    <material name="hazard_x" texture="hazard" texrepeat="9 1" specular="0.1"/>
    <material name="hazard_y" texture="hazard" texrepeat="9 1" specular="0.1"/>
    <material name="lane" rgba="0.85 0.85 0.82 1" specular="0.05"/>
    <material name="wall" texture="wallt" texrepeat="6 3" rgba="1 1 1 1" specular="0.05" emission="0.35"/>
    <material name="wall_band" rgba="0.30 0.33 0.36 1" specular="0.05" emission="0.3"/>
    <material name="ceiling" rgba="0.55 0.56 0.58 1" specular="0" emission="0.3"/>
    <material name="lamp" rgba="1 1 0.96 1" emission="1"/>
    <material name="rack_upright" rgba="0.10 0.24 0.52 1" specular="0.4" shininess="0.5"/>
    <material name="rack_beam" rgba="0.92 0.42 0.08 1" specular="0.4" shininess="0.5"/>
    <material name="wood" texture="wood" rgba="1 1 1 1" specular="0.05"/>
    <material name="cardboard" texture="cardboard" texrepeat="1 1" rgba="1 1 1 1" specular="0.05"/>
    <material name="wrap" rgba="0.80 0.82 0.84 1" specular="0.6" shininess="0.8" reflectance="0.02"/>
  </asset>
  <worldbody>
    <!-- 3-point lighting: warm key (soft shadows), cool fill, rim from behind -->
    <light name="key" type="spot" pos="2.6 -2.2 4.2" dir="-0.48 0.40 -0.78" cutoff="45" exponent="2"
           castshadow="true" bulbradius="0.25" diffuse="0.72 0.69 0.64" specular="0.25 0.25 0.25" attenuation="1 0 0"/>
    <light name="fill" type="directional" pos="2.0 3.0 2.6" dir="-0.4 -0.7 -0.6"
           castshadow="false" diffuse="0.28 0.31 0.36" specular="0 0 0"/>
    <light name="rim" type="directional" pos="-2.0 0.6 3.6" dir="0.55 -0.15 -0.82"
           castshadow="false" diffuse="0.45 0.47 0.52" specular="0.4 0.4 0.4"/>
    <light name="hall" type="directional" pos="0 0 6" dir="0.1 0.2 -1" castshadow="false"
           diffuse="0.14 0.14 0.14" specular="0 0 0"/>
    {DECOR}
    <body name="tote_decor" mocap="true" pos="0.42 0 0.15">
      {TOTE}
    </body>
  </worldbody>
  <!-- ===== END VISUAL SECTION ===== -->"""

src = open(SCENE).read()
new = re.sub(r"<!-- ===== VISUAL SECTION \(W2\) ===== -->.*?<!-- ===== END VISUAL SECTION ===== -->",
             lambda _: SECTION, src, count=1, flags=re.S)
assert new != src or SECTION in src
open(SCENE, "w").write(new)
print("visual section:", len(geoms), "decor geoms,", len(td), "tote decor geoms")
