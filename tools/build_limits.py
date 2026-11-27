"""
Construit lmu_limits.json : les vraies limites (premier et dernier cran) de chaque réglage, voiture par voiture,
à partir des relevés du garage de LMU (/rest/garage/getPlayerGarageData : minValue, maxValue = NOMBRE de crans).

  python tools/build_limits.py relevé_compact.json  ->  lmu_limits.json

Clé d'une voiture : le modèle en minuscules sans espaces (« porsche911gt3rlmgt3 »), comme dans le .svm
(« Porsche_911_GT3_R_LMGT3 »). Clé d'un réglage : « SECTION/Clé » du .svm.
"""
import json, re, sys
from pathlib import Path

WHEEL = {"FL": "FRONTLEFT", "FR": "FRONTRIGHT", "RL": "REARLEFT", "RR": "REARRIGHT"}
# noms du garage (VM_…) -> (section, clé) du .svm
VM = {
    "FRONT_ANTISWAY": ("SUSPENSION", "FrontAntiSwaySetting"), "REAR_ANTISWAY": ("SUSPENSION", "RearAntiSwaySetting"),
    "FRONT_TOEIN": ("SUSPENSION", "FrontToeInSetting"), "REAR_TOEIN": ("SUSPENSION", "RearToeInSetting"),
    "FRONT_TOEOFFSET": ("SUSPENSION", "FrontToeOffsetSetting"), "REAR_TOEOFFSET": ("SUSPENSION", "RearToeOffsetSetting"),
    "FRONT_WING": ("FRONTWING", "FWSetting"), "REAR_WING": ("REARWING", "RWSetting"),
    "BRAKE_BALANCE": ("CONTROLS", "RearBrakeSetting"), "BRAKE_PRESSURE": ("CONTROLS", "BrakePressureSetting"),
    "BRAKE_MIGRATION": ("CONTROLS", "BrakeMigrationSetting"), "STEER_LOCK": ("CONTROLS", "SteerLockSetting"),
    "TRACTIONCONTROLMAP": ("CONTROLS", "TractionControlMapSetting"),
    "TRACTIONCONTROLPOWERCUTMAP": ("CONTROLS", "TCPowerCutMapSetting"),
    "TRACTIONCONTROLSLIPANGLEMAP": ("CONTROLS", "TCSlipAngleMapSetting"),
    "ANTILOCKBRAKESYSTEMMAP": ("CONTROLS", "AntilockBrakeSystemMapSetting"),
    "BRAKE_DUCTS": ("BODYAERO", "BrakeDuctSetting"), "BRAKE_DUCTS_REAR": ("BODYAERO", "BrakeDuctRearSetting"),
    "WATER_RADIATOR": ("BODYAERO", "WaterRadiatorSetting"), "OIL_RADIATOR": ("BODYAERO", "OilRadiatorSetting"),
    "ENGINE_MIXTURE": ("ENGINE", "EngineMixtureSetting"), "ENGINE_BRAKEMAP": ("ENGINE", "EngineBrakingMapSetting"),
    "ENGINE_BOOST": ("ENGINE", "EngineBoostSetting"), "REGEN_LEVEL": ("ENGINE", "RegenerationMapSetting"),
    "ELECTRIC_MOTOR_MAP": ("ENGINE", "ElectricMotorMapSetting"), "REV_LIMITER": ("ENGINE", "RevLimitSetting"),
    "DIFF_PRELOAD": ("DRIVELINE", "DiffPreloadSetting"), "DIFF_POWER": ("DRIVELINE", "DiffPowerSetting"),
    "DIFF_COAST": ("DRIVELINE", "DiffCoastSetting"), "DIFF_PUMP": ("DRIVELINE", "DiffPumpSetting"),
    "FRONT_DIFF_PRELOAD": ("DRIVELINE", "FrontDiffPreloadSetting"), "FRONT_DIFF_POWER": ("DRIVELINE", "FrontDiffPowerSetting"),
    "FRONT_DIFF_COAST": ("DRIVELINE", "FrontDiffCoastSetting"), "GEAR_FINAL": ("DRIVELINE", "FinalDriveSetting"),
    "FRONT_3RD_SPRING": ("SUSPENSION", "Front3rdSpringSetting"), "REAR_3RD_SPRING": ("SUSPENSION", "Rear3rdSpringSetting"),
    "FRONT_3RD_PACKERS": ("SUSPENSION", "Front3rdPackerSetting"), "REAR_3RD_PACKERS": ("SUSPENSION", "Rear3rdPackerSetting"),
    "FRONT_3RD_SLOWBUMP": ("SUSPENSION", "Front3rdSlowBumpSetting"), "REAR_3RD_SLOWBUMP": ("SUSPENSION", "Rear3rdSlowBumpSetting"),
    "FRONT_3RD_FASTBUMP": ("SUSPENSION", "Front3rdFastBumpSetting"), "REAR_3RD_FASTBUMP": ("SUSPENSION", "Rear3rdFastBumpSetting"),
    "FRONT_3RD_SLOWREBOUND": ("SUSPENSION", "Front3rdSlowReboundSetting"), "REAR_3RD_SLOWREBOUND": ("SUSPENSION", "Rear3rdSlowReboundSetting"),
    "FRONT_3RD_FASTREBOUND": ("SUSPENSION", "Front3rdFastReboundSetting"), "REAR_3RD_FASTREBOUND": ("SUSPENSION", "Rear3rdFastReboundSetting"),
}
WM = {"CAMBER": "CamberSetting", "PRESSURE": "PressureSetting", "PACKERS": "PackerSetting", "SPRING": "SpringSetting",
      "RIDEHEIGHT": "RideHeightSetting", "SLOWBUMP": "SlowBumpSetting", "FASTBUMP": "FastBumpSetting",
      "SLOWREBOUND": "SlowReboundSetting", "FASTREBOUND": "FastReboundSetting", "COMPOUND": "CompoundSetting",
      "BRAKEDISC": "BrakeDiscSetting", "BRAKEPAD": "BrakePadSetting", "TENDERSPRING": "TenderSpringSetting",
      "TENDERTRAVEL": "TenderTravelSetting"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def build(src: dict) -> dict:
    out, unknown = {}, set()
    for f, v in src.items():
        tree = v.get("tree") or ""
        model = tree.split(",")[-1].strip()
        g = v.get("garage") or {}
        if not model or model == "?" or not g:
            continue
        lim = {}
        for k, x in g.items():
            if not x.get("available") or x.get("maxValue") is None:
                continue
            lo, n = x.get("minValue") or 0, x["maxValue"]
            if n <= 1:
                continue                          # non réglable sur cette voiture
            key = None
            if k.startswith("VM_") and k[3:] in VM:
                sec, kk = VM[k[3:]]
                key = f"{sec}/{kk}"
            elif k.startswith("WM_"):
                m = re.match(r"WM_([A-Z]+)-W_(FL|FR|RL|RR)$", k)
                if m and m.group(1) in WM:
                    key = f"{WHEEL[m.group(2)]}/{WM[m.group(1)]}"
            if key is None:
                unknown.add(k)
                continue
            lim[key] = [lo, n - 1]                # maxValue = NOMBRE de crans : dernier cran = maxValue − 1
        out[norm(model)] = {"name": model, "class": (tree.split(",")[1].strip() if tree.count(",") >= 2 else ""),
                            "limits": dict(sorted(lim.items()))}
    return out, sorted(unknown)


if __name__ == "__main__":
    src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    res, unk = build(src)
    dst = Path(__file__).resolve().parent.parent / "lmu_limits.json"
    dst.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(res)} voitures -> {dst.name}")
    for k, v in res.items():
        print(f"  {v['name']:40s} {len(v['limits'])} réglages")
    if unk:
        print("non reliés :", ", ".join(unk))
