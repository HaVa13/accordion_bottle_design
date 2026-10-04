# accordion_bottle_thermal_analysis.py
# Parametric design and thermal evaluation for a collapsible beverage bottle
# Updated material: PP COPO / Moplen EP310D HP (ALBIS)
# Source: http://hongrunplastics.com/public/uploads/images/20250809/ALBIS%20PP%20COPO%20Moplen%20EP310D%20HP.pdf
# Values used are screening-level engineering estimates based on manufacturer data and PE/PP polymer trends.
# Goal: optimize 300 mL accordion bottle with hot liquid use.

import json
import math
from typing import Any, Dict, List, Tuple

import numpy as np


# ----------------------------
# 1) Material properties: PP COPO / Moplen EP310D HP
# ----------------------------
class PPMaterialProperties:
    def __init__(self):
        self.name = "PP COPO / Moplen EP310D HP"
        self.density_g_cm3 = 0.90
        self.tensile_strength_mpa_rt = 25.0  # nominal yield, ~22-27 MPa
        self.elastic_modulus_mpa = 1100.0
        self.glass_transition_temp_c = -10.0
        self.heat_deflection_temp_045mpa_c = 65.0
        self.heat_deflection_temp_18mpa_c = 50.0
        self.max_service_temp_c = 60.0
        self.melting_temp_c = 160.0
        self.thermal_expansion_coeff_1_per_k = 11e-5  # 110 ppm/K
        self.wall_thickness_mm = 2.2


# ----------------------------
# 2) Temperature-dependent tensile strength model for PP
# ----------------------------
def tensile_strength_vs_temperature(temperature_c: float, material: PPMaterialProperties) -> float:
    """
    Conservative approximation for PP copolymer.
    Strength decreases with temperature, especially beyond ~60°C.
    """
    sigma_ref = material.tensile_strength_mpa_rt
    T_ref = 23.0

    if temperature_c <= material.glass_transition_temp_c:
        sigma = sigma_ref * 1.05
    elif material.glass_transition_temp_c < temperature_c <= material.max_service_temp_c:
        delta_t = temperature_c - T_ref
        reduction = 1.0 - 0.012 * abs(delta_t)
        sigma = sigma_ref * max(0.35, reduction)
    elif material.max_service_temp_c < temperature_c < material.melting_temp_c:
        delta_t = temperature_c - material.max_service_temp_c
        softening_span = material.melting_temp_c - material.max_service_temp_c
        sigma_at_limit = sigma_ref * 0.35
        reduction = math.exp(-0.20 * (delta_t / softening_span))
        sigma = sigma_at_limit * reduction
    else:
        sigma = 0.05

    return max(0.05, sigma)


def safety_factor_vs_temperature(temperature_c: float, material: PPMaterialProperties, design_stress_mpa: float) -> float:
    sigma = tensile_strength_vs_temperature(temperature_c, material)
    if design_stress_mpa <= 0:
        return float("inf")
    return sigma / design_stress_mpa


# ----------------------------
# 3) Stress models
# ----------------------------
def hoop_stress_mpa(internal_pressure_mpa: float, outer_diameter_mm: float, wall_thickness_mm: float) -> float:
    if wall_thickness_mm <= 0:
        return float("inf")
    return (internal_pressure_mpa * outer_diameter_mm) / (2.0 * wall_thickness_mm)


def hydrostatic_pressure_mpa(liquid_height_mm: float, liquid_density_g_cm3: float = 1.0, gravity_m_s2: float = 9.81) -> float:
    height_m = liquid_height_mm / 1000.0
    density_kg_m3 = liquid_density_g_cm3 * 1000.0
    pressure_pa = density_kg_m3 * gravity_m_s2 * height_m
    return pressure_pa / 1e6


def thermal_expansion_stress_mpa(delta_temp_c: float, elastic_modulus_mpa: float,
                                 thermal_expansion_coeff_1_per_k: float = 11e-5) -> float:
    return elastic_modulus_mpa * thermal_expansion_coeff_1_per_k * delta_temp_c


# ----------------------------
# 4) Bellows geometry model
# ----------------------------
def bellows_radius_profile(z_mm: np.ndarray, height_mm: float, diameter_mm: float,
                           folds: int, amplitude_mm: float) -> np.ndarray:
    radius_base_mm = diameter_mm / 2.0
    wave = np.sin(2.0 * np.pi * folds * z_mm / max(height_mm, 1e-6))
    r = radius_base_mm + amplitude_mm * wave
    return np.maximum(r, 2.0)


def bellows_volume_mm3(height_mm: float, diameter_mm: float,
                      folds: int, amplitude_mm: float, samples: int = 4000) -> float:
    z = np.linspace(0.0, height_mm, samples)
    r = bellows_radius_profile(z, height_mm, diameter_mm, folds, amplitude_mm)
    area = np.pi * r**2
    volume = np.trapz(area, z)
    return float(volume)


def compressed_height_estimate(height_mm: float, folds: int, amplitude_mm: float) -> float:
    return max(0.0, height_mm - 0.9 * folds * amplitude_mm)


# ----------------------------
# 5) Feasible design search
# ----------------------------
def generate_feasible_candidates() -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for diameter in np.arange(35.0, 71.0, 1.0):
        for height in np.arange(60.0, 180.0, 1.0):
            for folds in range(4, 28):
                for amplitude in np.arange(1.0, 18.0, 0.5):
                    volume = bellows_volume_mm3(height, diameter, folds, amplitude)
                    volume_ml = volume / 1000.0
                    compressed = compressed_height_estimate(height, folds, amplitude)
                    cand = {
                        "diameter_mm": float(diameter),
                        "height_mm": float(height),
                        "folds": int(folds),
                        "amplitude_mm": float(amplitude),
                        "volume_mm3": float(volume),
                        "volume_ml": float(volume_ml),
                        "compressed_height_mm": float(compressed),
                    }
                    if cand["diameter_mm"] <= 70 and cand["compressed_height_mm"] < 25 and cand["volume_ml"] >= 250 and cand["volume_ml"] <= 340:
                        candidates.append(cand)
    return candidates


def rank_candidate(c: Dict[str, Any]) -> Tuple[float, float, float, float]:
    return (
        abs(c["volume_ml"] - 300.0),
        c["compressed_height_mm"],
        c["diameter_mm"],
        -c["volume_ml"],
    )


# ----------------------------
# 6) Thermal safety evaluation
# ----------------------------
def evaluate_thermal_safety(candidate: Dict[str, Any], operating_temperature_c: float = 85.0,
                            material: PPMaterialProperties = None) -> Dict[str, Any]:
    if material is None:
        material = PPMaterialProperties()

    D = candidate["diameter_mm"]
    H = candidate["height_mm"]
    t = material.wall_thickness_mm

    delta_t = operating_temperature_c - 23.0
    sigma_thermal = thermal_expansion_stress_mpa(delta_t, material.elastic_modulus_mpa, material.thermal_expansion_coeff_1_per_k)
    p_hydrostatic = hydrostatic_pressure_mpa(H, 1.0)
    sigma_hydrostatic = hoop_stress_mpa(p_hydrostatic, D, t)
    sigma_total = sigma_thermal + sigma_hydrostatic
    sigma_material = tensile_strength_vs_temperature(operating_temperature_c, material)
    sf = safety_factor_vs_temperature(operating_temperature_c, material, sigma_total)

    return {
        "operating_temperature_c": operating_temperature_c,
        "thermal_expansion_stress_mpa": float(sigma_thermal),
        "hydrostatic_stress_mpa": float(sigma_hydrostatic),
        "combined_stress_mpa": float(sigma_total),
        "material_strength_at_temp_mpa": float(sigma_material),
        "safety_factor": float(sf),
        "is_safe": sf >= 2.0,
        "margin_to_failure_pct": float((sigma_material - sigma_total) / sigma_material * 100.0) if sigma_material > 0 else 0.0,
    }


# ----------------------------
# 7) Main analysis
# ----------------------------
def main() -> None:
    material = PPMaterialProperties()

    print("=" * 100)
    print("Accordion bottle design - material update to PP COPO / Moplen EP310D HP")
    print("=" * 100)
    print("Material properties used:")
    print(f"- Density: {material.density_g_cm3} g/cm3")
    print(f"- Tensile strength (yield): ~{material.tensile_strength_mpa_rt} MPa")
    print(f"- Glass transition: {material.glass_transition_temp_c}°C")
    print(f"- HDT @0.45 MPa: {material.heat_deflection_temp_045mpa_c}°C")
    print(f"- HDT @1.8 MPa: {material.heat_deflection_temp_18mpa_c}°C")
    print(f"- Max service temp used in screening: {material.max_service_temp_c}°C")
    print(f"- CTE: {material.thermal_expansion_coeff_1_per_k} /°C")

    temps = np.array([-20, 0, 23, 40, 60, 80, 90, 100, 120])
    print("\nStrength vs temperature:")
    print(f"{'Temp (°C)':>10} {'Strength (MPa)':>18}")
    print("-" * 32)
    for t in temps:
        s = tensile_strength_vs_temperature(float(t), material)
        print(f"{t:>10.0f} {s:>18.2f}")

    candidates = sorted(generate_feasible_candidates(), key=rank_candidate)
    print(f"\nFeasible candidate count: {len(candidates)}")
    for i, c in enumerate(candidates[:10], 1):
        print(f"{i:>2}. D={c['diameter_mm']:>5.1f} mm | H={c['height_mm']:>5.1f} mm | F={c['folds']:>2} | amp={c['amplitude_mm']:>4.1f} mm | V={c['volume_ml']:>6.1f} mL | comp={c['compressed_height_mm']:>5.1f} mm")

    best = candidates[0]
    print("\nBest candidate:")
    print(best)

    for temp in [60, 70, 80, 90, 100]:
        result = evaluate_thermal_safety(best, operating_temperature_c=temp, material=material)
        print(f"\nAt {temp}°C:")
        for k, v in result.items():
            print(f"  {k}: {v}")

    report = {
        "material": {
            "name": material.name,
            "density_g_cm3": material.density_g_cm3,
            "tensile_strength_mpa_rt": material.tensile_strength_mpa_rt,
            "elastic_modulus_mpa": material.elastic_modulus_mpa,
            "heat_deflection_temp_045mpa_c": material.heat_deflection_temp_045mpa_c,
            "heat_deflection_temp_18mpa_c": material.heat_deflection_temp_18mpa_c,
            "glass_transition_temp_c": material.glass_transition_temp_c,
            "thermal_expansion_coeff_1_per_k": material.thermal_expansion_coeff_1_per_k,
            "source": "http://hongrunplastics.com/public/uploads/images/20250809/ALBIS%20PP%20COPO%20Moplen%20EP310D%20HP.pdf",
        },
        "best_design": best,
    }

    with open("pp_material_analysis_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\nSaved pp_material_analysis_report.json")


if __name__ == "__main__":
    main()
