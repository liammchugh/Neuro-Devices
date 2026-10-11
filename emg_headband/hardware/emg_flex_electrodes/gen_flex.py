#!/usr/bin/env python3
"""Generate the forehead EMG electrode flex (Rev A draft) as a KiCad board.

Everything is parametric: edit the constants below and re-run
    python3 gen_flex.py
to rewrite the KiCad project in kicad/ (schematic, board, symbol and
footprint libraries) and docs/flex_layout.png. The schematic and board share
symbol UUIDs, so KiCad's "Update PCB from Schematic" keeps them linked.

Design coordinates: x = arc length along the headband from the forehead
midline (+x toward the tail side, where the flex leaves for the back of the
head), y = height above the eyebrow line, both in mm. TAIL_SIDE picks the
subject's side the tail runs along. The board is drawn as seen from its outer
(F) side, which is the front view of the forehead, so a right-side tail runs
to -X in KiCad. KiCad's y axis points down: ky = OY - y.

Needs: shapely, matplotlib (pip install shapely matplotlib).
"""
import math
import os
import uuid

from shapely.geometry import Point, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
# Main board J6 faces the board's right edge (seen from outside, F side out,
# USB-C down), which is the subject's right at the back of the head.
TAIL_SIDE = "R"
SIGN = 1 if TAIL_SIDE == "L" else -1   # front view: subject's left is +X
OX, OY = (60.0 if SIGN > 0 else 340.0), 120.0
T, O = TAIL_SIDE, ("R" if TAIL_SIDE == "L" else "L")   # tail side, other side

# --- Connector (main board J6, Hirose FH34SRJ-12S-0.5SH, 0.5 mm pitch) -------
# Pin order as on hardware/emg-rev-a-kicad (commit c72bb90, 11 Oct 2026).
PINS = {1: "AGND", 2: "CH1P", 3: "CH1N", 4: "REF", 5: "AGND", 6: "CH2P",
        7: "CH2N", 8: "REF", 9: "AGND", 10: "CH3P", 11: "CH3N", 12: "REF"}
# The main board's AGND pins (1, 5, 9) are left unconnected on the flex. The
# B.Cu shield is tied to REF instead: REF is the RLD-driven body potential, so
# the ~35-55 pF each signal trace has to the shield carries no common-mode
# current and does not convert 50/60 Hz into a differential error. An AGND
# shield would add that capacitance to AGND on top of the main board's 100 pF
# input caps and undo their dry-electrode CMRR margin.
NC_PINS = {p for p, n in PINS.items() if n == "AGND"}
SHIELD_NET = "REF"
NETS = ["", "REF", "CH1P", "CH1N", "CH2P", "CH2N", "CH3P", "CH3N"]
NET = {n: i for i, n in enumerate(NETS)}

# --- Electrode sites ----------------------------------------------------------
# (ref, net, x, y, pad diameter, label)
ELECTRODES = [
    ("E1", "CH1P", 30.0, 34.0, 8.0, f"CH1+ FRONTALIS {T}"),
    ("E2", "CH1N", 30.0, 14.0, 8.0, f"CH1- FRONTALIS {T}"),
    ("E3", "CH2P", -10.0, 8.0, 8.0, f"CH2+ CORRUGATOR {O}"),
    ("E4", "CH2N", -25.0, 8.0, 8.0, f"CH2- CORRUGATOR {O}"),
    ("E5", "CH3P", 85.0, 34.0, 8.0, f"CH3+ TEMPORALIS {T}"),
    ("E6", "CH3N", 85.0, 14.0, 8.0, f"CH3- TEMPORALIS {T}"),
    ("E7", "REF", 0.0, 37.0, 12.0, "REF / RLD"),
]
DRILL = 2.7          # plated hole for a DIN 660 2.5 mm round-head rivet (optional)
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
X_SPREAD0, X_SPREAD1 = 118.0, 122.0
# Tail end: half of a 58 cm head (290 mm) minus 27 mm from the back centre
# to J6 contacts on the 62.5 mm main board (c72bb90), plus ~7 mm slack.
X_END = 270.0
TAB_LEN = 6.0        # stiffened FPC tab
TAB_W = 6.5          # Hirose FH34SRJ-12S FPC width "G" = 6.5 +/- 0.05
FINGER = (2.5, 0.3)  # exposed contact length x width
FINGER_INSET = 0.2   # JLC cuts gold fingers back to 0.2 mm from the edge

# --- Ear keep-out (58 cm head) ----------------------------------------------
# The pinna, modelled as an ellipse in band coordinates: front of the helix
# about 120 mm along the band from the forehead midline, back about 184 mm,
# top of the helix 8 mm above the brow line (conservative; it is usually at or
# below brow level). The flex must stay EAR_CLEAR away from it, which also
# leaves room for glasses arms.
EAR_C, EAR_AX = (152.0, -12.0), (32.0, 20.0)
EAR_CLEAR = 12.0


def tail_y(pin):
    return TAIL_YC + (6.5 - pin) * TAIL_PITCH


def spread_y(pin):
    return TAIL_YC + (6.5 - pin) * SPREAD_PITCH


def K(x, y):
    return (round(OX + SIGN * x, 4), round(OY - y, 4))


UUID_NS = uuid.UUID("6d1b7a52-3c2e-4f4b-9a39-0f3f6e1c9a10")


def uid(name=None):
    """Stable UUID for a named object (so regenerating keeps links), else random."""
    return str(uuid.uuid5(UUID_NS, name) if name else uuid.uuid4())


def ear_shape():
    from shapely import affinity
    return affinity.scale(Point(EAR_C).buffer(1, 128), EAR_AX[0], EAR_AX[1])


# --- Outline ------------------------------------------------------------------
def outline():
    parts = [box(-33, 16, 100, 28),            # forehead spine
             box(-31, 3, -4, 16),              # corrugator paddle
             box(96, 17, 115, 42),             # crossover: via columns
             box(110, 26, 124, 42),            # crossover: spread, lifted off the ear
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
    shape = unary_union([shape, tab]).simplify(0.01)
    gap = shape.distance(ear_shape())
    assert gap >= EAR_CLEAR, f"flex is {gap:.1f} mm from the ear, need {EAR_CLEAR}"
    return shape


# --- Routing ------------------------------------------------------------------
def routes():
    """Return (segments, vias): segment = (layer, net, (x1,y1), (x2,y2))."""
    segs, vias = [], []
    via_x = {}
    k = 0
    for pin in range(1, 13):
        if pin in NC_PINS:
            continue
        net = PINS[pin]
        ty, sy = tail_y(pin), spread_y(pin)
        # tail at 0.5 mm pitch, then spread to 1.0 mm
        segs.append(("F.Cu", net, (X_END - FINGER_INSET - FINGER[0] / 2, ty), (X_SPREAD1, ty)))
        segs.append(("F.Cu", net, (X_SPREAD1, ty), (X_SPREAD0, sy)))
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
FONT = "(effects (font (size 1 1) (thickness 0.15)))"


def electrode_fp_name(d):
    return f"Electrode_Dome_{d:g}mm"


def fp_electrode_body(d, ref="E**", value=None, net=None):
    netx = f' (net {NET[net]} "{net}")' if net else ""
    value = value or electrode_fp_name(d)
    return f'''    (descr "Skin electrode site: {d:g} mm ENIG pad exposed on the skin side (B), {DRILL} mm plated hole for a domed stud or rivet soldered on the outer side (F).")
    (tags "EMG electrode dome")
    (attr exclude_from_pos_files exclude_from_bom)
    (fp_text reference "{ref}" (at 0 {-(d / 2 + 1.6):.2f}) (layer "F.Fab") {FONT})
    (fp_text value "{value}" (at 0 {d / 2 + 1.6:.2f}) (layer "F.Fab") {FONT})
    (fp_circle (center 0 0) (end {d / 2 + 0.5} 0) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))
    (fp_circle (center 0 0) (end {d / 2 + 0.5} 0) (stroke (width 0.05) (type solid)) (fill none) (layer "B.CrtYd"))
    (fp_circle (center 0 0) (end {d / 2} 0) (stroke (width 0.1) (type solid)) (fill none) (layer "B.Fab"))
    (pad "1" thru_hole circle (at 0 0) (size {d} {d}) (drill {DRILL}) (layers "*.Cu" "*.Mask"){netx})
'''


FPC_FP = "FPC_Tail_12P_P0.50mm_FH34SRJ"


def fp_fpc_body(ref="J**", value=FPC_FP, nets=False):
    pads = []
    for pin in range(1, 13):
        net = PINS[pin]
        dy = -(tail_y(pin) - TAIL_YC)
        netx = f' (net {NET[net]} "{net}")' if nets and pin not in NC_PINS else ""
        pads.append(f'    (pad "{pin}" smd rect (at 0 {dy:.3f}) (size {FINGER[0]} {FINGER[1]}) '
                    f'(layers "F.Cu" "F.Mask"){netx})')
    return f'''    (descr "FPC tail for Hirose FH34SRJ-12S-0.5SH: 12 contacts on F.Cu, 0.3 x 2.5 mm, 0.5 mm pitch, pin 1 at the top, tab edge on the {'+X' if SIGN > 0 else '-X'} side. Tab width 6.5 mm; needs a B-side stiffener to 0.30 +/- 0.03 mm total.")
    (tags "FPC FFC Hirose FH34SRJ 0.5mm 12pin tail")
    (attr exclude_from_pos_files exclude_from_bom)
    (fp_text reference "{ref}" (at {-4 * SIGN} -4.5) (layer "F.SilkS") {FONT})
    (fp_text value "{value}" (at {-4 * SIGN} 4.5) (layer "F.Fab") {FONT})
    (fp_text user "1" (at {-2.4 * SIGN} -2.75) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
{chr(10).join(pads)}
'''


def board_fp(lib_name, x, y, ref, body):
    kx, ky = K(x, y)
    return (f'  (footprint "emg_flex:{lib_name}" (layer "F.Cu") (at {kx} {ky})\n'
            f'    (path "/{uid("sym:" + ref)}")\n'
            f'    (property "Sheetfile" "emg_flex_electrodes.kicad_sch") (property "Sheetname" "")\n'
            f'{body}  )\n')


def write_footprint_lib(libdir):
    os.makedirs(libdir, exist_ok=True)
    fps = {electrode_fp_name(d): fp_electrode_body(d) for d in sorted({e[4] for e in ELECTRODES})}
    fps[FPC_FP] = fp_fpc_body()
    for name, body in fps.items():
        with open(os.path.join(libdir, name + ".kicad_mod"), "w") as f:
            f.write(f'(footprint "{name}" (version 20221018) (generator pcbnew)\n  (layer "F.Cu")\n{body})\n')


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
    for ref, net, x, y, d, label in ELECTRODES:
        out.append(board_fp(electrode_fp_name(d), x, y, ref, fp_electrode_body(d, ref, label, net)))
    out.append(board_fp(FPC_FP, X_END - FINGER_INSET - FINGER[0] / 2, TAIL_YC, "J1",
                        fp_fpc_body("J1", "TO MAIN BOARD J6", nets=True)))
    out.append(f'  (gr_poly (pts {poly_pts(shape)}) (stroke (width 0.1) (type solid)) (fill none) (layer "Edge.Cuts"))\n')
    for layer, net, a, b in segs:
        (x1, y1), (x2, y2) = K(*a), K(*b)
        out.append(f'  (segment (start {x1} {y1}) (end {x2} {y2}) (width {TW}) (layer "{layer}") (net {NET[net]}))\n')
    for net, p in vias:
        x, y = K(*p)
        out.append(f'  (via (at {x} {y}) (size {VIA[0]}) (drill {VIA[1]}) (layers "F.Cu" "B.Cu") (net {NET[net]}))\n')
    # Hatched shield on the skin side (B.Cu) at REF potential, clear of the FPC
    # tab. It joins REF through the crossover jumpers and the REF electrode.
    shield = shape.difference(box(X_END - TAB_LEN - 1.5, -100, X_END + 10, 100)).buffer(-0.5, 16)
    if shield.geom_type != "Polygon":
        shield = max(shield.geoms, key=lambda g: g.area)
    shield = shield.simplify(0.05)
    out.append(f'''  (zone (net {NET[SHIELD_NET]}) (net_name "{SHIELD_NET}") (layer "B.Cu") (name "SHIELD") (hatch edge 0.5)
    (connect_pads (clearance 0.6)) (min_thickness 0.2) (filled_areas_thickness no)
    (fill (mode hatch) (thermal_gap 0.5) (thermal_bridge_width 0.5)
      (hatch_thickness 0.3) (hatch_gap 1.0) (hatch_orientation 45)
      (hatch_smoothing_level 0) (hatch_smoothing_value 0.1)
      (hatch_border_algorithm hatch_thickness) (hatch_min_hole_area 0.3))
    (polygon (pts {poly_pts(shield)}))
  )
''')
    # stiffener (User.1): PI under the FPC tab, B side. Rev 1 has none at the
    # electrodes; the foam disc behind each lobe supports the rivet.
    tx0, ty0 = K(X_END - TAB_LEN, TAIL_YC + TAB_W / 2)
    tx1, ty1 = K(X_END, TAIL_YC - TAB_W / 2)
    out.append(f'  (gr_rect (start {tx0} {ty0}) (end {tx1} {ty1}) (stroke (width 0.1) (type solid)) (fill none) (layer "User.1"))\n')
    out.append(gr_text("STIFFENER: PI 0.2 B-SIDE", X_END - TAB_LEN / 2, TAIL_YC + 5.5, "Cmts.User", 0.8))
    # ear outline and keep-out (drawing only; the generator asserts the gap)
    ear = ear_shape().simplify(0.2)
    out.append(f'  (gr_poly (pts {poly_pts(ear)}) (stroke (width 0.15) (type dash)) (fill none) (layer "Dwgs.User"))\n')
    out.append(f'  (gr_poly (pts {poly_pts(ear.buffer(EAR_CLEAR, 32).simplify(0.2))}) (stroke (width 0.1) (type dot)) (fill none) (layer "Dwgs.User"))\n')
    out.append(gr_text(f"EAR {T} (keep-out {EAR_CLEAR:g} mm)", EAR_C[0], EAR_C[1] + 6, "Dwgs.User", 1.5))
    # labels
    out.append(gr_text(f"FRONTALIS {T} (CH1)", 30, 43.5))
    out.append(gr_text(f"TEMPORALIS {T} (CH3)", 85, 43.5))
    out.append(gr_text(f"CORRUGATOR {O} (CH2)", -17.5, 0.8))
    out.append(gr_text("REF", 0, 46.5))
    out.append(gr_text("MIDLINE", 0, 17.2, size=0.8))
    out.append(gr_text("OUTER SIDE  -  SKIN SIDE IS B (ELECTRODES)", 175, TAIL_YC, size=1.5))
    out.append(gr_text("CONTACTS FACE UP (F) - CHECK J6 ORIENTATION", 215, TAIL_YC + 5.5, "Cmts.User", 1.0))
    out.append(")\n")
    with open(path, "w") as f:
        f.write("".join(out))


# --- Schematic and symbol library -------------------------------------------
SFONT = "(effects (font (size 1.27 1.27)))"
SFONT_HIDE = "(effects (font (size 1.27 1.27)) hide)"


def sym_electrode():
    return f'''(symbol "Electrode" (pin_names (offset 1.016) hide) (in_bom no) (on_board yes)
      (property "Reference" "E" (at 0 3.81 0) {SFONT})
      (property "Value" "Electrode" (at 0 -3.81 0) {SFONT})
      (property "Footprint" "emg_flex:Electrode_Dome_8mm" (at 0 0 0) {SFONT_HIDE})
      (property "Datasheet" "" (at 0 0 0) {SFONT_HIDE})
      (property "ki_description" "Skin electrode contact (dome or snap on a flex pad)" (at 0 0 0) {SFONT_HIDE})
      (symbol "Electrode_0_1"
        (circle (center 0 0) (radius 1.27) (stroke (width 0.254) (type default)) (fill (type outline)))
        (polyline (pts (xy -2.54 -2.032) (xy 2.54 -2.032)) (stroke (width 0.254) (type default)) (fill (type none)))
      )
      (symbol "Electrode_1_1"
        (pin passive line (at 3.81 0 180) (length 2.54) (name "~" {SFONT}) (number "1" {SFONT}))
      )
    )'''


def sym_fpc():
    pins = "\n".join(
        f'        (pin passive line (at -5.08 {13.97 - (i - 1) * 2.54:.2f} 0) (length 2.54) '
        f'(name "{"NC" if i in NC_PINS else PINS[i]}" {SFONT}) (number "{i}" {SFONT}))' for i in range(1, 13))
    return f'''(symbol "FPC_Tail_12P" (pin_names (offset 1.016)) (in_bom no) (on_board yes)
      (property "Reference" "J" (at 0 16.51 0) {SFONT})
      (property "Value" "FPC_Tail_12P" (at 0 -16.51 0) {SFONT})
      (property "Footprint" "emg_flex:{FPC_FP}" (at 0 0 0) {SFONT_HIDE})
      (property "Datasheet" "" (at 0 0 0) {SFONT_HIDE})
      (property "ki_description" "12-contact FPC tail into Hirose FH34SRJ-12S-0.5SH (main board J6)" (at 0 0 0) {SFONT_HIDE})
      (symbol "FPC_Tail_12P_0_1"
        (rectangle (start -2.54 15.24) (end 7.62 -15.24) (stroke (width 0.254) (type default)) (fill (type background)))
      )
      (symbol "FPC_Tail_12P_1_1"
{pins}
      )
    )'''


def write_symbol_lib(path):
    body = "\n  ".join(s.replace("\n    ", "\n  ") for s in (sym_electrode(), sym_fpc()))
    with open(path, "w") as f:
        f.write(f"(kicad_symbol_lib (version 20220914) (generator kicad_symbol_editor)\n  {body}\n)\n")


def write_schematic(path):
    root = uid("sheet:root")
    lib = "\n    ".join(s.replace('(symbol "', '(symbol "emg_flex:', 1) for s in (sym_electrode(), sym_fpc()))
    items = []

    def place(lib_id, ref, value, fp, x, y, npins):
        u = uid("sym:" + ref)
        pins = " ".join(f'(pin "{i}" (uuid {uid(f"pin:{ref}:{i}")}))' for i in range(1, npins + 1))
        items.append(f'''  (symbol (lib_id "emg_flex:{lib_id}") (at {x:.2f} {y:.2f} 0) (unit 1)
    (in_bom no) (on_board yes) (dnp no) (uuid {u})
    (property "Reference" "{ref}" (at {x:.2f} {y - (3.81 if npins == 1 else 16.51):.2f} 0) {SFONT})
    (property "Value" "{value}" (at {x + (0 if npins == 1 else 2.54):.2f} {y + (3.81 if npins == 1 else 16.51):.2f} 0) {SFONT})
    (property "Footprint" "emg_flex:{fp}" (at {x:.2f} {y:.2f} 0) {SFONT_HIDE})
    (property "Datasheet" "" (at {x:.2f} {y:.2f} 0) {SFONT_HIDE})
    {pins}
    (instances (project "emg_flex_electrodes" (path "/{root}" (reference "{ref}") (unit 1))))
  )''')

    def stub(x0, y0, x1, net, angle):
        items.append(f'  (wire (pts (xy {x0:.2f} {y0:.2f}) (xy {x1:.2f} {y0:.2f})) (stroke (width 0) (type default)) (uuid {uid()}))')
        just = "left" if angle == 0 else "right"
        items.append(f'  (label "{net}" (at {x1:.2f} {y0:.2f} {angle}) (effects (font (size 1.27 1.27)) (justify {just} bottom)) (uuid {uid()}))')

    # electrodes in a column on the left, FPC tail on the right
    for k, (ref, net, x, y, d, label) in enumerate(ELECTRODES):
        ex, ey = 63.5, 50.8 + k * 12.7
        place("Electrode", ref, label, electrode_fp_name(d), ex, ey, 1)
        stub(ex + 3.81, ey, ex + 3.81 + 7.62, net, 0)
    jx, jy = 177.8, 88.9
    place("FPC_Tail_12P", "J1", "TO MAIN BOARD J6 (FH34SRJ-12S)", FPC_FP, jx, jy, 12)
    for i in range(1, 13):
        py = jy - 13.97 + (i - 1) * 2.54
        if i in NC_PINS:
            items.append(f'  (no_connect (at {jx - 5.08:.2f} {py:.2f}) (uuid {uid()}))')
        else:
            stub(jx - 5.08, py, jx - 5.08 - 7.62, PINS[i], 180)
    notes = [
        "Forehead EMG electrode flex. Generated by gen_flex.py: edit there, not here.",
        f"Tail runs along the subject's {'right' if TAIL_SIDE == 'R' else 'left'} to main board J6 (pin order from hardware/emg-rev-a-kicad c72bb90).",
        "CH1 frontalis (brow raise), CH2 corrugator (frown), CH3 anterior temporalis (jaw clench).",
        "REF is the shared RLD electrode; the three REF pins all land on it. Main board AGND pins 1/5/9 are not connected; the B.Cu hatched shield is tied to REF.",
        "Electrode pairs: 20 mm centre spacing along the fibres (corrugator 15 mm).",
    ]
    for k, t in enumerate(notes):
        items.append(f'  (text "{t}" (at 30.48 {152.4 + k * 5.08:.2f} 0) (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid {uid()}))')
    with open(path, "w") as f:
        f.write(f'''(kicad_sch (version 20230121) (generator eeschema)
  (uuid {root})
  (paper "A4")
  (title_block (title "EMG forehead electrode flex") (rev "A-draft") (comment 1 "Generated by gen_flex.py"))
  (lib_symbols
    {lib}
  )
{chr(10).join(items)}
  (sheet_instances (path "/" (page "1")))
)
''')


def write_lib_tables(kdir):
    with open(os.path.join(kdir, "sym-lib-table"), "w") as f:
        f.write('(sym_lib_table\n  (version 7)\n  (lib (name "emg_flex")(type "KiCad")(uri "${KIPRJMOD}/emg_flex.kicad_sym")(options "")(descr "Electrode flex symbols"))\n)\n')
    with open(os.path.join(kdir, "fp-lib-table"), "w") as f:
        f.write('(fp_lib_table\n  (version 7)\n  (lib (name "emg_flex")(type "KiCad")(uri "${KIPRJMOD}/emg_flex.pretty")(options "")(descr "Electrode flex footprints"))\n)\n')


def write_drawing(shape, segs, vias, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon

    HA = "left" if SIGN > 0 else "right"   # text alignment in the mirrored view
    fig, ax = plt.subplots(figsize=(18, 5.6), dpi=150)
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
            ax.text(x + d / 2 + 1, y, label, fontsize=7, va="center", ha=HA)
    from matplotlib.patches import Ellipse
    ax.add_patch(Ellipse(EAR_C, 2 * EAR_AX[0], 2 * EAR_AX[1], fc="#eeeeee", ec="#888", ls="--"))
    ax.add_patch(Ellipse(EAR_C, 2 * (EAR_AX[0] + EAR_CLEAR), 2 * (EAR_AX[1] + EAR_CLEAR), fc="none", ec="#bbb", ls=":"))
    ax.text(EAR_C[0], EAR_C[1] + 4, f"ear ({EAR_CLEAR:g} mm keep-out)", fontsize=7, color="#666", ha="center")
    ax.axhline(0, color="#999", lw=0.8, ls="--")
    ax.text(-38, 0.6, "eyebrow line", fontsize=7, color="#666", ha="right" if SIGN > 0 else "left")
    ax.axvline(0, color="#999", lw=0.8, ls=":")
    ax.text(0.8, -10, "forehead midline", fontsize=7, color="#666", ha=HA)
    ax.annotate("", xy=(X_END, 45), xytext=(130, 45), arrowprops=dict(arrowstyle="->", color="#666"))
    side = "left" if TAIL_SIDE == "L" else "right"
    ax.text(140, 46.5, f"tail runs above the {side} ear to main board J6 at the back of the head", fontsize=8, color="#444", ha=HA)
    ax.text(X_END - 4, TAIL_YC - 9.5, "FPC tab, 12P 0.5 mm, pin 1 at top\nPI stiffener to 0.3 mm", fontsize=7, ha="right" if SIGN > 0 else "left")
    ax.text(98, 44, "crossover\n(B.Cu jumps)", fontsize=7, color="#2a63b5", ha=HA)
    ax.set_aspect("equal")
    ax.set_xlim(-45, X_END + 5)
    ax.set_ylim(-34, 52)
    if SIGN < 0:
        ax.invert_xaxis()   # front view: the subject's right is on the viewer's left
    ax.set_xlabel(f"arc length along the band from forehead midline (mm, + = toward the tail, subject's {side})")
    ax.set_ylabel("height above brow (mm)")
    ax.set_title("EMG forehead electrode flex, Rev A draft (outer side view; red = F.Cu traces, blue = B.Cu jumpers; "
                 "B.Cu hatched REF shield not drawn)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    shape = outline()
    segs, vias = routes()
    os.makedirs(os.path.join(HERE, "kicad"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
    kdir = os.path.join(HERE, "kicad")
    write_footprint_lib(os.path.join(kdir, "emg_flex.pretty"))
    write_symbol_lib(os.path.join(kdir, "emg_flex.kicad_sym"))
    write_lib_tables(kdir)
    write_schematic(os.path.join(kdir, "emg_flex_electrodes.kicad_sch"))
    write_pcb(shape, segs, vias, os.path.join(kdir, "emg_flex_electrodes.kicad_pcb"))
    write_drawing(shape, segs, vias, os.path.join(HERE, "docs", "flex_layout.png"))
    minx, miny, maxx, maxy = shape.bounds
    print(f"outline {maxx - minx:.1f} x {maxy - miny:.1f} mm, area {shape.area / 100:.1f} cm^2")


if __name__ == "__main__":
    main()
