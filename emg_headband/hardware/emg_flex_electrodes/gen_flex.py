#!/usr/bin/env python3
"""Generate the forehead EMG electrode flex (Rev A draft) as a KiCad board.

Everything is parametric: edit the constants below and re-run
    python3 gen_flex.py
to rewrite kicad/emg_flex_electrodes.kicad_pcb and docs/flex_layout.png.

Design coordinates: x = arc length along the headband from the forehead
midline (+x toward the subject's LEFT, where the tail leaves for the back of
the head), y = height above the eyebrow line, both in mm. KiCad's y axis
points down, so kx = x + OX, ky = OY - y.

Needs: shapely, matplotlib (pip install shapely matplotlib).
"""
import os
import uuid

from shapely.geometry import Point, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
OX, OY = 60.0, 120.0

# --- Connector (main board J6, Hirose FH34SRJ-12S-0.5SH, 0.5 mm pitch) -------
# Pin order as on hardware/emg-rev-a-kicad (README, 11 Oct 2026).
PINS = {1: "AGND", 2: "CH3N", 3: "CH3P", 4: "REF", 5: "AGND", 6: "CH2N",
        7: "CH2P", 8: "REF", 9: "AGND", 10: "CH1N", 11: "CH1P", 12: "REF"}
NETS = ["", "AGND", "REF", "CH1P", "CH1N", "CH2P", "CH2N", "CH3P", "CH3N"]
NET = {n: i for i, n in enumerate(NETS)}

# --- Electrode sites ----------------------------------------------------------
# (ref, net, x, y, pad diameter, label)
ELECTRODES = [
    ("E1", "CH1P", 30.0, 34.0, 8.0, "CH1+ FRONTALIS L"),
    ("E2", "CH1N", 30.0, 14.0, 8.0, "CH1- FRONTALIS L"),
    ("E3", "CH2P", -10.0, 8.0, 8.0, "CH2+ CORRUGATOR R"),
    ("E4", "CH2N", -25.0, 8.0, 8.0, "CH2- CORRUGATOR R"),
    ("E5", "CH3P", 85.0, 34.0, 8.0, "CH3+ TEMPORALIS L"),
    ("E6", "CH3N", 85.0, 14.0, 8.0, "CH3- TEMPORALIS L"),
    ("E7", "REF", 0.0, 37.0, 12.0, "REF / RLD"),
]
DRILL = 1.5          # plated hole for a dome stud / rivet shank
LOBE_MARGIN = 2.0    # flex material around each pad

# --- Routing ------------------------------------------------------------------
TW = 0.25            # track width
VIA = (0.6, 0.3)     # via diameter, drill (JLC flex regular via 0.55/0.3)
# Fan-out lanes along the forehead spine (F.Cu), top to bottom. The order
# lets every net leave the bundle without crossing: outermost lanes leave
# first (temporalis), then frontalis, REF up, corrugator down.
FAN_ORDER = ["CH3P", "CH1P", "REF", "CH2N", "CH2P", "CH1N", "CH3N"]
FAN_Y0, FAN_PITCH = 24.4, 0.8
FAN_Y = {n: FAN_Y0 - k * FAN_PITCH for k, n in enumerate(FAN_ORDER)}

TAIL_YC = 34.0       # tail centre height (runs above the ear)
TAIL_PITCH = 0.5
SPREAD_PITCH = 1.0
X_VIA0, X_VIA_STEP = 102.0, 1.4   # crossover via columns
X_GND_VIA = 115.5
X_SPREAD0, X_SPREAD1 = 118.0, 122.0
X_END = 265.0        # tail end (connector edge); trim to fit the band
TAB_LEN = 6.0        # stiffened FPC tab
TAB_W = 6.5          # Hirose FH34SRJ-12S FPC width "G" = 6.5 +/- 0.05
FINGER = (2.5, 0.3)  # exposed contact length x width
FINGER_INSET = 0.2   # JLC cuts gold fingers back to 0.2 mm from the edge


def tail_y(pin):
    return TAIL_YC + (6.5 - pin) * TAIL_PITCH


def spread_y(pin):
    return TAIL_YC + (6.5 - pin) * SPREAD_PITCH


def K(x, y):
    return (round(x + OX, 4), round(OY - y, 4))


def uid():
    return str(uuid.uuid4())


# --- Outline ------------------------------------------------------------------
def outline():
    parts = [box(-33, 16, 100, 28),            # forehead spine
             box(-31, 3, -4, 16),              # corrugator paddle
             box(96, 17, 124, 42),             # crossover block
             box(120, TAIL_YC - 4, X_END - TAB_LEN, TAIL_YC + 4)]  # tail
    for _, _, x, y, d, _ in ELECTRODES:
        r = d / 2 + LOBE_MARGIN
        parts.append(Point(x, y).buffer(r, 64))
        lo, hi = sorted((y, 22.0))
        parts.append(box(x - r * 0.8, lo, x + r * 0.8, hi))
    shape = unary_union(parts)
    shape = shape.buffer(3, 32).buffer(-3, 32)      # fillet inside corners
    shape = shape.buffer(-1.5, 32).buffer(1.5, 32)  # round outside corners
    tab = box(X_END - TAB_LEN - 1, TAIL_YC - TAB_W / 2, X_END, TAIL_YC + TAB_W / 2)
    return unary_union([shape, tab]).simplify(0.01)


# --- Routing ------------------------------------------------------------------
def routes():
    """Return (segments, vias): segment = (layer, net, (x1,y1), (x2,y2))."""
    segs, vias = [], []
    via_x = {}
    k = 0
    for pin in range(1, 13):
        net = PINS[pin]
        ty, sy = tail_y(pin), spread_y(pin)
        # tail at 0.5 mm pitch, then spread to 1.0 mm
        segs.append(("F.Cu", net, (X_END - FINGER_INSET - FINGER[0] / 2, ty), (X_SPREAD1, ty)))
        segs.append(("F.Cu", net, (X_SPREAD1, ty), (X_SPREAD0, sy)))
        if net == "AGND":
            segs.append(("F.Cu", net, (X_SPREAD0, sy), (X_GND_VIA, sy)))
            vias.append((net, (X_GND_VIA, sy)))   # to the B.Cu shield
            continue
        x = X_VIA0 + k * X_VIA_STEP
        k += 1
        segs.append(("F.Cu", net, (X_SPREAD0, sy), (x, sy)))
        vias.append((net, (x, sy)))
        segs.append(("B.Cu", net, (x, sy), (x, FAN_Y[net])))   # crossover jump
        vias.append((net, (x, FAN_Y[net])))
        via_x[net] = max(via_x.get(net, -1e9), x)
    # fan-out lanes and exits to the electrodes
    exits = {}
    for ref, net, ex, ey, d, _ in ELECTRODES:
        exits.setdefault(net, []).append((ex, ey))
    for net, pts in exits.items():
        xmin = min(p[0] for p in pts)
        y = FAN_Y[net]
        segs.append(("F.Cu", net, (via_x[net], y), (xmin, y)))
        for ex, ey in pts:
            segs.append(("F.Cu", net, (ex, y), (ex, ey)))
    return segs, vias


# --- KiCad writer -------------------------------------------------------------
def fp_electrode(ref, net, x, y, d, label):
    kx, ky = K(x, y)
    n = NET[net]
    return f'''  (footprint "emg_flex:Electrode_Dome_{d:g}mm" (layer "F.Cu") (at {kx} {ky})
    (descr "Skin electrode site: {d:g} mm ENIG pad exposed on the skin side (B), {DRILL} mm plated hole for a domed stud or rivet soldered on the outer side (F).")
    (attr exclude_from_pos_files exclude_from_bom)
    (fp_text reference "{ref}" (at 0 {-(d / 2 + 1.6):.2f}) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
    (fp_text value "{label}" (at 0 {d / 2 + 1.6:.2f}) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
    (fp_circle (center 0 0) (end {d / 2 + 0.5} 0) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))
    (fp_circle (center 0 0) (end {d / 2 + 0.5} 0) (stroke (width 0.05) (type solid)) (fill none) (layer "B.CrtYd"))
    (fp_circle (center 0 0) (end {d / 2} 0) (stroke (width 0.1) (type solid)) (fill none) (layer "B.Fab"))
    (pad "1" thru_hole circle (at 0 0) (size {d} {d}) (drill {DRILL}) (layers "*.Cu" "*.Mask") (net {n} "{net}"))
  )
'''


def fp_fpc_tail():
    kx, ky = K(X_END - FINGER_INSET - FINGER[0] / 2, TAIL_YC)
    pads = []
    for pin in range(1, 13):
        net = PINS[pin]
        dy = -(tail_y(pin) - TAIL_YC)
        pads.append(f'    (pad "{pin}" smd rect (at 0 {dy:.3f}) (size {FINGER[0]} {FINGER[1]}) '
                    f'(layers "F.Cu" "F.Mask") (net {NET[net]} "{net}"))')
    return f'''  (footprint "emg_flex:FPC_Tail_12P_P0.50mm_FH34SRJ" (layer "F.Cu") (at {kx} {ky})
    (descr "FPC tail for Hirose FH34SRJ-12S-0.5SH: 12 contacts on F.Cu, 0.3 x 2.5 mm, 0.5 mm pitch, tab width 6.5 mm. Needs a B-side stiffener to 0.30 +/- 0.03 mm total.")
    (attr exclude_from_pos_files exclude_from_bom)
    (fp_text reference "J1" (at -4 -4.5) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
    (fp_text value "TO MAIN BOARD J6" (at -4 4.5) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
    (fp_text user "1" (at -2.4 -2.75) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
{chr(10).join(pads)}
  )
'''


def gr_text(txt, x, y, layer="F.SilkS", size=1.2, rot=0):
    kx, ky = K(x, y)
    return (f'  (gr_text "{txt}" (at {kx} {ky} {rot}) (layer "{layer}") '
            f'(effects (font (size {size} {size}) (thickness {size * 0.15:.2f}))))\n')


def poly_pts(poly):
    return " ".join(f"(xy {K(x, y)[0]} {K(x, y)[1]})" for x, y in list(poly.exterior.coords)[:-1])


def write_pcb(shape, segs, vias, path):
    out = ['''(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 0.11))
  (paper "A3")
  (title_block (title "EMG forehead electrode flex") (rev "A-draft") (comment 1 "2-layer polyimide flex, 0.11 mm, 1/3 oz, ENIG. Skin side = B. Generated by gen_flex.py"))
  (layers
    (0 "F.Cu" signal) (31 "B.Cu" signal)
    (34 "B.Paste" user) (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user) (39 "F.Mask" user)
    (40 "Dwgs.User" user "User.Drawings") (41 "Cmts.User" user "User.Comments")
    (44 "Edge.Cuts" user) (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user) (49 "F.Fab" user)
    (50 "User.1" user "Stiffener")
  )
  (setup (pad_to_mask_clearance 0))
''']
    for i, n in enumerate(NETS):
        out.append(f'  (net {i} "{n}")\n')
    for e in ELECTRODES:
        out.append(fp_electrode(*e))
    out.append(fp_fpc_tail())
    out.append(f'  (gr_poly (pts {poly_pts(shape)}) (stroke (width 0.1) (type solid)) (fill none) (layer "Edge.Cuts"))\n')
    for layer, net, a, b in segs:
        (x1, y1), (x2, y2) = K(*a), K(*b)
        out.append(f'  (segment (start {x1} {y1}) (end {x2} {y2}) (width {TW}) (layer "{layer}") (net {NET[net]}))\n')
    for net, p in vias:
        x, y = K(*p)
        out.append(f'  (via (at {x} {y}) (size {VIA[0]}) (drill {VIA[1]}) (layers "F.Cu" "B.Cu") (net {NET[net]}))\n')
    # AGND hatched shield on the skin side (B.Cu), clear of the FPC tab
    shield = shape.difference(box(X_END - TAB_LEN - 1.5, -100, X_END + 10, 100)).buffer(-0.5, 16)
    if shield.geom_type != "Polygon":
        shield = max(shield.geoms, key=lambda g: g.area)
    shield = shield.simplify(0.05)
    out.append(f'''  (zone (net 1) (net_name "AGND") (layer "B.Cu") (name "SHIELD") (hatch edge 0.5)
    (connect_pads (clearance 0.6)) (min_thickness 0.2) (filled_areas_thickness no)
    (fill (mode hatch) (thermal_gap 0.5) (thermal_bridge_width 0.5)
      (hatch_thickness 0.3) (hatch_gap 1.0) (hatch_orientation 45)
      (hatch_smoothing_level 0) (hatch_smoothing_value 0.1)
      (hatch_border_algorithm hatch_thickness) (hatch_min_hole_area 0.3))
    (polygon (pts {poly_pts(shield)}))
  )
''')
    # stiffeners (User.1): PI under the FPC tab, FR4 rings behind electrodes
    tx0, ty0 = K(X_END - TAB_LEN, TAIL_YC + TAB_W / 2)
    tx1, ty1 = K(X_END, TAIL_YC - TAB_W / 2)
    out.append(f'  (gr_rect (start {tx0} {ty0}) (end {tx1} {ty1}) (stroke (width 0.1) (type solid)) (fill none) (layer "User.1"))\n')
    out.append(gr_text("PI 0.2 B-SIDE", X_END - TAB_LEN / 2, TAIL_YC + 5.5, "User.1", 0.8))
    for ref, net, x, y, d, _ in ELECTRODES:
        kx, ky = K(x, y)
        out.append(f'  (gr_circle (center {kx} {ky}) (end {kx + d / 2 + 1.0} {ky}) (stroke (width 0.1) (type solid)) (fill none) (layer "User.1"))\n')
        out.append(f'  (gr_circle (center {kx} {ky}) (end {kx + 2.0} {ky}) (stroke (width 0.1) (type solid)) (fill none) (layer "User.1"))\n')
    # labels
    out.append(gr_text("FRONTALIS L (CH1)", 30, 43.5))
    out.append(gr_text("TEMPORALIS L (CH3)", 85, 43.5))
    out.append(gr_text("CORRUGATOR R (CH2)", -17.5, 0.8))
    out.append(gr_text("REF", 0, 46.5))
    out.append(gr_text("MIDLINE", 0, 17.2, size=0.8))
    out.append(gr_text("OUTER SIDE  -  SKIN SIDE IS B (ELECTRODES)", 175, TAIL_YC, size=1.5))
    out.append(gr_text("CONTACTS FACE UP (F) - CHECK J6 ORIENTATION", 215, TAIL_YC + 5.5, "Cmts.User", 1.0))
    out.append(")\n")
    with open(path, "w") as f:
        f.write("".join(out))


def write_drawing(shape, segs, vias, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon

    fig, ax = plt.subplots(figsize=(18, 4.6), dpi=150)
    ax.add_patch(Polygon(list(shape.exterior.coords), closed=True, fc="#f3c26b", ec="#8a5a00", lw=1.2))
    for layer, net, (x1, y1), (x2, y2) in segs:
        ax.plot([x1, x2], [y1, y2], lw=0.8 if layer == "F.Cu" else 1.2,
                color="#b5402a" if layer == "F.Cu" else "#2a63b5", solid_capstyle="round")
    for net, (x, y) in vias:
        ax.add_patch(Circle((x, y), VIA[0] / 2, fc="#555", ec="none"))
    for ref, net, x, y, d, label in ELECTRODES:
        ax.add_patch(Circle((x, y), d / 2, fc="#d9d9d9", ec="#333", lw=1))
        ax.add_patch(Circle((x, y), DRILL / 2, fc="white", ec="#333", lw=0.5))
        if y < 12:   # corrugator pair sits close together: label below
            ax.text(x, y - d / 2 - 1.5, label.replace(" ", "\n", 1), fontsize=6.5, ha="center", va="top")
        else:
            ax.text(x + d / 2 + 1, y, label, fontsize=7, va="center")
    ax.axhline(0, color="#999", lw=0.8, ls="--")
    ax.text(-38, 0.6, "eyebrow line", fontsize=7, color="#666")
    ax.axvline(0, color="#999", lw=0.8, ls=":")
    ax.text(0.8, -10, "forehead midline", fontsize=7, color="#666")
    ax.annotate("", xy=(X_END, 45), xytext=(130, 45), arrowprops=dict(arrowstyle="->", color="#666"))
    ax.text(140, 46.5, "tail runs above the left ear to main board J6 at the back of the head", fontsize=8, color="#444")
    ax.text(X_END - 18, TAIL_YC - 7.5, "FPC tab, 12P 0.5 mm\nPI stiffener to 0.3 mm", fontsize=7)
    ax.text(98, 44, "crossover\n(B.Cu jumps)", fontsize=7, color="#2a63b5")
    ax.set_aspect("equal")
    ax.set_xlim(-45, X_END + 5)
    ax.set_ylim(-12, 52)
    ax.set_xlabel("arc length along the band from forehead midline (mm, + = subject's left)")
    ax.set_ylabel("height above brow (mm)")
    ax.set_title("EMG forehead electrode flex, Rev A draft (outer side view; red = F.Cu traces, blue = B.Cu jumpers; "
                 "B.Cu hatched AGND shield not drawn)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    shape = outline()
    segs, vias = routes()
    os.makedirs(os.path.join(HERE, "kicad"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
    write_pcb(shape, segs, vias, os.path.join(HERE, "kicad", "emg_flex_electrodes.kicad_pcb"))
    write_drawing(shape, segs, vias, os.path.join(HERE, "docs", "flex_layout.png"))
    minx, miny, maxx, maxy = shape.bounds
    print(f"outline {maxx - minx:.1f} x {maxy - miny:.1f} mm, area {shape.area / 100:.1f} cm^2")


if __name__ == "__main__":
    main()
