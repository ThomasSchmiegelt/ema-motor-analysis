//
// Runs INSIDE the Docker sandbox only. Loads a compiled skill assembly
// (built from LLM-generated code, already static-analysis-checked by the
// host before it ever got here), invokes its fixed-signature Generate()
// method, and validates + exports the result. Never trusts the skill code
// beyond calling the one contracted entry point - no shell-out, no network,
// no file access beyond the paths explicitly passed in.
//
// Uses Library.GlobalInstance directly (not Library.Go()) since this is a
// one-shot batch run, not an interactive session - Go() blocks in a
// viewer-poll loop meant for interactive apps.
//

using System.Numerics;
using System.Reflection;
using System.Text.Json;
using PicoGK;

if (args.Length != 3)
{
    Console.Error.WriteLine("Usage: Harness <skillDllPath> <paramsJsonPath> <outputStlPath>");
    Environment.Exit(2);
    return;
}

string skillDllPath = args[0];
string paramsJsonPath = args[1];
string outputStlPath = args[2];

try
{
    Dictionary<string, float> parameters = JsonSerializer.Deserialize<Dictionary<string, float>>(
        File.ReadAllText(paramsJsonPath))
        ?? throw new Exception("Parameter-Datei ist leer/ungueltig.");

    Assembly asm = Assembly.LoadFrom(skillDllPath);
    Type type = asm.GetType("GeneratedSkill.SkillGenerator")
        ?? throw new Exception("Typ 'GeneratedSkill.SkillGenerator' nicht gefunden - falsche Code-Struktur.");
    MethodInfo method = type.GetMethod("Generate", BindingFlags.Public | BindingFlags.Static)
        ?? throw new Exception("Statische Methode 'Generate(Library, Dictionary<string,float>)' nicht gefunden.");

    using Library.GlobalInstance instance = new(0.25f, Path.Combine(Path.GetTempPath(), "harness_picogk.log"));
    Library lib = instance.oLibrary;

    object? result = method.Invoke(null, new object[] { lib, parameters });

    if (result is not Voxels vox)
        throw new Exception("Generate() lieferte kein Voxels-Objekt zurueck.");

    Mesh msh = vox.mshAsMesh();
    int triCount = msh.nTriangleCount();

    if (triCount == 0)
        throw new Exception("Ergebnis ist leer (0 Dreiecke) - ungueltige Geometrie.");

    BBox3 bbox = msh.oBoundingBox();
    Vector3 size = bbox.vecSize();

    if (size.X <= 0.001f || size.Y <= 0.001f || size.Z <= 0.001f)
        throw new Exception($"Ergebnis-Geometrie ist entartet (BBox: {size.X}x{size.Y}x{size.Z}mm).");

    msh.SaveToStlFile(outputStlPath);

    Console.WriteLine(JsonSerializer.Serialize(new
    {
        ok = true,
        triangleCount = triCount,
        boundingBoxMM = new { x = size.X, y = size.Y, z = size.Z },
    }));
    Environment.Exit(0);
}
catch (Exception ex)
{
    Console.WriteLine(JsonSerializer.Serialize(new { ok = false, error = ex.ToString() }));
    Environment.Exit(1);
}
