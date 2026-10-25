"""Replay renderer for traj.npz (W2). Replay only: mj_forward per frame, no physics.

    render_traj(traj_npz, out_mp4, camera="hero", hud=True, size=(1280,720), fps=30, title=None)
    render_grid(traj_npz, out_mp4, size=(1280,480), fps=30, title=None)   # hero | side, the critic format
    render_still(traj_npz, out_png, camera="hero", frame=-1, ...)

CLI:
    .venv/bin/python sim/render.py runs/x/traj.npz out.mp4 [--camera hero|side|hands|grid] [--no-hud]
        [--title "Round 3 · 30 kg"] [--size 1280x720] [--fps 30] [--still out.png --frame 120]
If result.json sits next to the npz, a PASS/FAIL stamp is shown at the end.
"""
import argparse
import json
import os
import time as _time

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.join(HERE, "g1", "scene_lift.xml")
END_HOLD_S = 1.6  # frozen tail with the PASS/FAIL stamp
TOTE_DESIGN_HALF = (0.15, 0.20, 0.15)  # half-size the tote decor in scene_lift.xml was authored for

# ---------------------------------------------------------------- fonts
_FONT_CANDIDATES = [
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_font_cache = {}


def font(size, weight="Regular"):
    key = (int(size), weight)
    if key in _font_cache:
        return _font_cache[key]
    f = None
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, int(size))
                try:
                    f.set_variation_by_name(weight)
                except Exception:
                    pass
                break
            except Exception:
                continue
    if f is None:
        try:
            f = ImageFont.load_default(size=int(size))
        except TypeError:
            f = ImageFont.load_default()
    _font_cache[key] = f
    return f


# ---------------------------------------------------------------- data
def load_traj(traj_npz):
    z = np.load(traj_npz, allow_pickle=True)
    T = z["qpos"].shape[0]

    def get(k, default):
        return np.asarray(z[k]) if k in z.files else default

    tr = {
        "qpos": z["qpos"],
        "time": get("time", np.arange(T) / 30.0),
        "box_mass": float(get("box_mass", np.float64(np.nan))),
        "assist_force": get("assist_force", np.zeros(T)),
        "tau_frac": get("tau_frac", None),
        "com_margin": get("com_margin", np.full(T, np.nan)),
        "box_slip": get("box_slip", np.zeros(T)),
        "phase": [str(p) for p in get("phase", np.array([""] * T))],
    }
    # after a fall the scorer has already decided FAIL, and the limp arms can go numerically unstable; show only
    # 1.5 s past the fall (pelvis z is qpos[2], same FALL_Z = 0.45 m as sim/trial.py)
    fell = np.where(tr["qpos"][:, 2] < 0.45)[0]
    if len(fell):
        cut = int(np.searchsorted(tr["time"], tr["time"][fell[0]] + 1.5))
        for k in ("qpos", "time", "assist_force", "tau_frac", "com_margin", "box_slip"):
            if tr[k] is not None and len(tr[k]) > cut:
                tr[k] = tr[k][:cut]
        tr["phase"] = tr["phase"][:cut]
    if tr["assist_force"].ndim > 1:  # tolerate a 3-vector per frame
        tr["assist_force"] = np.linalg.norm(tr["assist_force"], axis=-1)
    res_path = os.path.join(os.path.dirname(os.path.abspath(traj_npz)), "result.json")
    tr["result"] = None
    if os.path.exists(res_path):
        try:
            tr["result"] = json.load(open(res_path))
        except Exception:
            pass
    return tr


class Scene:
    def __init__(self, width, height):
        self.m = mujoco.MjModel.from_xml_path(SCENE)
        m = self.m
        if os.environ.get("RENDER_FAST"):  # RENDER_FAST=1: cheaper AA + shadow map for quick previews
            m.vis.quality.offsamples = 2
            m.vis.quality.shadowsize = 2048
        m.vis.global_.offwidth = max(m.vis.global_.offwidth, width)
        m.vis.global_.offheight = max(m.vis.global_.offheight, height)
        self.d = mujoco.MjData(m)
        self.r = mujoco.Renderer(m, height=height, width=width)
        self.r.scene.flags[mujoco.mjtRndFlag.mjRND_FOG] = True
        self.r.scene.flags[mujoco.mjtRndFlag.mjRND_HAZE] = True
        self.vopt = mujoco.MjvOption()
        self.box_adr = m.jnt_qposadr[m.joint("box").id]
        b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "tote_decor")
        self.decor_mocap = m.body_mocapid[b] if b >= 0 else -1
        self.box_body = m.body("box").id
        self._fit_tote_decor()
        self.hand_bodies = [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, n)
                            for n in ("left_wrist_yaw_link", "right_wrist_yaw_link")]
        self.pelvis = m.body("pelvis").id
        # actuator index groups for torque bars
        names = [m.actuator(i).name for i in range(m.nu)]
        self.groups = []
        for label, keys in [("Hips", ("hip_",)), ("Knees", ("knee",)), ("Ankles", ("ankle",)),
                            ("Waist", ("waist",)), ("Shoulders", ("shoulder",)), ("Elbows", ("elbow",))]:
            idx = [i for i, n in enumerate(names) if any(k in n for k in keys)]
            if idx:
                self.groups.append((label, idx))

    def _fit_tote_decor(self):
        """Decor geoms were authored for a TOTE_DESIGN_HALF box; stretch them onto the real box geom."""
        m = self.m
        b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "tote_decor")
        if b < 0:
            return
        real = m.geom_size[m.geom("box").id].copy()
        dz = np.array(TOTE_DESIGN_HALF)
        for g in range(m.ngeom):
            if m.geom_bodyid[g] != b:
                continue
            p, sz = m.geom_pos[g].copy(), m.geom_size[g].copy()
            for k in range(3):
                if abs(p[k]) >= dz[k] - 0.03:  # sits on / near a face: shift with the face
                    p[k] += np.sign(p[k]) * (real[k] - dz[k])
                else:  # interior coordinate: scale
                    p[k] *= real[k] / dz[k]
                if sz[k] >= 0.5 * dz[k]:  # spans the face: stretch
                    sz[k] += real[k] - dz[k]
            m.geom_pos[g], m.geom_size[g] = p, sz
            m.geom_rbound[g] = float(np.linalg.norm(sz))

    def tint_tote(self, mass):
        """Tote colour by mass band: blue < 15 kg, amber 15-30 kg, red > 30 kg."""
        if not np.isfinite(mass):
            return
        if mass < 15:
            base = np.array([0.10, 0.36, 0.70])
        elif mass <= 30:
            base = np.array([0.88, 0.52, 0.06])
        else:
            base = np.array([0.72, 0.12, 0.10])
        for name, f in (("tote", 1.0), ("tote_rim", 0.85), ("tote_rib", 0.93), ("tote_inside", 0.4)):
            mid = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_MATERIAL, name)
            if mid >= 0:
                self.m.mat_rgba[mid, :3] = base * f

    def set_qpos(self, q):
        d = self.d
        d.qpos[:] = q
        if self.decor_mocap >= 0:
            a = self.box_adr
            d.mocap_pos[self.decor_mocap] = q[a:a + 3]
            d.mocap_quat[self.decor_mocap] = q[a + 3:a + 7]
        mujoco.mj_forward(self.m, self.d)

    def render(self, cam):
        self.r.update_scene(self.d, camera=cam, scene_option=self.vopt)
        return self.r.render()

    def close(self):
        try:
            self.r.close()
        except Exception:
            pass


# ---------------------------------------------------------------- cameras
def make_camera(kind, u, sc, state):
    """u in [0,1] = progress through the clip. state carries smoothing between frames."""
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    d = sc.d
    pel = d.xpos[sc.pelvis]
    if kind == "hero":
        cam.lookat[:] = [0.20, 0.0, 0.62]
        cam.distance = 2.75
        cam.azimuth = 144.0 + 10.0 * u  # gentle slow orbit
        cam.elevation = -8.0
    elif kind == "side":
        cam.lookat[:] = [0.15, 0.0, 0.66]
        cam.distance = 2.7
        cam.azimuth = 90.0  # camera at -y looking +y: robot faces right
        cam.elevation = -4.0
    elif kind == "hands":
        box = d.xpos[sc.box_body]
        hands = [d.xpos[b] for b in sc.hand_bodies if b >= 0]
        tgt = 0.6 * box + 0.4 * (np.mean(hands, axis=0) if hands else box)
        tgt = np.array([tgt[0], 0.0, tgt[2]])
        prev = state.get("hands")
        tgt = tgt if prev is None else prev + 0.15 * (tgt - prev)
        state["hands"] = tgt
        cam.lookat[:] = tgt
        cam.distance = 1.35
        cam.azimuth = 152.0
        cam.elevation = -22.0
    else:
        raise ValueError(f"unknown camera {kind!r}")
    return cam


# ---------------------------------------------------------------- HUD
GREEN = np.array([52, 199, 89])
AMBER = np.array([255, 179, 0])
RED = np.array([255, 59, 48])
WHITE = (255, 255, 255, 255)
DIM = (255, 255, 255, 165)
PANEL = (14, 16, 20, 165)


def ramp(x):
    """0 -> green, 0.5 -> amber, 1 -> red."""
    x = float(np.clip(x, 0, 1))
    c = GREEN + (AMBER - GREEN) * (x / 0.5) if x < 0.5 else AMBER + (RED - AMBER) * ((x - 0.5) / 0.5)
    return tuple(int(v) for v in c) + (255,)


def rpanel(dr, box, r):
    dr.rounded_rectangle(box, radius=r, fill=PANEL)


def bar(dr, x, y, w, h, frac, color, s):
    dr.rounded_rectangle((x, y, x + w, y + h), radius=h / 2, fill=(255, 255, 255, 40))
    f = float(np.clip(frac, 0, 1))
    if f > 0.01:
        dr.rounded_rectangle((x, y, x + max(h, w * f), y + h), radius=h / 2, fill=color)


def draw_hud(img, tr, i, sc, title=None, end_alpha=0.0, pane_labels=None):
    """img: PIL RGB. Returns PIL RGB with the HUD composited."""
    W, H = img.size
    s = H / 720.0
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    pad = int(22 * s)
    T = len(tr["time"])
    i = min(i, T - 1)

    # --- top-left: title + phase pill
    y = pad
    if title:
        f = font(30 * s, "Semibold")
        tw = dr.textlength(title, font=f)
        rpanel(dr, (pad, y, pad + tw + 28 * s, y + 48 * s), 12 * s)
        dr.text((pad + 14 * s, y + 24 * s), title, font=f, fill=WHITE, anchor="lm")
        y += 58 * s
    ph = tr["phase"][i].strip().upper() or "—"
    f = font(19 * s, "Semibold")
    lab = f"PHASE  {ph}"
    ttxt = f"{tr['time'][i]:5.1f} s"
    ft = font(17 * s)
    tw = dr.textlength(lab, font=f)
    tw2 = dr.textlength(ttxt, font=ft)
    rpanel(dr, (pad, y, pad + tw + tw2 + 62 * s, y + 36 * s), 18 * s)
    dr.ellipse((pad + 12 * s, y + 13 * s, pad + 22 * s, y + 23 * s), fill=(90, 200, 250, 255))
    dr.text((pad + 30 * s, y + 18 * s), lab, font=f, fill=WHITE, anchor="lm")
    dr.text((pad + tw + 48 * s, y + 18 * s), ttxt, font=ft, fill=DIM, anchor="lm")

    # --- top-right: tote mass (large)
    mass = tr["box_mass"]
    mtxt = f"{mass:.0f} kg" if np.isfinite(mass) else "? kg"
    fbig = font(64 * s, "Bold")
    fsm = font(14 * s, "Semibold")
    mw = max(dr.textlength(mtxt, font=fbig), 120 * s)
    x1 = W - pad
    x0 = x1 - mw - 40 * s
    rpanel(dr, (x0, pad, x1, pad + 110 * s), 16 * s)
    dr.text((x0 + 20 * s, pad + 22 * s), "TOTE MASS", font=fsm, fill=DIM, anchor="lm")
    dr.text((x1 - 20 * s, pad + 68 * s), mtxt, font=fbig, fill=WHITE, anchor="rm")

    # --- bottom-left: balance + assist + slip
    pw, phh = 330 * s, 168 * s
    x0, y0 = pad, H - pad - phh
    rpanel(dr, (x0, y0, x0 + pw, y0 + phh), 16 * s)
    fl, fv = font(14 * s, "Semibold"), font(20 * s, "Semibold")
    cx = x0 + 18 * s
    bw = pw - 36 * s
    cm = tr["com_margin"][i]
    yy = y0 + 22 * s
    dr.text((cx, yy), "BALANCE MARGIN", font=fl, fill=DIM, anchor="lm")
    if np.isfinite(cm):
        dr.text((cx + bw, yy), f"{cm * 100:+.1f} cm", font=fv, fill=WHITE, anchor="rm")
        frac = np.clip((cm + 0.04) / 0.14, 0, 1)  # -4 cm .. +10 cm
        bar(dr, cx, yy + 16 * s, bw, 10 * s, frac, ramp(1 - np.clip(cm / 0.08, 0, 1)), s)
        zx = cx + bw * (0.04 / 0.14)  # zero tick
        dr.line((zx, yy + 12 * s, zx, yy + 30 * s), fill=(255, 255, 255, 200), width=max(1, int(2 * s)))
    else:
        dr.text((cx + bw, yy), "n/a", font=fv, fill=DIM, anchor="rm")
    yy += 52 * s
    af = float(tr["assist_force"][i])
    dr.text((cx, yy), "BALANCE ASSIST", font=fl, fill=DIM, anchor="lm")
    dr.text((cx + bw, yy), f"{af:.0f} N", font=fv, fill=WHITE, anchor="rm")
    bar(dr, cx, yy + 16 * s, bw, 10 * s, af / 150.0, ramp(af / 150.0), s)
    yy += 52 * s
    sl = float(tr["box_slip"][i])
    dr.text((cx, yy), "BOX SLIP", font=fl, fill=DIM, anchor="lm")
    dr.text((cx + bw, yy), f"{sl * 1000:.0f} mm", font=fv, fill=WHITE, anchor="rm")
    bar(dr, cx, yy + 16 * s, bw, 10 * s, sl / 0.05, ramp(sl / 0.05), s)

    # --- bottom-right: torque bars
    tau = tr["tau_frac"]
    if tau is not None and sc is not None and tau.ndim == 2:
        rows = [(lab, float(np.max(tau[i, [j for j in idx if j < tau.shape[1]]])))
                for lab, idx in sc.groups if any(j < tau.shape[1] for j in idx)]
        rh = 27 * s
        phh = 40 * s + rh * len(rows)
        pw = 330 * s
        x1, y1 = W - pad, H - pad
        x0, y0 = x1 - pw, y1 - phh
        rpanel(dr, (x0, y0, x1, y1), 16 * s)
        dr.text((x0 + 18 * s, y0 + 20 * s), "JOINT TORQUE  / LIMIT", font=fl, fill=DIM, anchor="lm")
        for k, (lab, v) in enumerate(rows):
            yy = y0 + 46 * s + k * rh
            dr.text((x0 + 18 * s, yy), lab, font=font(16 * s), fill=WHITE, anchor="lm")
            bx = x0 + 112 * s
            bw2 = pw - 112 * s - 70 * s
            bar(dr, bx, yy - 5 * s, bw2, 10 * s, v, ramp(v), s)
            dr.text((x1 - 18 * s, yy), f"{v * 100:.0f}%", font=font(16 * s, "Semibold"),
                    fill=WHITE if v < 0.95 else tuple(RED) + (255,), anchor="rm")

    # --- pane labels (grid)
    if pane_labels:
        for (px, label) in pane_labels:
            f = font(14 * s, "Semibold")
            tw = dr.textlength(label, font=f)
            yb = pad + 120 * s
            rpanel(dr, (px - tw / 2 - 12 * s, yb, px + tw / 2 + 12 * s, yb + 26 * s), 13 * s)
            dr.text((px, yb + 13 * s), label, font=f, fill=WHITE, anchor="mm")

    out = Image.alpha_composite(img.convert("RGBA"), ov)

    # --- PASS / FAIL stamp
    res = tr.get("result")
    if res is not None and end_alpha > 0:
        ok = bool(res.get("success"))
        txt = "PASS" if ok else "FAIL"
        col = GREEN if ok else RED
        a = float(np.clip(end_alpha, 0, 1))
        st = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(st)
        sd.rectangle((0, 0, W, H), fill=(0, 0, 0, int(90 * a)))
        fb = font(150 * s, "Heavy")
        tw = sd.textlength(txt, font=fb)
        bw_, bh_ = tw + 90 * s, 200 * s
        cxm, cym = W / 2, H / 2 - 20 * s
        bx = (cxm - bw_ / 2, cym - bh_ / 2, cxm + bw_ / 2, cym + bh_ / 2)
        sd.rounded_rectangle(bx, radius=26 * s, fill=tuple(int(c) for c in col) + (int(215 * a),))
        sd.text((cxm, cym + 4 * s), txt, font=fb, fill=(255, 255, 255, int(255 * a)), anchor="mm")
        sub = res.get("fail_reason") or ""
        if ok:
            sub = f"lifted {res.get('box_rise_m', 0):.2f} m · held {res.get('held_s', 0):.1f} s"
        if sub:
            fsb = font(26 * s, "Semibold")
            sw = sd.textlength(sub, font=fsb)
            yb = cym + bh_ / 2 + 18 * s
            sd.rounded_rectangle((cxm - sw / 2 - 18 * s, yb, cxm + sw / 2 + 18 * s, yb + 46 * s), radius=14 * s,
                                 fill=(14, 16, 20, int(200 * a)))
            sd.text((cxm, yb + 23 * s), sub, font=fsb, fill=(255, 255, 255, int(255 * a)), anchor="mm")
        out = Image.alpha_composite(out, st)
    return out.convert("RGB")


# ---------------------------------------------------------------- video
class RenderError(RuntimeError):
    pass


def _tmp_path(out_mp4):
    """Write next to the target, then rename: a killed/failed render never leaves a stub at out_mp4.
    (An ffmpeg killed mid-write leaves a 48-byte ftyp+mdat header with no moov atom = unplayable.)"""
    out = os.path.abspath(out_mp4)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    base = out[:-4] if out.lower().endswith(".mp4") else out
    return f"{base}.writing-{os.getpid()}.mp4"


def _writer(out_mp4, fps):
    import imageio.v2 as imageio
    preset = os.environ.get("RENDER_PRESET", "veryfast")
    return imageio.get_writer(out_mp4, fps=fps, codec="libx264", quality=8, pixelformat="yuv420p",
                              macro_block_size=8, ffmpeg_log_level="error",
                              output_params=["-preset", preset, "-movflags", "+faststart"])


def _finish(tmp, out_mp4, expect_frames, size):
    """Verify the temp mp4 (decodable, frame count, size) and move it into place; raise otherwise."""
    import imageio_ffmpeg
    if not os.path.exists(tmp) or os.path.getsize(tmp) < 1024:
        raise RenderError(f"render produced no video ({os.path.getsize(tmp) if os.path.exists(tmp) else 0} bytes)")
    rd = imageio_ffmpeg.read_frames(tmp)
    meta = next(rd)
    rd.close()
    nfr, _ = imageio_ffmpeg.count_frames_and_secs(tmp)
    if tuple(meta["size"]) != tuple(size):
        raise RenderError(f"video size {meta['size']} != requested {size}")
    if abs(nfr - expect_frames) > 1:
        raise RenderError(f"video has {nfr} frames, expected {expect_frames}")
    os.replace(tmp, out_mp4)
    return nfr


def _check_frame(rgb, W, H):
    if rgb is None or rgb.shape[:2] != (H, W):
        raise RenderError(f"renderer returned {None if rgb is None else rgb.shape}, expected {(H, W)}")
    return rgb


def _frame_indices(tr, fps):
    """Resample to the output fps using traj time; then a frozen tail for the stamp."""
    t = np.asarray(tr["time"], dtype=float)
    T = len(t)
    if T < 2:
        idx = [0]
    else:
        tt = np.arange(t[0], t[-1] + 1e-9, 1.0 / fps)
        idx = np.clip(np.searchsorted(t, tt), 0, T - 1).tolist()
    tail = int(END_HOLD_S * fps) if tr.get("result") is not None else 0
    return idx, tail


def render_traj(traj_npz, out_mp4, camera="hero", hud=True, size=(1280, 720), fps=30, title=None):
    if camera == "grid":
        return render_grid(traj_npz, out_mp4, size=size if size != (1280, 720) else (1280, 480), fps=fps,
                           title=title, hud=hud)
    if camera not in ("hero", "side", "hands"):
        raise ValueError(f"unknown camera {camera!r} (hero|side|hands|grid)")
    tr = load_traj(traj_npz)
    if len(tr["qpos"]) == 0:
        raise RenderError(f"{traj_npz}: empty trajectory")
    W, H = size
    sc = Scene(W, H)
    sc.tint_tote(tr["box_mass"])
    idx, tail = _frame_indices(tr, fps)
    n = len(idx)
    tmp = _tmp_path(out_mp4)
    wr = _writer(tmp, fps)
    state = {}
    t0 = _time.time()
    last = None
    ok = False
    try:
        for k, i in enumerate(idx):
            sc.set_qpos(tr["qpos"][i])
            rgb = _check_frame(sc.render(make_camera(camera, k / max(1, n - 1), sc, state)), W, H)
            img = Image.fromarray(rgb)
            last = img
            frame = draw_hud(img, tr, i, sc, title) if hud else img
            wr.append_data(np.asarray(frame))
        for k in range(tail):
            a = min(1.0, (k + 1) / (0.25 * fps))
            frame = draw_hud(last, tr, idx[-1], sc, title, end_alpha=a) if hud else last
            wr.append_data(np.asarray(frame))
        wr.close()
        nfr = _finish(tmp, out_mp4, n + tail, (W, H))
        ok = True
    finally:
        try:
            wr.close()
        except Exception:
            pass
        sc.close()
        if not ok and os.path.exists(tmp):
            os.remove(tmp)
    dt = _time.time() - t0
    return {"out": out_mp4, "frames": nfr, "size": [W, H], "fps": fps, "duration_s": nfr / fps,
            "render_fps": (n + tail) / max(dt, 1e-6), "seconds": dt}


def render_grid(traj_npz, out_mp4, size=(1280, 480), fps=30, title=None, hud=True):
    """hero | side, side by side (the Argon critic format)."""
    tr = load_traj(traj_npz)
    W, H = size
    pw = W // 2
    sc = Scene(pw, H)
    sc.tint_tote(tr["box_mass"])
    idx, tail = _frame_indices(tr, fps)
    n = len(idx)
    tmp = _tmp_path(out_mp4)
    wr = _writer(tmp, fps)
    state = {}
    t0 = _time.time()
    last = None
    ok = False
    labels = [(pw / 2, "3/4 VIEW"), (pw + pw / 2, "SIDE PROFILE")]
    try:
        for k, i in enumerate(idx):
            sc.set_qpos(tr["qpos"][i])
            u = k / max(1, n - 1)
            a = _check_frame(sc.render(make_camera("hero", u, sc, state)), pw, H)
            b = _check_frame(sc.render(make_camera("side", u, sc, state)), pw, H)
            img = Image.fromarray(np.concatenate([a, b], axis=1))
            dr = ImageDraw.Draw(img)
            dr.line((pw, 0, pw, H), fill=(10, 10, 12), width=2)
            last = img
            frame = draw_hud(img, tr, i, sc, title, pane_labels=labels) if hud else img
            wr.append_data(np.asarray(frame))
        for k in range(tail):
            al = min(1.0, (k + 1) / (0.25 * fps))
            frame = draw_hud(last, tr, idx[-1], sc, title, end_alpha=al, pane_labels=labels) if hud else last
            wr.append_data(np.asarray(frame))
        wr.close()
        nfr = _finish(tmp, out_mp4, n + tail, (2 * pw, H))
        ok = True
    finally:
        try:
            wr.close()
        except Exception:
            pass
        sc.close()
        if not ok and os.path.exists(tmp):
            os.remove(tmp)
    dt = _time.time() - t0
    return {"out": out_mp4, "frames": nfr, "size": [2 * pw, H], "fps": fps, "duration_s": nfr / fps,
            "render_fps": (n + tail) / max(dt, 1e-6), "seconds": dt}


def render_still(traj_npz, out_png, camera="hero", frame=-1, hud=True, size=(1280, 720), title=None,
                 end_stamp=False):
    tr = load_traj(traj_npz)
    T = len(tr["time"])
    i = frame % T
    if camera == "grid":
        W, H = size
        sc = Scene(W // 2, H)
        sc.tint_tote(tr["box_mass"])
        sc.set_qpos(tr["qpos"][i])
        u = i / max(1, T - 1)
        img = Image.fromarray(np.concatenate([sc.render(make_camera("hero", u, sc, {})),
                                              sc.render(make_camera("side", u, sc, {}))], axis=1))
        labels = [(W / 4, "3/4 VIEW"), (3 * W / 4, "SIDE PROFILE")]
    else:
        W, H = size
        sc = Scene(W, H)
        sc.tint_tote(tr["box_mass"])
        sc.set_qpos(tr["qpos"][i])
        img = Image.fromarray(sc.render(make_camera(camera, i / max(1, T - 1), sc, {})))
        labels = None
    if hud:
        img = draw_hud(img, tr, i, sc, title, end_alpha=1.0 if end_stamp else 0.0, pane_labels=labels)
    sc.close()
    img.save(out_png)
    return out_png


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("traj")
    ap.add_argument("out", nargs="?", help="output .mp4 (or use --still)")
    ap.add_argument("--camera", default="hero", choices=["hero", "side", "hands", "grid"])
    ap.add_argument("--no-hud", action="store_true")
    ap.add_argument("--title", default=None)
    ap.add_argument("--size", default=None, help="WxH; default 1280x720 (grid: 1280x480)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--still", default=None, help="write a PNG instead of a video")
    ap.add_argument("--frame", type=int, default=-1)
    ap.add_argument("--stamp", action="store_true", help="still: draw the PASS/FAIL stamp")
    a = ap.parse_args()
    if a.size:
        size = tuple(int(v) for v in a.size.lower().split("x"))
    else:
        size = (1280, 480) if a.camera == "grid" else (1280, 720)
    if a.still:
        print(render_still(a.traj, a.still, a.camera, a.frame, not a.no_hud, size, a.title, a.stamp))
        return
    if not a.out:
        ap.error("need an output .mp4 or --still")
    if a.camera == "grid":
        info = render_grid(a.traj, a.out, size=size, fps=a.fps, title=a.title, hud=not a.no_hud)
    else:
        info = render_traj(a.traj, a.out, a.camera, not a.no_hud, size, a.fps, a.title)
    print(json.dumps(info))


if __name__ == "__main__":
    main()
