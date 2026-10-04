# accordion_bottle_thermal_analysis.py
# Final parametric design + optimization + 3D mesh generation
# Target: accordion beverage pack for 300 mL, max diameter 70 mm,
# compressed height <25 mm, hot water use, PP COPO / Moplen EP310D HP
# File output: final_accordion_bottle.obj and final_design_summary.json

import json
import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Tuple

import numpy as np


# ============================================================
# 1) Material data for PP COPO / Moplen EP310D HP
# ============================================================
@dataclass
class MaterialPP:
    name: str = "PP COPO / Moplen EP310D HP"
    density_g_cm3: float = 0.90
    tensile_strength_mpa_rt: float = 25.0
    elastic_modulus_mpa: float = 1100.0
    glass_transition_temp_c: float = -10.0
    heat_deflection_temp_045mpa_c: float = 65.0
    heat_deflection_temp_18mpa_c: float = 50.0
    max_service_temp_c: float = 60.0
    melting_temp_c: float = 160.0
    thermal_expansion_coeff_1_per_k: float = 11e-5
    wall_thickness_mm: float = 2.2


MATERIAL = MaterialPP()


# ============================================================
# 2) Design constraints
# ============================================================
TARGET_VOLUME_ML = 300.0
MIN_WATER_CAPACITY_ML = 250.0
MAX_DIAMETER_MM = 70.0
MAX_COMPRESSED_HEIGHT_MM = 25.0
TARGET_OPERATING_TEMP_C = 80.0
SAFETY_TARGET = 2.0


# ============================================================
# 3) Material strength vs temperature
# ============================================================
def tensile_strength_vs_temperature(temperature_c: float, material: MaterialPP = MATERIAL) -> float:
    sigma_ref = material.tensile_strength_mpa_rt
    T_ref = 23.0

    if temperature_c <= material.glass_transition_temp_c:
        return max(0.05, sigma_ref * 1.05)

    if material.glass_transition_temp_c < temperature_c <= material.max_service_temp_c:
        delta_t = temperature_c - T_ref
        reduction = 1.0 - 0.012 * abs(delta_t)
        sigma = sigma_ref * max(0.35, reduction)
        return max(0.05, sigma)

    if material.max_service_temp_c < temperature_c < material.melting_temp_c:
        delta_t = temperature_c - material.max_service_temp_c
        softening_span = material.melting_temp_c - material.max_service_temp_c
        sigma_at_limit = sigma_ref * 0.35
        reduction = math.exp(-0.20 * (delta_t / softening_span))
        sigma = sigma_at_limit * reduction
        return max(0.05, sigma)

    return 0.05


# ============================================================
# 4) Stress and structural checks
# ============================================================
def hydrostatic_pressure_mpa(liquid_height_mm: float, density_g_cm3: float = 1.0, g: float = 9.81) -> float:
    height_m = liquid_height_mm / 1000.0
    density_kg_m3 = density_g_cm3 * 1000.0
    pressure_pa = density_kg_m3 * g * height_m
    return pressure_pa / 1e6


def hoop_stress_mpa(internal_pressure_mpa: float, diameter_mm: float, wall_thickness_mm: float) -> float:
    if wall_thickness_mm <= 0:
        return float("inf")
    return (internal_pressure_mpa * diameter_mm) / (2.0 * wall_thickness_mm)


def thermal_expansion_stress_mpa(delta_temp_c: float, elastic_modulus_mpa: float,
                                 thermal_expansion_coeff_1_per_k: float) -> float:
    return elastic_modulus_mpa * thermal_expansion_coeff_1_per_k * delta_temp_c


def evaluate_thermal_safety(candidate: Dict[str, Any], temperature_c: float = TARGET_OPERATING_TEMP_C,
                            material: MaterialPP = MATERIAL) -> Dict[str, Any]:
    D = candidate["diameter_mm"]
    H = candidate["height_mm"]
    wall = material.wall_thickness_mm

    delta_t = temperature_c - 23.0
    sigma_thermal = thermal_expansion_stress_mpa(delta_t, material.elastic_modulus_mpa,
                                                material.thermal_expansion_coeff_1_per_k)
    p_hydro = hydrostatic_pressure_mpa(H, 1.0)
    sigma_hydro = hoop_stress_mpa(p_hydro, D, wall)
    sigma_total = sigma_thermal + sigma_hydro
    sigma_material = tensile_strength_vs_temperature(temperature_c, material)
    safety_factor = sigma_material / sigma_total if sigma_total > 0 else float("inf")

    return {
        "temperature_c": temperature_c,
        "thermal_stress_mpa": sigma_thermal,
        "hydrostatic_stress_mpa": sigma_hydro,
        "combined_stress_mpa": sigma_total,
        "material_strength_mpa": sigma_material,
        "safety_factor": safety_factor,
        "is_safe": safety_factor >= SAFETY_TARGET,
        "margin_pct": ((sigma_material - sigma_total) / sigma_material * 100.0) if sigma_material > 0 else 0.0,
    }


# ============================================================
# 5) Accordion geometry
# ============================================================
def bellows_radius_profile(z_mm: np.ndarray, height_mm: float, diameter_mm: float,
                           folds: int, amplitude_mm: float) -> np.ndarray:
    radius_base = diameter_mm / 2.0
    wave = np.sin(2.0 * np.pi * folds * z_mm / max(height_mm, 1e-6))
    return np.maximum(radius_base + amplitude_mm * wave, 2.0)


def bellows_volume_mm3(height_mm: float, diameter_mm: float, folds: int, amplitude_mm: float,
                      samples: int = 4000) -> float:
    z = np.linspace(0.0, height_mm, samples)
    r = bellows_radius_profile(z, height_mm, diameter_mm, folds, amplitude_mm)
    area = np.pi * r**2
    volume = np.trapz(area, z)
    return float(volume)


def compressed_height_estimate(height_mm: float, folds: int, amplitude_mm: float) -> float:
    return max(0.0, height_mm - 0.9 * folds * amplitude_mm)


# ============================================================
# 6) Feasible design search and optimization
# ============================================================
def is_geometry_feasible(candidate: Dict[str, Any]) -> bool:
    D = candidate["diameter_mm"]
    H = candidate["height_mm"]
    V_ml = candidate["volume_ml"]
    compressed_h = candidate["compressed_height_mm"]

    if D > MAX_DIAMETER_MM:
        return False
    if compressed_h >= MAX_COMPRESSED_HEIGHT_MM:
        return False
    if V_ml < MIN_WATER_CAPACITY_ML:
        return False
    if V_ml > 340.0:
        return False
    if H <= 0:
        return False
    return True


def design_objective(candidate: Dict[str, Any]) -> float:
    # prioritize closeness to target volume, then low compressed height, then compactness.
    penalty = abs(candidate["volume_ml"] - TARGET_VOLUME_ML) / TARGET_VOLUME_ML
    penalty += 0.4 * (candidate["compressed_height_mm"] / MAX_COMPRESSED_HEIGHT_MM)
    penalty += 0.2 * (candidate["diameter_mm"] / MAX_DIAMETER_MM)
    return penalty


def generate_candidate_space() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    for diameter in np.arange(40.0, MAX_DIAMETER_MM + 1.0, 1.0):
        for height in np.arange(75.0, 170.0, 1.0):
            for folds in range(5, 20):
                for amplitude in np.arange(1.5, 12.0, 0.5):
                    volume_mm3 = bellows_volume_mm3(height, diameter, folds, amplitude, samples=3500)
                    volume_ml = volume_mm3 / 1000.0
                    compressed_h = compressed_height_estimate(height, folds, amplitude)

                    cand = {
                        "diameter_mm": float(diameter),
                        "height_mm": float(height),
                        "folds": int(folds),
                        "amplitude_mm": float(amplitude),
                        "volume_mm3": float(volume_mm3),
                        "volume_ml": float(volume_ml),
                        "compressed_height_mm": float(compressed_h),
                    }

                    if is_geometry_feasible(cand):
                        thermal = evaluate_thermal_safety(cand, TARGET_OPERATING_TEMP_C, MATERIAL)
                        cand["thermal_80c"] = thermal
                        cand["penalty"] = design_objective(cand)
                        results.append(cand)

    return results


def select_best_candidate(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not candidates:
        raise ValueError("No feasible designs found.")

    ranked = sorted(candidates, key=lambda c: (c["penalty"], c["compressed_height_mm"], c["diameter_mm"]))
    return ranked[0]


# ============================================================
# 7) Mesh generation for 3D OBJ export
# ============================================================
def generate_bellows_obj(candidate: Dict[str, Any], file_path: str = "final_accordion_bottle.obj") -> None:
    H = candidate["height_mm"]
    D = candidate["diameter_mm"]
    folds = candidate["folds"]
    amplitude = candidate["amplitude_mm"]

    z_steps = 220
    theta_steps = 120
    z = np.linspace(0.0, H, z_steps)
    r = bellows_radius_profile(z, H, D, folds, amplitude)

    vertices: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int]] = []

    # Build ring vertices: each profile point adds a circular ring
    for i in range(z_steps):
        zz = z[i]
        rad = r[i]
        for j in range(theta_steps):
            theta = 2.0 * math.pi * j / theta_steps
            x = rad * math.cos(theta)
            y = rad * math.sin(theta)
            vertices.append((x, y, zz))

    ring_size = theta_steps
    for i in range(z_steps - 1):
        for j in range(theta_steps):
            a = i * ring_size + j
            b = i * ring_size + (j + 1) % ring_size
            c = (i + 1) * ring_size + j
            d = (i + 1) * ring_size + (j + 1) % ring_size

            # two triangles per quad
            faces.append((a, b, c))
            faces.append((b, d, c))

    # Add bottom and top caps to close the shape
    bottom_center = len(vertices)
    top_center = bottom_center + 1
    vertices.append((0.0, 0.0, 0.0))
    vertices.append((0.0, 0.0, H))

    bottom_ring_start = 0
    top_ring_start = (z_steps - 1) * ring_size

    for j in range(theta_steps):
        a = bottom_ring_start + j
        b = bottom_ring_start + (j + 1) % ring_size
        faces.append((bottom_center, a, b))

    for j in range(theta_steps):
        a = top_ring_start + j
        b = top_ring_start + (j + 1) % ring_size
        faces.append((top_center, b, a))

    # Write OBJ file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("# Final accordion bottle mesh\n")
        f.write(f"# volume_ml={candidate['volume_ml']:.2f}\n")
        f.write(f"# diameter_mm={candidate['diameter_mm']:.2f}\n")
        f.write(f"# height_mm={candidate['height_mm']:.2f}\n")
        f.write(f"# folds={candidate['folds']}\n")
        f.write(f"# amplitude_mm={candidate['amplitude_mm']:.2f}\n")
        f.write("\n")

        for x, y, zc in vertices:
            f.write(f"v {x:.6f} {y:.6f} {zc:.6f}\n")

        for a, b, c in faces:
            f.write(f"f {a + 1} {b + 1} {c + 1}\n")

    print(f"OBJ mesh exported to: {file_path}")


# ============================================================
# 8) Final run
# ============================================================
def main() -> None:
    print("=" * 110)
    print("Final accordion bottle optimization for PP COPO / Moplen EP310D HP")
    print("=" * 110)
    print(f"Target volume: {TARGET_VOLUME_ML} mL")
    print(f"Minimum capacity: {MIN_WATER_CAPACITY_ML} mL")
    print(f"Max diameter: {MAX_DIAMETER_MM} mm")
    print(f"Compressed height limit: {MAX_COMPRESSED_HEIGHT_MM} mm")
    print(f"Recommended operating temp: {TARGET_OPERATING_TEMP_C}°C")
    print(f"Safety target: {SAFETY_TARGET}")
    print()

    candidates = generate_candidate_space()
    print(f"Feasible designs found: {len(candidates)}")

    if not candidates:
        raise SystemExit("No feasible designs found for the requested constraints.")

    best = select_best_candidate(candidates)
    thermal = evaluate_thermal_safety(best, TARGET_OPERATING_TEMP_C, MATERIAL)

    print("Top candidates (sorted by objective):")
    ranked = sorted(candidates, key=lambda c: (c["penalty"], c["compressed_height_mm"], c["diameter_mm"]))
    for i, c in enumerate(ranked[:10], 1):
        print(
            f"{i}. D={c['diameter_mm']:.1f} mm | H={c['height_mm']:.1f} mm | "
            f"F={c['folds']} | amp={c['amplitude_mm']:.1f} mm | "
            f"V={c['volume_ml']:.1f} mL | comp={c['compressed_height_mm']:.1f} mm | "
            f"SF@{TARGET_OPERATING_TEMP_C}°C={c['thermal_80c']['safety_factor']:.2f}"
        )

    print("\nSelected best design:")
    print(json.dumps(best, indent=2, ensure_ascii=False))
    print("\nThermal safety at target temperature:")
    print(json.dumps(thermal, indent=2, ensure_ascii=False))

    # Save summary JSON
    summary = {
        "material": asdict(MATERIAL),
        "constraints": {
            "target_volume_ml": TARGET_VOLUME_ML,
            "min_capacity_ml": MIN_WATER_CAPACITY_ML,
            "max_diameter_mm": MAX_DIAMETER_MM,
            "max_compressed_height_mm": MAX_COMPRESSED_HEIGHT_MM,
            "target_operating_temp_c": TARGET_OPERATING_TEMP_C,
            "safety_target": SAFETY_TARGET,
        },
        "best_candidate": best,
        "thermal_safety": thermal,
        "note": "For PP COPO, safe operating use is generally best below 80°C; above this, thicker wall or multilayer design is recommended."
    }

    with open("final_design_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    generate_bellows_obj(best, "final_accordion_bottle.obj")

    print("\nSaved: final_design_summary.json")
    print("Saved: final_accordion_bottle.obj")


if __name__ == "__main__":
    main()
