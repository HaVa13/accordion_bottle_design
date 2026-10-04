# accordion_step_and_excel_generator.py
# Generate STEP 3D files + Excel workbook with complete stress/thermal/fatigue analysis
# No external dependencies - pure Python with built-in modules

import math
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any


# ============================================================
# 1) Design Models (A, B, C)
# ============================================================
class AccordionDesign:
    def __init__(self, model_id: str, diameter_mm: float, height_mm: float,
                 folds: int, amplitude_mm: float, wall_thickness_mm: float,
                 compressed_height_mm: float, top_cap_diameter_mm: float,
                 target_volume_ml: float, description: str):
        self.model_id = model_id
        self.diameter_mm = diameter_mm
        self.height_mm = height_mm
        self.folds = folds
        self.amplitude_mm = amplitude_mm
        self.wall_thickness_mm = wall_thickness_mm
        self.compressed_height_mm = compressed_height_mm
        self.top_cap_diameter_mm = top_cap_diameter_mm
        self.target_volume_ml = target_volume_ml
        self.description = description


# Define three models
MODEL_A = AccordionDesign(
    model_id="A",
    diameter_mm=70.0,
    height_mm=125.0,
    folds=11,
    amplitude_mm=8.0,
    wall_thickness_mm=2.2,
    compressed_height_mm=22.0,
    top_cap_diameter_mm=73.0,
    target_volume_ml=300.0,
    description="Compact - Optimized for portability"
)

MODEL_B = AccordionDesign(
    model_id="B",
    diameter_mm=68.0,
    height_mm=118.0,
    folds=12,
    amplitude_mm=7.5,
    wall_thickness_mm=2.3,
    compressed_height_mm=21.0,
    top_cap_diameter_mm=71.0,
    target_volume_ml=285.0,
    description="Balanced - Compromise between capacity and compactness"
)

MODEL_C = AccordionDesign(
    model_id="C",
    diameter_mm=70.0,
    height_mm=132.0,
    folds=13,
    amplitude_mm=8.5,
    wall_thickness_mm=2.4,
    compressed_height_mm=24.0,
    top_cap_diameter_mm=74.0,
    target_volume_ml=320.0,
    description="High Capacity - Maximum liquid holding"
)

MODELS = [MODEL_A, MODEL_B, MODEL_C]


# ============================================================
# 2) Material Properties (PP COPO)
# ============================================================
class MaterialPPCOPO:
    name = "PP COPO / Moplen EP310D HP"
    density_kg_m3 = 900.0
    elastic_modulus_mpa = 1100.0
    poisson_ratio = 0.40
    tensile_strength_mpa = 25.0
    yield_strength_mpa = 20.0
    cte_1_per_k = 11e-5
    thermal_conductivity_w_mk = 0.33
    specific_heat_j_kg_k = 1900.0
    max_service_temp_c = 60.0
    melting_temp_c = 160.0
    glass_transition_temp_c = -10.0
    fatigue_limit_mpa = 8.0


# ============================================================
# 3) Stress & Thermal Calculations
# ============================================================
def bellows_volume_mm3(height_mm: float, diameter_mm: float, folds: int,
                       amplitude_mm: float, samples: int = 1000) -> float:
    """Calculate bellows volume using numerical integration."""
    total_volume = 0.0
    dz = height_mm / samples
    
    for i in range(samples):
        z = (i + 0.5) * dz
        # Sinusoidal radius profile
        radius_base = diameter_mm / 2.0
        wave = math.sin(2.0 * math.pi * folds * z / max(height_mm, 1e-6))
        radius = max(radius_base + amplitude_mm * wave, 2.0)
        area = math.pi * radius**2
        total_volume += area * dz
    
    return total_volume


def thermal_modulus_at_temp(temp_c: float) -> float:
    """Elastic modulus reduction with temperature."""
    E_rt = MaterialPPCOPO.elastic_modulus_mpa
    T_ref = 23.0
    
    if temp_c <= MaterialPPCOPO.glass_transition_temp_c:
        return E_rt * 1.10
    if temp_c <= MaterialPPCOPO.max_service_temp_c:
        reduction = 1.0 - 0.008 * abs(temp_c - T_ref)
        return E_rt * max(0.40, reduction)
    
    delta_t = temp_c - MaterialPPCOPO.max_service_temp_c
    softening_range = MaterialPPCOPO.melting_temp_c - MaterialPPCOPO.max_service_temp_c
    if softening_range > 0:
        reduction = math.exp(-0.15 * (delta_t / softening_range))
    else:
        reduction = 0.0
    return E_rt * 0.40 * reduction


def hoop_stress_mpa(diameter_mm: float, wall_thickness_mm: float, 
                   internal_pressure_mpa: float) -> float:
    """Hoop stress: σ = (P*D)/(2*t)"""
    if wall_thickness_mm <= 0:
        return 0.0
    return (internal_pressure_mpa * diameter_mm) / (2.0 * wall_thickness_mm)


def bending_stress_mpa(diameter_mm: float, wall_thickness_mm: float, 
                      bending_moment_nm: float) -> float:
    """Bending stress in cylindrical shell."""
    r = diameter_mm / 2.0
    I = (math.pi * r**3 * wall_thickness_mm) / 4.0
    if I <= 0:
        return 0.0
    return (bending_moment_nm * 1000.0 * r) / I


def torsional_stress_mpa(diameter_mm: float, wall_thickness_mm: float, 
                        torque_nm: float) -> float:
    """Torsional shear stress."""
    r = diameter_mm / 2.0
    J = (math.pi * r**3 * wall_thickness_mm) / 2.0
    if J <= 0:
        return 0.0
    return (torque_nm * 1000.0 * r) / J


def thermal_expansion_stress_mpa(delta_temp_c: float, elastic_modulus_mpa: float) -> float:
    """Thermal stress from constrained expansion."""
    cte = MaterialPPCOPO.cte_1_per_k
    return elastic_modulus_mpa * cte * delta_temp_c


def lateral_deflection_mm(height_mm: float, diameter_mm: float, wall_thickness_mm: float,
                         elastic_modulus_mpa: float, lateral_force_n: float) -> float:
    """Lateral deflection under side force."""
    L = height_mm
    E = elastic_modulus_mpa
    r = diameter_mm / 2.0
    I = (math.pi * r**3 * wall_thickness_mm) / 4.0
    if I <= 0 or E <= 0:
        return 0.0
    return (lateral_force_n * L**3) / (3.0 * E * I)


def buckling_safety_factor(design: AccordionDesign) -> float:
    """Euler buckling safety factor."""
    r = design.diameter_mm / 2.0
    t = design.wall_thickness_mm
    E = MaterialPPCOPO.elastic_modulus_mpa
    I = (math.pi * r**3 * t) / 4.0
    L_eff = design.compressed_height_mm
    
    if L_eff <= 0:
        return 0.0
    
    P_cr = (math.pi**2 * E * I) / (L_eff**2)
    liquid_load_n = 0.25 * 9.81  # 250 mL water
    
    if liquid_load_n <= 0:
        return float('inf')
    
    return P_cr / liquid_load_n


def spring_back_recovery_percent(design: AccordionDesign) -> float:
    """Estimated shape recovery after compression."""
    total_strain = (1.0 - (design.compressed_height_mm / design.height_mm)) * 100.0
    elastic_recovery = 0.6 * total_strain
    return elastic_recovery


def fatigue_safety_factor(design: AccordionDesign) -> float:
    """Fatigue safety under hand squeeze cycles."""
    cyclic_stress_mpa = 20.0 / 400.0  # 20N hand force, ~400mm² contact
    cycles_to_failure = (MaterialPPCOPO.fatigue_limit_mpa / max(cyclic_stress_mpa, 0.01)) * 1e6
    total_life_cycles = 10 * 3 * 365  # 10 squeezes, 3 times/day, 365 days
    return cycles_to_failure / total_life_cycles


def calculate_all_metrics(design: AccordionDesign, design_temp_c: float = 80.0) -> Dict[str, Any]:
    """Calculate all structural and thermal metrics."""
    
    volume_mm3 = bellows_volume_mm3(design.height_mm, design.diameter_mm, 
                                    design.folds, design.amplitude_mm)
    volume_ml = volume_mm3 / 1000.0
    
    E_hot = thermal_modulus_at_temp(design_temp_c)
    
    # Stresses
    hoop = hoop_stress_mpa(design.diameter_mm, design.wall_thickness_mm, 0.05)
    bend = bending_stress_mpa(design.diameter_mm, design.wall_thickness_mm, 0.5)
    torsional = torsional_stress_mpa(design.diameter_mm, design.wall_thickness_mm, 0.1)
    
    # Von Mises
    vm_stress = math.sqrt(hoop**2 + bend**2 + 3 * torsional**2)
    
    # Thermal
    thermal_stress = thermal_expansion_stress_mpa(design_temp_c - 23.0, E_hot)
    combined_stress = vm_stress + thermal_stress
    
    # Safety factors
    sf_yield = MaterialPPCOPO.yield_strength_mpa / max(combined_stress, 0.001)
    sf_buckling = buckling_safety_factor(design)
    sf_fatigue = fatigue_safety_factor(design)
    
    # Deflection and recovery
    lateral_defl = lateral_deflection_mm(design.height_mm, design.diameter_mm,
                                        design.wall_thickness_mm, 
                                        MaterialPPCOPO.elastic_modulus_mpa, 10.0)
    spring_back = spring_back_recovery_percent(design)
    
    return {
        "volume_ml": volume_ml,
        "volume_mm3": volume_mm3,
        "thermal_modulus_80c_mpa": E_hot,
        "hoop_stress_mpa": hoop,
        "bending_stress_mpa": bend,
        "torsional_stress_mpa": torsional,
        "von_mises_stress_mpa": vm_stress,
        "thermal_expansion_stress_mpa": thermal_stress,
        "combined_stress_mpa": combined_stress,
        "safety_factor_yield": sf_yield,
        "safety_factor_buckling": sf_buckling,
        "safety_factor_fatigue": sf_fatigue,
        "lateral_deflection_mm": lateral_defl,
        "spring_back_recovery_percent": spring_back,
    }


# ============================================================
# 4) STEP File Generator
# ============================================================
def generate_step_file(design: AccordionDesign, output_path: Path) -> None:
    """Generate a simplified STEP file for the accordion bottle."""
    
    # STEP file header and geometry definition (simplified)
    step_content = f"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Accordion Bottle Model {design.model_id}','Parametric 3D Model'),
'2;1');
FILE_NAME('{output_path.name}',{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')},
('Generated by Accordion Calculator'),(''),
'Unknown','','');
FILE_SCHEMA(('AP203_CONFIGURATION_CONTROLLED_3D_DESIGN_OF_MECHANICAL_PARTS_AND_ASSEMBLIES_MCD'));
ENDSEC;
DATA;
#10 = PRODUCT_RELATED_PRODUCT_CATEGORY('part','',#12);
#12 = PRODUCT_CONTEXT('',#14,'mechanical');
#14 = APPLICATION_CONTEXT('mechanical design');
#20 = PRODUCT('Accordion Bottle Model {design.model_id}',
'Accordion Bottle - Model {design.model_id}','',
(#30));
#30 = PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE(
'NONE','',#20,.MADE.);
#40 = PRODUCT_DEFINITION('NONE','',#30,#50);
#50 = PRODUCT_DEFINITION_CONTEXT('',#60,'');
#60 = APPLICATION_CONTEXT('');
#100 = AXIS2_PLACEMENT_3D('Origin',#110,#120,#130);
#110 = CARTESIAN_POINT('',(0.,0.,0.));
#120 = DIRECTION('Direction',#121);
#121 = DIRECTION((0.,0.,1.));
#130 = DIRECTION('Direction',#131);
#131 = DIRECTION((1.,0.,0.));
#200 = CYLINDRICAL_SURFACE(#210,{design.diameter_mm/2.0});
#210 = AXIS2_PLACEMENT_3D('Axis',#211,#212,#213);
#211 = CARTESIAN_POINT('',(0.,0.,0.));
#212 = DIRECTION('Direction',#213);
#213 = DIRECTION((0.,0.,1.));
#300 = PLANE(#310,(0.,0.,1.),0.);
#310 = AXIS2_PLACEMENT_3D('Base',#311,#312,#313);
#311 = CARTESIAN_POINT('',(0.,0.,0.));
#312 = DIRECTION('Direction',#313);
#313 = DIRECTION((0.,0.,-1.));
ENDSEC;
END-ISO-10303-21;
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(step_content)


# ============================================================
# 5) Excel Workbook Generator (using only built-in Python)
# ============================================================
def generate_excel_csv(models: List[AccordionDesign], output_path: Path) -> None:
    """Generate Excel-compatible CSV with all calculations."""
    
    lines = []
    
    # Header
    lines.append("ACCORDION BOTTLE DESIGN - COMPREHENSIVE STRESS & THERMAL ANALYSIS")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Material: {MaterialPPCOPO.name}")
    lines.append("")
    
    # Summary table
    lines.append("=" * 200)
    lines.append("SUMMARY COMPARISON - ALL MODELS")
    lines.append("=" * 200)
    
    headers = [
        "Model ID", "Description", "Diameter (mm)", "Height (mm)", "Folds", 
        "Amplitude (mm)", "Wall (mm)", "Compressed (mm)", "Target Vol (mL)",
        "Volume (mL)", "Hoop Stress (MPa)", "Bending Stress (MPa)",
        "Von Mises (MPa)", "Thermal Stress (MPa)", "Combined (MPa)",
        "SF Yield", "SF Buckling", "SF Fatigue", "Lateral Defl (mm)",
        "Spring Back (%)"
    ]
    
    lines.append(",".join([f'"{h}"' for h in headers]))
    
    for model in models:
        metrics = calculate_all_metrics(model)
        
        row = [
            f'"{model.model_id}"',
            f'"{model.description}"',
            f'{model.diameter_mm}',
            f'{model.height_mm}',
            f'{model.folds}',
            f'{model.amplitude_mm}',
            f'{model.wall_thickness_mm}',
            f'{model.compressed_height_mm}',
            f'{model.target_volume_ml}',
            f'{metrics["volume_ml"]:.2f}',
            f'{metrics["hoop_stress_mpa"]:.4f}',
            f'{metrics["bending_stress_mpa"]:.4f}',
            f'{metrics["von_mises_stress_mpa"]:.4f}',
            f'{metrics["thermal_expansion_stress_mpa"]:.4f}',
            f'{metrics["combined_stress_mpa"]:.4f}',
            f'{metrics["safety_factor_yield"]:.2f}',
            f'{metrics["safety_factor_buckling"]:.2f}',
            f'{metrics["safety_factor_fatigue"]:.2f}',
            f'{metrics["lateral_deflection_mm"]:.4f}',
            f'{metrics["spring_back_recovery_percent"]:.2f}'
        ]
        
        lines.append(",".join(row))
    
    lines.append("")
    lines.append("")
    
    # Detailed analysis for each model
    for model in models:
        metrics = calculate_all_metrics(model)
        
        lines.append("=" * 200)
        lines.append(f"DETAILED ANALYSIS - MODEL {model.model_id}")
        lines.append("=" * 200)
        lines.append("")
        
        # Geometry
        lines.append("GEOMETRIC PARAMETERS")
        lines.append(f'Diameter,{model.diameter_mm}')
        lines.append(f'Height (Expanded),{model.height_mm}')
        lines.append(f'Number of Folds,{model.folds}')
        lines.append(f'Amplitude (Wave Depth),{model.amplitude_mm}')
        lines.append(f'Wall Thickness,{model.wall_thickness_mm}')
        lines.append(f'Compressed Height,{model.compressed_height_mm}')
        lines.append(f'Top Cap Diameter,{model.top_cap_diameter_mm}')
        lines.append(f'Target Volume,{model.target_volume_ml}')
        lines.append(f'Calculated Volume,{metrics["volume_ml"]:.2f}')
        lines.append("")
        
        # Stress Analysis
        lines.append("STRESS ANALYSIS (Operating Pressure: 0.05 MPa, 80°C)")
        lines.append(f'Elastic Modulus @ 80°C,{metrics["thermal_modulus_80c_mpa"]:.2f}')
        lines.append(f'Hoop Stress,{metrics["hoop_stress_mpa"]:.4f}')
        lines.append(f'Bending Stress,{metrics["bending_stress_mpa"]:.4f}')
        lines.append(f'Torsional Stress,{metrics["torsional_stress_mpa"]:.4f}')
        lines.append(f'Von Mises Stress,{metrics["von_mises_stress_mpa"]:.4f}')
        lines.append("")
        
        # Thermal Analysis
        lines.append("THERMAL ANALYSIS")
        lines.append(f'Design Temperature,80°C')
        lines.append(f'Thermal Expansion Stress,{metrics["thermal_expansion_stress_mpa"]:.4f}')
        lines.append(f'Combined Mechanical + Thermal,{metrics["combined_stress_mpa"]:.4f}')
        lines.append("")
        
        # Safety Factors
        lines.append("SAFETY FACTORS")
        lines.append(f'Yield Strength Limit,{MaterialPPCOPO.yield_strength_mpa}')
        lines.append(f'Safety Factor (Yield),{metrics["safety_factor_yield"]:.2f}')
        lines.append(f'Safety Factor (Buckling),{metrics["safety_factor_buckling"]:.2f}')
        lines.append(f'Safety Factor (Fatigue),{metrics["safety_factor_fatigue"]:.2f}')
        lines.append(f'Status,{"✓ PASS" if metrics["safety_factor_yield"] > 2.0 and metrics["safety_factor_buckling"] > 1.5 else "✗ REVIEW"}')
        lines.append("")
        
        # Performance
        lines.append("PERFORMANCE METRICS")
        lines.append(f'Lateral Deflection (10N),{metrics["lateral_deflection_mm"]:.4f}')
        lines.append(f'Spring Back Recovery,{metrics["spring_back_recovery_percent"]:.2f}%')
        lines.append("")
        lines.append("")
    
    # Material properties
    lines.append("=" * 200)
    lines.append("MATERIAL PROPERTIES - PP COPO / Moplen EP310D HP")
    lines.append("=" * 200)
    lines.append(f'Density,{MaterialPPCOPO.density_kg_m3}')
    lines.append(f'Elastic Modulus @ 23°C,{MaterialPPCOPO.elastic_modulus_mpa}')
    lines.append(f'Poisson Ratio,{MaterialPPCOPO.poisson_ratio}')
    lines.append(f'Tensile Strength,{MaterialPPCOPO.tensile_strength_mpa}')
    lines.append(f'Yield Strength,{MaterialPPCOPO.yield_strength_mpa}')
    lines.append(f'Thermal Expansion Coefficient,{MaterialPPCOPO.cte_1_per_k}')
    lines.append(f'Fatigue Limit,{MaterialPPCOPO.fatigue_limit_mpa}')
    lines.append(f'Max Service Temperature,{MaterialPPCOPO.max_service_temp_c}°C')
    
    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


# ============================================================
# 6) Main Execution
# ============================================================
def main() -> None:
    print("=" * 120)
    print("ACCORDION BOTTLE - STEP + EXCEL GENERATOR")
    print("=" * 120)
    print()
    
    # Create output directory
    output_dir = Path(__file__).resolve().parent / "accordion_output"
    output_dir.mkdir(exist_ok=True)
    
    step_dir = output_dir / "step_models"
    step_dir.mkdir(exist_ok=True)
    
    print(f"Output directory: {output_dir}")
    print()
    
    # Generate STEP files
    print("Generating STEP 3D files...")
    for model in MODELS:
        step_path = step_dir / f"accordion_model_{model.model_id.lower()}.step"
        generate_step_file(model, step_path)
        print(f"  ✓ {step_path.name}")
    
    print()
    
    # Generate Excel CSV
    print("Generating Excel analysis workbook...")
    excel_path = output_dir / "accordion_bottle_analysis.csv"
    generate_excel_csv(MODELS, excel_path)
    print(f"  ✓ {excel_path.name}")
    
    print()
    print("=" * 120)
    print("GENERATION COMPLETE")
    print("=" * 120)
    print()
    print(f"STEP files saved to:    {step_dir}/")
    print(f"Excel workbook saved to: {excel_path}")
    print()
    print("Next steps:")
    print("  1. Open accordion_bottle_analysis.csv in Excel/LibreOffice Calc")
    print("  2. Import STEP files into SolidWorks/CAD for further refinement")
    print("  3. Run FEA simulation with the calculated loads and boundary conditions")
    print()


if __name__ == "__main__":
    main()
