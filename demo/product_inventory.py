"""
Leeway Parts Product Inventory — keyword matching catalog.

Used by demo.py to filter demand signals against actual available products.
Only keep signals where we have matching parts in stock.
"""

# ── Product keyword catalog ──────────────────────────────────────────────
# Each entry: keywords that appear in buyer descriptions → our product match.
# order matters: first match wins.

PRODUCT_CATALOG = [
    # ── 空气预滤器 (Air Pre-Cleaners) — 17 models, Z3/Z4/Z5/ZN3 ──
    {
        "keywords": ["air pre-cleaner", "pre cleaner", "pre-cleaner",
                     "air cleaner", "pre filter", "pre-filter", "air intake"],
        "brand": "Kubota",
        "category": "Engine Parts > Intake System",
    },
    # ── 齿轮 (Gears) — 24 OEM-confirmed ──
    {
        "keywords": ["gear", "transmission gear", "pto gear", "spline",
                     "bevel gear", "spur gear", "differential gear"],
        "brand": "Kubota",
        "category": "Transmission & Drivetrain > Gears",
    },
    # ── 座椅 (Seats) — JT-01 to JT-08 ──
    {
        "keywords": ["seat", "tractor seat", "suspension seat", "driver seat",
                     "operator seat", "bucket seat", "fabric seat"],
        "brand": "Universal",
        "category": "Tractor Body & Cab Parts > Seats",
    },
    # ── 格栅/大灯 (Grille & Headlight) — 2 products with Alibaba inquiries ──
    {
        "keywords": ["grille", "headlight", "head light", "light assembly",
                     "front grille", "face shield", "headlamp",
                     "light housing", "led light", "work light"],
        "brand": "Kubota",
        "category": "Tractor Body & Cab Parts > Grille & Headlight",
    },
    # ── 液压泵 (Hydraulic Pump) ──
    {
        "keywords": ["hydraulic pump", "hydraulic motor", "oil pump",
                     "gear pump", "pto pump", "hydraulic gear pump"],
        "brand": "Kubota",
        "category": "Hydraulic Parts > Hydraulic Pump",
    },
    # ── 液压油缸 (Hydraulic Cylinder) ──
    {
        "keywords": ["hydraulic cylinder", "steering cylinder",
                     "power steering cylinder", "lift cylinder",
                     "tilt cylinder", "bucket cylinder"],
        "brand": "Kubota",
        "category": "Hydraulic Parts > Hydraulic Cylinder",
    },
    # ── 控制阀 (Control Valve) ──
    {
        "keywords": ["control valve", "hydraulic valve", "directional valve",
                     "spool valve", "monoblock valve", "relief valve",
                     "check valve"],
        "brand": "Kubota",
        "category": "Hydraulic Parts > Control Valve",
    },
    # ── 提升连杆/三点悬挂 (Lift Link & 3-Point Hitch) ──
    {
        "keywords": ["lift link", "lift arm", "lift rod", "top link",
                     "tie rod", "tie rod end", "stabilizer", "drag link",
                     "three point hitch", "3 point hitch", "3-point hitch",
                     "drawbar", "lower link", "stabilizer chain"],
        "brand": "Kubota",
        "category": "Linkage & Hitch Parts",
    },
    # ── PTO 部件 ──
    {
        "keywords": ["pto shaft", "pto clutch", "pto drive", "pto bearing",
                     "power take off", "power take-off", "pto assembly",
                     "pto adapter"],
        "brand": "Kubota",
        "category": "Transmission & Drivetrain > PTO Components",
    },
    # ── 离合器 (Clutch) ──
    {
        "keywords": ["clutch", "clutch plate", "clutch disc", "clutch kit",
                     "clutch assembly", "clutch pressure plate",
                     "clutch release bearing", "clutch cover"],
        "brand": "Kubota",
        "category": "Transmission & Drivetrain > Clutch Parts",
    },
    # ── 车桥/轴承 (Axle & Bearing) ──
    {
        "keywords": ["front axle", "rear axle", "axle shaft", "axle housing",
                     "bearing", "ball bearing", "roller bearing",
                     "wheel bearing", "axle bearing",
                     "final drive", "final drive case"],
        "brand": "Kubota",
        "category": "Transmission & Drivetrain > Axle Parts",
    },
    # ── 发动机件 (Engine Parts) ──
    {
        "keywords": ["water pump", "fuel pump", "fuel injector",
                     "fuel filter", "oil filter", "air filter",
                     "alternator", "starter motor", "starter",
                     "glow plug", "thermostat", "radiator",
                     "piston", "piston ring", "cylinder liner",
                     "cylinder head", "gasket", "gasket kit",
                     "oil seal", "crankshaft seal", "valve seal",
                     "valve", "valve guide", "connecting rod",
                     "camshaft", "crankshaft",
                     "fuel line", "intake hose", "coolant hose",
                     "exhaust manifold", "intake manifold"],
        "brand": "Kubota/Yanmar",
        "category": "Engine Parts",
    },
    # ── 割草机/收割机配件 (Harvester) ──
    {
        "keywords": ["cutterbar", "harvester blade", "sickle bar",
                     "threshing", "concave", "sprocket", "chain",
                     "combine part", "harvester knife"],
        "brand": "Kubota/Yanmar",
        "category": "Harvester Accessories",
    },
    # ── 车罩/挡泥板 (Hood / Fender) ──
    {
        "keywords": ["hood", "fender", "bonnet", "engine cover",
                     "side panel", "dash panel", "cowling"],
        "brand": "Kubota",
        "category": "Tractor Body & Cab Parts > Hood & Fender",
    },
    # ── 紧固件/通用件 (Fasteners, low priority but we carry them) ──
    {
        "keywords": ["bolt", "nut", "washer", "pin", "cotter pin",
                     "spring", "shim", "spacer", "bushing",
                     "snap ring", "circlip", "o-ring", "seal",
                     "u-joint", "universal joint"],
        "brand": "Universal",
        "category": "Other > Fasteners & Hardware",
    },
]

# ── Negative keywords — these are NOT our products ─────────────────────
NEGATIVE_KEYWORDS = [
    "software", "computer", "laptop", "video game",
    "car part", "automobile", "pickup truck", "suv",
    "lawn mower", "lawnmower", "garden tractor",
    "chainsaw", "weed eater", "string trimmer",
    "construction equipment", "excavator", "bulldozer",
]

# ── Matching logic ─────────────────────────────────────────────────────

def match_product(signal: dict) -> dict:
    """Check if an extracted signal matches Leeway Parts inventory.

    Modifies signal in-place, adding:
      has_product: bool
      matched_category: str | None
      matched_brand: str | None
    """
    part = (signal.get("part_type") or "").lower()
    model = (signal.get("machine_model") or "").lower()

    # ── Step 1: negative filter ──
    for nk in NEGATIVE_KEYWORDS:
        if nk in part or nk in model:
            signal["has_product"] = False
            signal["match_reason"] = f"not our product: {nk}"
            signal["matched_category"] = None
            signal["matched_brand"] = None
            return signal

    # ── Step 2: match against catalog ──
    for product in PRODUCT_CATALOG:
        for kw in product["keywords"]:
            if kw in part:
                signal["has_product"] = True
                signal["matched_category"] = product["category"]
                signal["matched_brand"] = product["brand"]
                signal["match_reason"] = f"matched keyword: {kw}"
                return signal

    # ── No match ──
    signal["has_product"] = False
    signal["match_reason"] = "no matching product in inventory"
    signal["matched_category"] = None
    signal["matched_brand"] = None
    return signal
