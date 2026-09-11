using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Drawing;
using System.Diagnostics;
using System.Windows.Forms;
using System.ComponentModel;
[assembly: AssemblyTitle("AgentLink GUI Setup")]
[assembly: AssemblyDescription("PyQt5 two-PC collaboration installer")]
[assembly: AssemblyVersion("0.3.14.0")]
internal static class Package {
    const string ExpectedHash = "PAYLOAD_HASH";
    internal static void Extract(string target) {
        target = Path.GetFullPath(target);
        Directory.CreateDirectory(target);
        using (Stream input = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
        using (MemoryStream data = new MemoryStream()) {
            input.CopyTo(data);
            using (SHA256 hash = SHA256.Create()) {
                string actual = BitConverter.ToString(hash.ComputeHash(data.ToArray())).Replace("-", "");
                if (actual != ExpectedHash) throw new InvalidDataException("安装包完整性校验失败。");
            }
            data.Position = 0;
            using (ZipArchive zip = new ZipArchive(data, ZipArchiveMode.Read)) {
                foreach (ZipArchiveEntry entry in zip.Entries) {
                    string file = Path.GetFullPath(Path.Combine(target, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                    if (!file.StartsWith(target.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("安装路径无效。");
                    Directory.CreateDirectory(Path.GetDirectoryName(file));
                    if (String.IsNullOrEmpty(entry.Name)) continue;
                    using (Stream source = entry.Open())
                    using (Stream output = new FileStream(file, FileMode.Create, FileAccess.Write)) source.CopyTo(output);
                }
            }
        }
    }
    internal static void Shortcut(string path, string target, string role) {
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(shellType);
        object link = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { path });
        Type type = link.GetType();
        type.InvokeMember("TargetPath", BindingFlags.SetProperty, null, link, new object[] { target });
        type.InvokeMember("Arguments", BindingFlags.SetProperty, null, link, new object[] { "--role " + role });
        type.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, link, new object[] { Path.GetDirectoryName(target) });
        type.InvokeMember("Description", BindingFlags.SetProperty, null, link, new object[] { "AgentLink PyQt5 双机协作" });
        type.InvokeMember("Save", BindingFlags.InvokeMethod, null, link, null);
        System.Runtime.InteropServices.Marshal.FinalReleaseComObject(link);
        System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);
    }
}
internal sealed class SetupWindow : Form {
    readonly RadioButton roleA = new RadioButton(), roleB = new RadioButton();
    readonly Button install = new Button(), launch = new Button();
    readonly Label status = new Label();
    readonly ProgressBar progress = new ProgressBar();
    string installedPath;
    bool working;
    internal SetupWindow() {
        Text = "AgentLink GUI · 安装";
        Font = new Font("Microsoft YaHei UI", 10F);
        ClientSize = new Size(660, 435); FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(244, 246, 250);
        Controls.Add(new Label { Text = "AgentLink GUI", Font = new Font(Font.FontFamily, 24F, FontStyle.Bold), ForeColor = Color.FromArgb(32, 63, 102), Location = new Point(30, 25), AutoSize = true });
        Controls.Add(new Label { Text = "PyQt5 界面 · 双向控制 · 多轮讨论 · 中文实时输出", Location = new Point(32, 80), AutoSize = true });
        Controls.Add(new Label { Text = "本机节点（两台电脑分别选择不同节点）", Location = new Point(32, 130), AutoSize = true });
        roleA.Text = "A · ZHOUBY"; roleA.SetBounds(35, 163, 240, 30);
        roleB.Text = "B · WILLDESKTOP"; roleB.SetBounds(315, 163, 285, 30);
        roleB.Checked = Environment.MachineName.Equals("WILLDESKTOP", StringComparison.OrdinalIgnoreCase);
        roleA.Checked = !roleB.Checked; Controls.Add(roleA); Controls.Add(roleB);
        Controls.Add(new Label { Text = "已内置 Python 3.13 与 PyQt5，无需另装 Python。\n使用本机已经登录的 Codex；首次启动可调整共享目录和权限。\n程序按当前用户安装，旧版讨论记录保留。", Location = new Point(32, 217), Size = new Size(600, 83) });
        status.Text = "准备安装。"; status.SetBounds(32, 312, 600, 34); Controls.Add(status);
        progress.SetBounds(32, 349, 600, 8); Controls.Add(progress);
        install.Text = "安装到本机"; install.SetBounds(310, 379, 150, 36); install.Click += BeginInstall; Controls.Add(install);
        launch.Text = "打开 AgentLink"; launch.SetBounds(475, 379, 157, 36); launch.Enabled = false;
        launch.Click += delegate { Process.Start(new ProcessStartInfo(installedPath, "--role " + (roleA.Checked ? "A" : "B")) { UseShellExecute = true }); Close(); };
        Controls.Add(launch);
        FormClosing += delegate(object sender, FormClosingEventArgs e) { if (working) e.Cancel = true; };
    }
    void BeginInstall(object sender, EventArgs e) {
        string role = roleA.Checked ? "A" : "B";
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string target = Path.Combine(local, "Programs", "AgentLinkGUI");
        string userData = Path.Combine(local, "AgentLinkGUI");
        install.Enabled = roleA.Enabled = roleB.Enabled = false; working = true;
        status.Text = "正在校验和安装内置运行环境…"; progress.Style = ProgressBarStyle.Marquee;
        BackgroundWorker worker = new BackgroundWorker();
        worker.DoWork += delegate {
            Directory.CreateDirectory(userData);
            using (FileStream guard = new FileStream(Path.Combine(userData, "gui.lease"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None)) {
                Package.Extract(target);
                installedPath = Path.Combine(target, "AgentLink.exe");
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string menu = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "AgentLink GUI");
                Directory.CreateDirectory(menu);
                Package.Shortcut(Path.Combine(desktop, "AgentLink GUI.lnk"), installedPath, role);
                Package.Shortcut(Path.Combine(menu, "AgentLink GUI.lnk"), installedPath, role);
            }
        };
        worker.RunWorkerCompleted += delegate(object s, RunWorkerCompletedEventArgs done) {
            working = false; progress.Style = ProgressBarStyle.Blocks;
            if (done.Error != null) {
                status.Text = "安装未完成。"; install.Enabled = roleA.Enabled = roleB.Enabled = true;
                MessageBox.Show(this, done.Error.Message + "\n\n若程序已打开，请先关闭后重试。", "安装失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
            } else { progress.Value = 100; status.Text = "安装完成，已创建桌面快捷方式。"; launch.Enabled = true; }
        };
        worker.RunWorkerAsync();
    }
}
internal static class Program {
    [STAThread] static int Main(string[] args) {
        try {
            if (args.Length == 2 && args[0] == "--extract") { Package.Extract(args[1]); return 0; }
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            if (args.Length == 2 && args[0] == "--preview") {
                using (SetupWindow preview = new SetupWindow()) {
                    preview.ShowInTaskbar = false; preview.StartPosition = FormStartPosition.Manual;
                    preview.Location = new Point(-32000, -32000); preview.Show(); Application.DoEvents();
                    using (Bitmap bitmap = new Bitmap(preview.Width, preview.Height)) {
                        preview.DrawToBitmap(bitmap, new Rectangle(Point.Empty, preview.Size));
                        bitmap.Save(Path.GetFullPath(args[1]));
                    }
                    preview.Close();
                }
                return 0;
            }
            Application.Run(new SetupWindow()); return 0;
        } catch (Exception error) {
            if (args.Length == 2 && args[0] == "--extract") {
                try { File.WriteAllText(Path.Combine(Path.GetFullPath(args[1]), "extract-error.txt"), error.ToString()); } catch { }
                Console.Error.WriteLine(error); return 1;
            }
            MessageBox.Show(error.Message, "AgentLink 安装失败"); return 1;
        }
    }
}
