# accordion_model_generator.py
# Parametric generator for the accordion bottle family.
# Produces: Excel workbook with one sheet per model and a SolidWorks-compatible STEP export.
# This script is designed to work on a machine with CadQuery installed.

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any

try:
    import cadquery as cq
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "CadQuery is required. Install it with: pip install cadquery openpyxl"
    ) from exc

try:
    import openpyxl
    from openpyxl import Workbook
except Exception as exc:  # pragma: no cover
    raise SystemExit("openpyxl is required. Install it with: pip install openpyxl") from exc


# ----------------------------
# 1) Design variants based on the reference architecture
# ----------------------------
@dataclass
class AccordionModel:
    model_name: str
    diameter_mm: float
    height_mm: float
    folds: int
    amplitude_mm: float
    wall_thickness_mm: float
    top_cap_diameter_mm: float
    top_cap_height_mm: float
    material: str
    target_volume_ml: float
    target_hot_water_ml: float
    compressed_height_mm: float
    note: str = ""


MODEL_LIBRARY: List[AccordionModel] = [
    AccordionModel(
        model_name="Model_A",
        diameter_mm=70.0,
        height_mm=125.0,
        folds=11,
        amplitude_mm=8.0,
        wall_thickness_mm=2.2,
        top_cap_diameter_mm=73.0,
        top_cap_height_mm=10.0,
        material="PP COPO / Moplen EP310D HP",
        target_volume_ml=300.0,
        target_hot_water_ml=250.0,
        compressed_height_mm=22.0,
        note="Most compact architecture aligned to reference drawing"
    ),
    AccordionModel(
        model_name="Model_B",
        diameter_mm=68.0,
        height_mm=118.0,
        folds=12,
        amplitude_mm=7.5,
        wall_thickness_mm=2.3,
        top_cap_diameter_mm=71.0,
        top_cap_height_mm=9.5,
        material="PP COPO / Moplen EP310D HP",
        target_volume_ml=285.0,
        target_hot_water_ml=240.0,
        compressed_height_mm=21.0,
        note="Balanced for easy carry and good esthetics"
    ),
    AccordionModel(
        model_name="Model_C",
        diameter_mm=70.0,
        height_mm=132.0,
        folds=13,
        amplitude_mm=8.5,
        wall_thickness_mm=2.4,
        top_cap_diameter_mm=74.0,
        top_cap_height_mm=12.0,
        material="PP COPO / Moplen EP310D HP",
        target_volume_ml=320.0,
        target_hot_water_ml=260.0,
        compressed_height_mm=24.0,
        note="Higher volume / safer hot-liquid capacity"
    ),
]


def bellows_profile(radius_mm: float, height_mm: float, folds: int, amplitude_mm: float) -> List[float]:
    z_values = [i * (height_mm / (folds * 2)) for i in range(folds * 2 + 1)]
    profile = []
    for z in z_values:
        wave = 1.0 + (amplitude_mm / radius_mm) * math.sin(2.0 * math.pi * folds * z / height_mm)
        profile.append(radius_mm * wave)
    return profile


def build_accordion_body(model: AccordionModel) -> cq.Workplane:
    # A conceptual bellows profile built as a revolved sketch.
    # This is designed to mirror the sample architecture in the reference image.
    radius = model.diameter_mm / 2.0
    profile_points = []
    section_count = 200
    for i in range(section_count + 1):
        z = (i / section_count) * model.height_mm
        wave = math.sin(2.0 * math.pi * model.folds * z / model.height_mm)
        r = radius + model.amplitude_mm * wave
        profile_points.append((r, z))

    # Create a 2D profile for revolve.
    pt_list = []
    for r, z in profile_points:
        pt_list.append((0.0, z))
        pt_list.append((r, z))

    # Simplified body: revolve the radial profile around the axis for a bellows-like form.
    sketch = cq.Workplane("XY")
    for idx, (x, y) in enumerate(pt_list):
        if idx == 0:
            sketch = sketch.moveTo(x, y)
        else:
            sketch = sketch.lineTo(x, y)

    solid = sketch.close().revolve(axisStart=(0, 0, 0), axisEnd=(0, 0, 1), angle=360)
    return solid


# ----------------------------
# 2) Export models to STEP
# ----------------------------
def export_step(model: AccordionModel, output_dir: Path) -> Path:
    # Build a simplified bellows body and export a STEP file.
    body = build_accordion_body(model)
    step_path = output_dir / f"{model.model_name.lower()}_accordion_bottle.step"
    cq.exporters.export(body, str(step_path))
    return step_path


# ----------------------------
# 3) Produce Excel workbook with one sheet per model
# ----------------------------

def model_specs_rows(model: AccordionModel) -> Dict[str, Any]:
    return {
        "Model": model.model_name,
        "Material": model.material,
        "Diameter_mm": model.diameter_mm,
        "Height_mm": model.height_mm,
        "Fold_Count": model.folds,
        "Amplitude_mm": model.amplitude_mm,
        "Wall_Thickness_mm": model.wall_thickness_mm,
        "Top_Cap_Diameter_mm": model.top_cap_diameter_mm,
        "Top_Cap_Height_mm": model.top_cap_height_mm,
        "Target_Volume_mL": model.target_volume_ml,
        "Hot_Water_Capacity_mL": model.target_hot_water_ml,
        "Compressed_Height_mm": model.compressed_height_mm,
        "Note": model.note,
    }


def create_specs_workbook(models: List[AccordionModel], target_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append([
        "Model",
        "Material",
        "Diameter_mm",
        "Height_mm",
        "Fold_Count",
        "Amplitude_mm",
        "Wall_Thickness_mm",
        "Top_Cap_Diameter_mm",
        "Top_Cap_Height_mm",
        "Target_Volume_mL",
        "Hot_Water_Capacity_mL",
        "Compressed_Height_mm",
        "Note",
    ])

    for m in models:
        ws.append(list(model_specs_rows(m).values()))

    for m in models:
        sheet = wb.create_sheet(m.model_name)
        row = [
            "Parameter",
            "Value",
        ]
        sheet.append(row)
        for key, value in model_specs_rows(m).items():
            sheet.append([key, value])

    wb.save(target_path)
    print(f"Excel workbook created: {target_path}")


# ----------------------------
# 4) Main
# ----------------------------
def main() -> None:
    project_dir = Path(__file__).resolve().parent
    export_dir = project_dir / "generated_models"
    export_dir.mkdir(exist_ok=True)

    # export model files
    for model in MODEL_LIBRARY:
        step_path = export_step(model, export_dir)
        print(f"Exported: {step_path}")

    # create summary workbook
    xlsx_path = project_dir / "accordion_models_specs.xlsx"
    create_specs_workbook(MODEL_LIBRARY, xlsx_path)

    # save model metadata
    metadata_path = project_dir / "accordion_models_meta.json"
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump([asdict(m) for m in MODEL_LIBRARY], f, indent=2, ensure_ascii=False)

    print("\nDone.")
    print(f"Metadata: {metadata_path}")
    print(f"Workbook: {xlsx_path}")
    print(f"STEP files: {export_dir}")


if __name__ == "__main__":
    main()

