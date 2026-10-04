# accordion_comprehensive_structural_thermal_analysis.py
# COMPREHENSIVE STRUCTURAL & THERMAL ANALYSIS
# Accordion Bottle Design for PP COPO / Moplen EP310D HP
#
# Includes:
#   1. Stress Analysis (Hoop, Bending, Torsional)
#   2. Thermal Analysis (Distribution, Expansion Stress)
#   3. Spring Back Analysis (Viscoelastic Recovery)
#   4. Buckling Analysis (Euler & Geometric Instability)
#   5. Lateral Forces & Impact Analysis
#   6. Hand Pressure Effects & Fatigue
#
# Usage: python accordion_comprehensive_structural_thermal_analysis.py

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Tuple, Any
from datetime import datetime

import numpy as np
from scipy import integrate, optimize


# ============================================================
# 1) Material Properties for PP COPO
# ============================================================
@dataclass
class MaterialPPCOPO:
    name: str = "PP COPO / Moplen EP310D HP"
    density_kg_m3: float = 900.0
    tensile_strength_mpa_rt: float = 25.0
    elastic_modulus_rt_mpa: float = 1100.0
    glass_transition_temp_c: float = -10.0
    max_service_temp_c: float = 60.0
    melting_temp_c: float = 160.0
    cte_1_per_k: float = 11e-5
    poisson_ratio: float = 0.40
    yield_strain_percent: float = 8.0
    elongation_at_break_percent: float = 600.0
    fatigue_strength_mpa: float = 8.0  # Typical for PP at 10^7 cycles
    relaxation_modulus_decay: float = 0.65  # Modulus retention after 1000 hours
    viscosity_parameter_pa_s: float = 1e8  # Viscous damping parameter
    thermal_conductivity_w_mk: float = 0.33
    specific_heat_j_kg_k: float = 1900.0


MATERIAL = MaterialPPCOPO()


# ============================================================
# 2) Accordion Bottle Model Definition
# ============================================================
@dataclass
class AccordionBottleDesign:
    model_id: str
    diameter_mm: float
    height_mm: float
    folds: int
    amplitude_mm: float
    wall_thickness_mm: float
    top_cap_diameter_mm: float
    compressed_height_mm: float
    target_volume_ml: float


# Reference design (Model A)
DESIGN_A = AccordionBottleDesign(
    model_id="A",
    diameter_mm=70.0,
    height_mm=125.0,
    folds=11,
    amplitude_mm=8.0,
    wall_thickness_mm=2.2,
    top_cap_diameter_mm=73.0,
    compressed_height_mm=22.0,
    target_volume_ml=300.0
)


# ============================================================
# 3) STRESS ANALYSIS
# ============================================================
class StressAnalysis:
    def __init__(self, design: AccordionBottleDesign, material: MaterialPPCOPO):
        self.design = design
        self.material = material
    
    def hoop_stress_mpa(self, internal_pressure_mpa: float) -> float:
        """
        Hoop stress in thin-walled cylinder under internal pressure.
        σ_hoop = (P * D) / (2 * t)
        """
        D = self.design.diameter_mm
        t = self.design.wall_thickness_mm
        if t <= 0:
            return float('inf')
        return (internal_pressure_mpa * D) / (2.0 * t)
    
    def bending_stress_mpa(self, bending_moment_nm: float) -> float:
        """
        Bending stress in cylindrical shell.
        σ_bending = M * c / I
        where c = radius, I = second moment of inertia
        """
        r = self.design.diameter_mm / 2.0
        t = self.design.wall_thickness_mm
        # Second moment of inertia for thin cylindrical shell
        I = (math.pi * r**3 * t) / 4.0
        c = r
        if I <= 0:
            return 0.0
        return (bending_moment_nm * 1000 * c) / I  # Convert N·m to N·mm
    
    def torsional_stress_mpa(self, torque_nm: float) -> float:
        """
        Torsional shear stress in cylindrical shell.
        τ = (T * r) / J
        where J = polar moment of inertia
        """
        r = self.design.diameter_mm / 2.0
        t = self.design.wall_thickness_mm
        # Polar moment for thin shell
        J = (math.pi * r**3 * t) / 2.0
        if J <= 0:
            return 0.0
        return (torque_nm * 1000 * r) / J
    
    def combined_stress_mpa(self, internal_pressure_mpa: float, 
                           bending_moment_nm: float, 
                           torque_nm: float) -> float:
        """
        Von Mises equivalent stress combining all components.
        σ_vm = sqrt(σ_hoop² + σ_bending² + 3*τ²)
        """
        sigma_h = self.hoop_stress_mpa(internal_pressure_mpa)
        sigma_b = self.bending_stress_mpa(bending_moment_nm)
        tau = self.torsional_stress_mpa(torque_nm)
        
        vm_stress = math.sqrt(sigma_h**2 + sigma_b**2 + 3 * tau**2)
        return vm_stress
    
    def stress_concentration_factor(self, radius_of_curvature_mm: float) -> float:
        """
        Stress concentration factor due to geometric discontinuities (folds).
        Kt ≈ 1 + 2*(h/ρ) for notches
        h = depth of notch, ρ = radius of curvature
        """
        h = self.design.amplitude_mm  # Notch depth
        rho = max(radius_of_curvature_mm, 0.5)
        Kt = 1.0 + 2.0 * (h / rho)
        return min(Kt, 3.0)  # Cap at 3.0 for conservative estimate
    
    def effective_stress_with_concentration(self, base_stress_mpa: float,
                                          radius_of_curvature_mm: float = 1.0) -> float:
        """Apply stress concentration factor."""
        Kt = self.stress_concentration_factor(radius_of_curvature_mm)
        return base_stress_mpa * Kt
    
    def safety_factor(self, equivalent_stress_mpa: float) -> float:
        """Calculate safety factor vs. yield stress."""
        yield_stress = self.material.tensile_strength_mpa_rt * 0.7  # Approximate yield
        if equivalent_stress_mpa <= 0:
            return float('inf')
        return yield_stress / equivalent_stress_mpa


# ============================================================
# 4) THERMAL ANALYSIS
# ============================================================
class ThermalAnalysis:
    def __init__(self, design: AccordionBottleDesign, material: MaterialPPCOPO):
        self.design = design
        self.material = material
    
    def temperature_dependent_modulus(self, temperature_c: float) -> float:
        """Elastic modulus degradation with temperature."""
        E_rt = self.material.elastic_modulus_rt_mpa
        T_ref = 23.0
        
        if temperature_c <= self.material.glass_transition_temp_c:
            return E_rt * 1.1
        elif temperature_c <= self.material.max_service_temp_c:
            delta_t = temperature_c - T_ref
            reduction = 1.0 - 0.008 * abs(delta_t)
            return E_rt * max(0.4, reduction)
        else:
            delta_t = temperature_c - self.material.max_service_temp_c
            softening_range = self.material.melting_temp_c - self.material.max_service_temp_c
            reduction = math.exp(-0.15 * (delta_t / softening_range))
            return E_rt * 0.4 * reduction
    
    def thermal_expansion_stress_mpa(self, delta_temp_c: float, 
                                     temperature_c: float = 80.0) -> float:
        """
        Thermal expansion stress assuming constrained expansion.
        σ_thermal = E(T) * α * ΔT
        """
        E_temp = self.temperature_dependent_modulus(temperature_c)
        alpha = self.material.cte_1_per_k
        stress = E_temp * alpha * delta_temp_c
        return stress
    
    def temperature_gradient_stress_mpa(self, outer_temp_c: float, 
                                       inner_temp_c: float) -> float:
        """
        Stress due to temperature gradient across wall thickness.
        Simplified cylindrical shell: σ_gradient ≈ (E*α/t) * Δt_gradient * r
        """
        delta_t = outer_temp_c - inner_temp_c
        E_avg = self.temperature_dependent_modulus((outer_temp_c + inner_temp_c) / 2.0)
        alpha = self.material.cte_1_per_k
        t = self.design.wall_thickness_mm
        r = self.design.diameter_mm / 2.0
        
        if t <= 0:
            return 0.0
        stress = (E_avg * alpha * delta_t * r) / t
        return stress
    
    def heat_transfer_time_to_equilibrium_s(self) -> float:
        """
        Approximate time for thermal equilibration through wall.
        τ ≈ ρ*c*t² / (4*k)
        where t is wall thickness
        """
        rho = self.material.density_kg_m3 / 1000.0  # Convert to g/mm³
        c = self.material.specific_heat_j_kg_k / 1000.0  # J/g·K
        t = self.material.thermal_conductivity_w_mk  # W/m·K
        thickness_m = self.design.wall_thickness_mm / 1000.0
        
        tau = (rho * c * thickness_m**2) / (4.0 * t)
        return tau


# ============================================================
# 5) SPRING BACK ANALYSIS (Viscoelastic Recovery)
# ============================================================
class SpringBackAnalysis:
    def __init__(self, design: AccordionBottleDesign, material: MaterialPPCOPO):
        self.design = design
        self.material = material
    
    def elastic_recovery_percent(self, strain_percent: float, 
                                hold_time_minutes: float = 1.0,
                                temperature_c: float = 23.0) -> float:
        """
        Estimate elastic recovery (spring back) after compression.
        Model: Recovery = Elastic_Strain * (1 - exp(-t/τ)) * f(T)
        where τ is relaxation time and f(T) is temperature factor
        """
        # Assume ~60% of strain is elastic for PP
        elastic_strain = strain_percent * 0.60
        
        # Relaxation time increases with lower temperature
        base_tau_min = 10.0  # minutes at room temperature
        temp_factor = (23.0 - temperature_c + 25.0) / 48.0
        tau_minutes = base_tau_min * (1.0 + temp_factor)
        
        # Recovery after hold time
        hold_time_minutes_clamped = max(hold_time_minutes, 0.1)
        recovery_fraction = 1.0 - math.exp(-hold_time_minutes_clamped / tau_minutes)
        
        # Total recovery
        recovery_percent = elastic_strain * recovery_fraction
        return min(recovery_percent, elastic_strain)
    
    def permanent_deformation_percent(self, strain_percent: float,
                                      hold_time_minutes: float = 60.0,
                                      temperature_c: float = 80.0) -> float:
        """
        Estimate permanent deformation (plastic creep).
        Plastic_Deformation = Total_Strain - Elastic_Recovery - Recoverable_Creep
        """
        # For PP: ~40% is plastic/viscous at significant strain
        plastic_strain = strain_percent * 0.40
        
        # Additional creep over time (viscous effect)
        creep_rate_per_hour = 0.08  # Per hour at high temp
        additional_creep = (hold_time_minutes / 60.0) * creep_rate_per_hour * strain_percent
        
        # Temperature effect: higher temp = more creep
        temp_multiplier = math.exp((temperature_c - 23.0) / 40.0)
        additional_creep *= temp_multiplier
        
        total_permanent = plastic_strain + additional_creep
        return min(total_permanent, strain_percent * 0.8)  # Cap at 80%
    
    def shape_recovery_after_release(self, compressed_height_mm: float,
                                     expanded_height_mm: float,
                                     hold_time_minutes: float = 10.0,
                                     release_time_seconds: float = 5.0,
                                     temperature_c: float = 23.0) -> Dict[str, float]:
        """
        Comprehensive spring back analysis.
        Returns: Initial recovery, time-based recovery, permanent set
        """
        total_compression_ratio = compressed_height_mm / expanded_height_mm
        strain_percent = (1.0 - total_compression_ratio) * 100.0
        
        # Immediate elastic recovery (upon release)
        immediate_recovery = self.elastic_recovery_percent(strain_percent, 0.01, temperature_c)
        
        # Recovery over time (e.g., 10 minutes rest)
        recovery_after_hold = self.elastic_recovery_percent(strain_percent, hold_time_minutes, temperature_c)
        
        # Permanent deformation
        permanent_deform = self.permanent_deformation_percent(strain_percent, hold_time_minutes, temperature_c)
        
        # Final height estimation
        recovered_percent = immediate_recovery + (recovery_after_hold - immediate_recovery) * 0.7
        final_height = expanded_height_mm * (1.0 - (strain_percent - recovered_percent - permanent_deform) / 100.0)
        
        return {
            "total_compression_strain_percent": strain_percent,
            "immediate_elastic_recovery_percent": immediate_recovery,
            "recovery_after_hold_percent": recovery_after_hold,
            "permanent_deformation_percent": permanent_deform,
            "estimated_final_height_mm": final_height,
            "shape_fidelity_percent": 100.0 - permanent_deform
        }


# ============================================================
# 6) BUCKLING ANALYSIS
# ============================================================
class BucklingAnalysis:
    def __init__(self, design: AccordionBottleDesign, material: MaterialPPCOPO):
        self.design = design
        self.material = material
    
    def euler_critical_load_n(self, effective_length_mm: float) -> float:
        """
        Euler buckling load for cylindrical column.
        P_cr = (π² * E * I) / L_eff²
        """
        E = self.material.elastic_modulus_rt_mpa
        r = self.design.diameter_mm / 2.0
        t = self.design.wall_thickness_mm
        
        # Second moment of inertia (thin cylindrical shell)
        I = (math.pi * r**3 * t) / 4.0
        
        L_eff = effective_length_mm
        if L_eff <= 0:
            return 0.0
        
        P_cr = (math.pi**2 * E * I) / (L_eff**2)
        return P_cr  # in N·mm, convert to N if needed
    
    def elastic_stability_check(self) -> Dict[str, float]:
        """
        Check elastic stability for the compressed accordion.
        Compares axial load to critical buckling load.
        """
        # Weight of liquid in compressed state (approximate)
        liquid_volume_mm3 = self.design.target_volume_ml * 1000.0
        liquid_mass_kg = 0.25  # 250 mL of water
        axial_load_n = liquid_mass_kg * 9.81
        
        # Effective length = compressed height
        L_eff = self.design.compressed_height_mm
        
        # Critical load
        P_cr = self.euler_critical_load_n(L_eff)
        
        # Safety against buckling
        if P_cr <= 0:
            safety_factor = 0.0
        else:
            safety_factor = P_cr / max(axial_load_n, 0.1)
        
        return {
            "axial_load_n": axial_load_n,
            "critical_buckling_load_n": P_cr,
            "safety_factor_buckling": safety_factor,
            "is_stable": safety_factor > 1.5
        }
    
    def geometric_instability_via_fold_collapse(self) -> float:
        """
        Simplified analysis of fold collapse/local buckling.
        Estimates maximum pressure before fold collapse.
        P_collapse ≈ (4*E*t) / (D * amplitude_ratio)
        """
        E = self.material.elastic_modulus_rt_mpa
        t = self.design.wall_thickness_mm
        D = self.design.diameter_mm
        amplitude_ratio = self.design.amplitude_mm / (D / 2.0)
        
        if amplitude_ratio <= 0:
            return 0.0
        
        P_collapse = (4.0 * E * t) / (D * amplitude_ratio)
        return P_collapse


# ============================================================
# 7) LATERAL FORCES & IMPACT ANALYSIS
# ============================================================
class LateralForcesAnalysis:
    def __init__(self, design: AccordionBottleDesign, material: MaterialPPCOPO):
        self.design = design
        self.material = material
    
    def lateral_deflection_mm(self, lateral_force_n: float) -> float:
        """
        Estimate lateral deflection under side force (cantilever beam approximation).
        δ = (F * L³) / (3 * E * I)
        """
        F = lateral_force_n
        L = self.design.height_mm
        E = self.material.elastic_modulus_rt_mpa
        r = self.design.diameter_mm / 2.0
        t = self.design.wall_thickness_mm
        I = (math.pi * r**3 * t) / 4.0
        
        if E <= 0 or I <= 0:
            return 0.0
        
        deflection = (F * L**3) / (3.0 * E * I)
        return deflection
    
    def impact_stress_mpa(self, impact_velocity_m_s: float, 
                         impact_time_ms: float = 10.0) -> float:
        """
        Impact stress from collision/drop.
        σ_impact ≈ ρ * v² (simplified)
        """
        rho = self.material.density_kg_m3 / 1e6  # Convert to kg/mm³
        v = impact_velocity_m_s * 1000 / 1000  # m/s to mm/s
        
        # Simplified: impact stress ≈ E * v / c (wave speed)
        E = self.material.elastic_modulus_rt_mpa
        c_wave = math.sqrt(E * 1e6 / rho) if rho > 0 else 1000  # Wave speed
        
        stress = (E * v / c_wave) * 1e-6  # Normalize
        return max(0.0, stress)
    
    def acceleration_stress_mpa(self, acceleration_g: float) -> float:
        """
        Stress due to acceleration/vibration.
        σ_accel = ρ * g_accel * L * (D/2)
        """
        g_accel = acceleration_g * 9.81
        rho = self.material.density_kg_m3
        L = self.design.height_mm / 1000.0
        D = self.design.diameter_mm / 1000.0
        
        stress_pa = rho * g_accel * L * (D / 2.0)
        stress_mpa = stress_pa / 1e6
        return stress_mpa


# ============================================================
# 8) HAND PRESSURE & FATIGUE ANALYSIS
# ============================================================
class HandPressureAnalysis:
    def __init__(self, design: AccordionBottleDesign, material: MaterialPPCOPO):
        self.design = design
        self.material = material
    
    def localized_pressure_stress_mpa(self, hand_force_n: float,
                                     contact_area_mm2: float = 500.0) -> float:
        """
        Localized stress under hand pressure/grip.
        σ_local = F / A * concentration_factor
        """
        if contact_area_mm2 <= 0:
            return 0.0
        
        base_stress = (hand_force_n * 1000) / contact_area_mm2  # Convert N to cN
        # Concentration factor for localized loading
        Kt = 1.5  # Typical for distributed hand pressure
        
        return base_stress * Kt
    
    def fatigue_cycles_to_failure(self, cyclic_stress_mpa: float,
                                  stress_ratio_r: float = 0.0) -> int:
        """
        Estimate cycles to failure under cyclic loading (hand squeezing).
        Use S-N curve for PP: log(N) ≈ A - B*log(S)
        """
        # Typical S-N parameters for PP
        # Fatigue strength at 10^7 cycles ≈ 8 MPa
        S_fatigue_ref = self.material.fatigue_strength_mpa
        N_ref = 1e7
        
        # S-N equation: log(N) = a + b*log(S)
        # Slope b ≈ -0.15 to -0.20 for thermoplastics
        b = -0.18
        a = math.log10(N_ref) + b * math.log10(S_fatigue_ref)
        
        if cyclic_stress_mpa <= 0:
            return int(1e9)
        
        log_N = a + b * math.log10(cyclic_stress_mpa)
        N = 10**log_N
        return int(max(1, N))
    
    def squeeze_cycle_analysis(self, squeeze_force_n: float = 20.0,
                              cycles_per_use: int = 10,
                              uses_per_day: int = 3,
                              days_of_use: int = 365) -> Dict[str, Any]:
        """
        Comprehensive analysis of hand pressure fatigue over product lifetime.
        """
        contact_area_mm2 = 400.0  # Typical grip area
        cyclic_stress = self.localized_pressure_stress_mpa(squeeze_force_n, contact_area_mm2)
        
        cycles_to_fail = self.fatigue_cycles_to_failure(cyclic_stress)
        
        total_cycles = cycles_per_use * uses_per_day * days_of_use
        
        safety_factor = cycles_to_fail / max(total_cycles, 1)
        
        return {
            "squeeze_force_n": squeeze_force_n,
            "contact_area_mm2": contact_area_mm2,
            "cyclic_stress_mpa": cyclic_stress,
            "cycles_per_use": cycles_per_use,
            "uses_per_day": uses_per_day,
            "days_of_use": days_of_use,
            "total_cycles_lifetime": total_cycles,
            "cycles_to_fatigue_failure": cycles_to_fail,
            "safety_factor_fatigue": safety_factor,
            "is_safe": safety_factor > 2.0,
            "lifetime_estimate": "Safe" if safety_factor > 2.0 else f"Fail after {cycles_to_fail / (cycles_per_use * uses_per_day):.0f} days"
        }


# ============================================================
# 9) COMPREHENSIVE ANALYSIS REPORT
# ============================================================
def generate_comprehensive_report(design: AccordionBottleDesign,
                                 material: MaterialPPCOPO) -> Dict[str, Any]:
    """
    Generate comprehensive structural, thermal, and fatigue analysis.
    """
    print("=" * 120)
    print("COMPREHENSIVE STRUCTURAL & THERMAL ANALYSIS")
    print(f"Design: Model {design.model_id} | {design.diameter_mm}Ø × {design.height_mm}H mm")
    print(f"Material: {material.name}")
    print("=" * 120)
    print()
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "design": asdict(design),
        "material": asdict(material),
        "analyses": {}
    }
    
    # 1. STRESS ANALYSIS
    print("1. STRESS ANALYSIS")
    print("-" * 120)
    stress_analysis = StressAnalysis(design, material)
    
    # Normal operation: assume 0.05 MPa internal pressure (hot water partial vacuum effect)
    internal_pressure = 0.05
    bending_moment = 0.5  # N·m (hand holding)
    torque = 0.1  # N·m (twisting)
    
    hoop_stress = stress_analysis.hoop_stress_mpa(internal_pressure)
    bending_stress = stress_analysis.bending_stress_mpa(bending_moment)
    torsional_stress = stress_analysis.torsional_stress_mpa(torque)
    combined = stress_analysis.combined_stress_mpa(internal_pressure, bending_moment, torque)
    
    print(f"  Internal Pressure: {internal_pressure} MPa")
    print(f"  Hoop Stress: {hoop_stress:.3f} MPa")
    print(f"  Bending Stress: {bending_stress:.3f} MPa")
    print(f"  Torsional Stress: {torsional_stress:.3f} MPa")
    print(f"  Combined (Von Mises): {combined:.3f} MPa")
    print(f"  Safety Factor: {stress_analysis.safety_factor(combined):.2f}")
    print()
    
    report["analyses"]["stress"] = {
        "hoop_stress_mpa": hoop_stress,
        "bending_stress_mpa": bending_stress,
        "torsional_stress_mpa": torsional_stress,
        "combined_stress_mpa": combined,
        "safety_factor": stress_analysis.safety_factor(combined),
        "stress_concentration_factor": stress_analysis.stress_concentration_factor(1.0)
    }
    
    # 2. THERMAL ANALYSIS
    print("2. THERMAL ANALYSIS (80°C Hot Water)")
    print("-" * 120)
    thermal_analysis = ThermalAnalysis(design, material)
    
    delta_temp = 80.0 - 23.0  # Room temp to hot water
    thermal_stress_80c = thermal_analysis.thermal_expansion_stress_mpa(delta_temp, 80.0)
    modulus_80c = thermal_analysis.temperature_dependent_modulus(80.0)
    gradient_stress = thermal_analysis.temperature_gradient_stress_mpa(80.0, 40.0)
    equilibration_time = thermal_analysis.heat_transfer_time_to_equilibrium_s()
    
    print(f"  Temperature Rise: {delta_temp}°C")
    print(f"  Elastic Modulus @ 80°C: {modulus_80c:.0f} MPa (vs {material.elastic_modulus_rt_mpa} at RT)")
    print(f"  Thermal Expansion Stress: {thermal_stress_80c:.3f} MPa")
    print(f"  Gradient Stress (80°C outer, 40°C inner): {gradient_stress:.3f} MPa")
    print(f"  Thermal Equilibration Time: {equilibration_time:.1f} seconds")
    print(f"  Combined Thermal + Mechanical Stress: {combined + thermal_stress_80c:.3f} MPa")
    print()
    
    report["analyses"]["thermal"] = {
        "operating_temperature_c": 80.0,
        "temperature_rise_c": delta_temp,
        "elastic_modulus_at_temp_mpa": modulus_80c,
        "thermal_expansion_stress_mpa": thermal_stress_80c,
        "gradient_stress_mpa": gradient_stress,
        "equilibration_time_s": equilibration_time,
        "combined_stress_mpa": combined + thermal_stress_80c
    }
    
    # 3. SPRING BACK ANALYSIS
    print("3. SPRING BACK ANALYSIS (Compression to 22 mm)")
    print("-" * 120)
    springback = SpringBackAnalysis(design, material)
    
    recovery_data = springback.shape_recovery_after_release(
        compressed_height_mm=design.compressed_height_mm,
        expanded_height_mm=design.height_mm,
        hold_time_minutes=10.0,
        temperature_c=23.0
    )
    
    for key, val in recovery_data.items():
        if isinstance(val, float):
            print(f"  {key}: {val:.2f}")
        else:
            print(f"  {key}: {val}")
    print()
    
    report["analyses"]["springback"] = recovery_data
    
    # 4. BUCKLING ANALYSIS
    print("4. BUCKLING ANALYSIS (Compressed State)")
    print("-" * 120)
    buckling = BucklingAnalysis(design, material)
    
    stability = buckling.elastic_stability_check()
    collapse_pressure = buckling.geometric_instability_via_fold_collapse()
    
    print(f"  Axial Load (liquid + bottle weight): {stability['axial_load_n']:.2f} N")
    print(f"  Critical Buckling Load: {stability['critical_buckling_load_n']:.2f} N")
    print(f"  Safety Factor (Buckling): {stability['safety_factor_buckling']:.2f}")
    print(f"  Elastic Stability: {'✓ STABLE' if stability['is_stable'] else '✗ UNSTABLE'}")
    print(f"  Fold Collapse Pressure: {collapse_pressure:.4f} MPa")
    print()
    
    report["analyses"]["buckling"] = stability
    report["analyses"]["buckling"]["fold_collapse_pressure_mpa"] = collapse_pressure
    
    # 5. LATERAL FORCES ANALYSIS
    print("5. LATERAL FORCES & IMPACT ANALYSIS")
    print("-" * 120)
    lateral = LateralForcesAnalysis(design, material)
    
    lateral_force = 10.0  # 10 N side force (drop impact)
    lateral_defl = lateral.lateral_deflection_mm(lateral_force)
    impact_stress = lateral.impact_stress_mpa(2.0)  # 2 m/s impact
    accel_stress = lateral.acceleration_stress_mpa(2.0)  # 2g acceleration
    
    print(f"  Lateral Force (side impact): {lateral_force} N")
    print(f"  Lateral Deflection: {lateral_defl:.3f} mm")
    print(f"  Impact Stress (2 m/s): {impact_stress:.3f} MPa")
    print(f"  Acceleration Stress (2g): {accel_stress:.3f} MPa")
    print()
    
    report["analyses"]["lateral_impact"] = {
        "lateral_force_n": lateral_force,
        "lateral_deflection_mm": lateral_defl,
        "impact_stress_mpa": impact_stress,
        "acceleration_stress_mpa": accel_stress
    }
    
    # 6. HAND PRESSURE & FATIGUE
    print("6. HAND PRESSURE & FATIGUE ANALYSIS")
    print("-" * 120)
    hand_pressure = HandPressureAnalysis(design, material)
    
    squeeze_analysis = hand_pressure.squeeze_cycle_analysis(
        squeeze_force_n=20.0,
        cycles_per_use=10,
        uses_per_day=3,
        days_of_use=365
    )
    
    for key, val in squeeze_analysis.items():
        print(f"  {key}: {val}")
    print()
    
    report["analyses"]["hand_pressure_fatigue"] = squeeze_analysis
    
    # OVERALL SAFETY SUMMARY
    print("=" * 120)
    print("OVERALL SAFETY SUMMARY")
    print("=" * 120)
    
    all_stresses = [
        combined,
        thermal_stress_80c,
        gradient_stress,
        impact_stress,
        accel_stress
    ]
    max_stress = max(all_stresses)
    overall_sf = stress_analysis.safety_factor(max_stress)
    
    print(f"  Maximum Combined Stress: {max_stress:.3f} MPa")
    print(f"  Overall Safety Factor: {overall_sf:.2f}")
    print(f"  Thermal Safety @ 80°C: {'✓ PASS' if overall_sf > 2.0 else '✗ FAIL'}")
    print(f"  Buckling Safety: {'✓ PASS' if stability['safety_factor_buckling'] > 1.5 else '✗ FAIL'}")
    print(f"  Fatigue Safety (Hand Squeeze): {'✓ PASS' if squeeze_analysis['is_safe'] else '✗ FAIL'}")
    print(f"  Spring Back Recovery: {recovery_data['shape_fidelity_percent']:.1f}%")
    print()
    
    report["summary"] = {
        "max_combined_stress_mpa": max_stress,
        "overall_safety_factor": overall_sf,
        "thermal_safe_at_80c": overall_sf > 2.0,
        "buckling_safe": stability["safety_factor_buckling"] > 1.5,
        "fatigue_safe": squeeze_analysis["is_safe"],
        "shape_recovery_percent": recovery_data["shape_fidelity_percent"]
    }
    
    return report


# ============================================================
# 10) MAIN EXECUTION
# ============================================================
def main() -> None:
    # Generate comprehensive analysis
    report = generate_comprehensive_report(DESIGN_A, MATERIAL)
    
    # Save report to JSON
    output_dir = Path(__file__).resolve().parent / "structural_thermal_analysis"
    output_dir.mkdir(exist_ok=True)
    
    report_path = output_dir / "comprehensive_analysis_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Detailed report saved: {report_path}")
    print()


if __name__ == "__main__":
    main()
