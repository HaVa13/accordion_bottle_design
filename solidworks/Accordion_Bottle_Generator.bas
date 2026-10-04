' SolidWorks macro for generating a bellows bottle part from the reference architecture.
' This is a blueprint macro that can be run in SolidWorks on a desktop machine with SolidWorks installed.
' It creates a new part and saves it as a .sldprt file.
'
'Instructions:
'  1) Open SolidWorks and create a new macro.
'  2) Paste this code into the macro editor.
'  3) Run the macro.
'  4) It will generate a parametric bellows bottle part.

Option Explicit

Sub main()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As SldWorks.ModelDoc2
    Dim swPart As SldWorks.PartDoc
    Dim swFeat As SldWorks.Feature
    Dim swSketch As SldWorks.Sketch
    Dim swSketchMgr As SldWorks.SketchManager
    Dim swProfile As Object
    Dim i As Integer
    Dim j As Integer
    Dim pi As Double
    Dim height As Double
    Dim diameter As Double
    Dim folds As Integer
    Dim amplitude As Double
    Dim theta As Double
    Dim x As Double
    Dim y As Double
    Dim z As Double
    Dim ringCount As Integer
    Dim ringSize As Integer
    Dim v As Variant
    Dim vPoints As Variant
    Dim bbox As Variant
    Dim filePath As String

    Set swApp = Application.SldWorks
    Set swModel = swApp.NewDocument("C:\ProgramData\SolidWorks\SOLIDWORKS 2024\templates\Part.prtdot", 0, 0, 0)
    Set swPart = swModel
    Set swSketchMgr = swModel.SketchManager

    diameter = 70.0
    height = 125.0
    folds = 11
    amplitude = 8.0
    pi = 3.14159265358979

    ' Create a sketch on the Front Plane
    swModel.Extension.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    swSketchMgr.InsertSketch True

    ' Build a revolved profile for the accordion body using a sinusoidal radius profile.
    ' This approximates the architecture in the reference drawing.
    swSketchMgr.CreateLine 0, 0, 0, 0, height, 0
    ' Approximate bellows profile as a set of radii vs. height
    For i = 0 To 100
        z = (i / 100) * height
        theta = 2 * pi * folds * z / height
        x = (diameter / 2) + amplitude * Sin(theta)
        swSketchMgr.CreateLine x, z, 0, x, z + 0.1, 0
    Next i

    ' Wrap it into a simple revolved feature for concept generation.
    swModel.FeatureManager.FeatureRevolve "Boss-Extrude1", True, False, False, False, False, False, 0, 0, 360, 0, 0, 0, False, False, False, False, 0, 0, False, False

    ' Save as .sldprt file in the current working directory
    filePath = ThisWorkbook.Path & "\accordion_bottle_reference.sldprt"
    swModel.SaveAs filePath
    swModel.Visible = True

    MsgBox "SolidWorks part created: " & filePath, vbInformation
End Sub
