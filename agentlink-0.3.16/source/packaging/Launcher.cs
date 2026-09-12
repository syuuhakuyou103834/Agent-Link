using System;
using System.IO;
using System.Diagnostics;
using System.Windows.Forms;
using System.Reflection;
[assembly: AssemblyTitle("AgentLink GUI")]
[assembly: AssemblyVersion("0.3.16.0")]
internal static class Launcher {
    [STAThread] static void Main(string[] args) {
        try {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            var info = new ProcessStartInfo(Path.Combine(root, "runtime", "pythonw.exe"));
            info.Arguments = "\"" + Path.Combine(root, "main.py") + "\"";
            // The installer passes only a validated first-run role.
            if (args.Length == 2 && args[0] == "--role" && (args[1] == "A" || args[1] == "B"))
                info.Arguments += " --role " + args[1];
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            using (Process process = Process.Start(info)) { process.WaitForExit(); }
        } catch (Exception error) {
            MessageBox.Show(error.Message, "AgentLink 启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
