// Lanceur Windows d'Apex Radio : démarre l'appli (Python portable inclus) sans console.
// Compilé par GitHub Actions avec le compilateur C# de .NET Framework (C# 5, volontairement simple).
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

[assembly: AssemblyTitle("Apex Radio")]
[assembly: AssemblyProduct("Apex Radio")]
[assembly: AssemblyDescription("Voice race engineer for Le Mans Ultimate")]
[assembly: AssemblyCopyright("GPL-3.0")]

static class ApexRadio
{
    [STAThread]
    static int Main(string[] args)
    {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string[] candidates = {
            Path.Combine(dir, "python", "pythonw.exe"),
            Path.Combine(dir, ".venv", "Scripts", "pythonw.exe")
        };
        string py = null;
        foreach (string c in candidates) { if (File.Exists(c)) { py = c; break; } }
        if (py == null || !File.Exists(Path.Combine(dir, "app.py")))
        {
            MessageBox.Show("Apex Radio est incomplet : réinstalle-le.\nApex Radio is incomplete: please reinstall it.\n\n" + dir,
                            "Apex Radio", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        StringBuilder cmd = new StringBuilder("app.py");
        foreach (string a in args) { cmd.Append(" \"").Append(a.Replace("\"", "")).Append("\""); }
        ProcessStartInfo psi = new ProcessStartInfo(py, cmd.ToString());
        psi.WorkingDirectory = dir;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        try { Process.Start(psi); }
        catch (Exception e)
        {
            MessageBox.Show("Impossible de lancer Apex Radio / Cannot start Apex Radio:\n" + e.Message,
                            "Apex Radio", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        return 0;
    }
}
