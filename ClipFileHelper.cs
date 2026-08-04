// 剪贴板写入助手（WinExe，无控制台窗口）
// 用途：用 .NET 把文件/图片写入剪贴板（微信 4.0 只认 .NET/OLE 写入的剪贴板）
// 替代旧的 `powershell -WindowStyle Hidden` 方案：
//   1. WinExe 无控制台 → 不会触发 conhost 隐藏其他窗口的竞态
//   2. 直接进程调用 → 比启动 PowerShell 快约 2 秒
// 编译：csc /nologo /target:winexe /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.dll /out:clipfile.exe ClipFileHelper.cs
// 用法：clipfile.exe <路径> [image]
// 退出码：0=成功 1=剪贴板占用 2=参数错误 3=文件不存在 4=图片加载失败
using System;
using System.Collections.Specialized;
using System.Threading;
using System.Windows.Forms;

static class ClipFileHelper
{
    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length < 1) return 2;
        string path = args[0];
        bool asImage = args.Length >= 2 && args[1] == "image";
        if (!System.IO.File.Exists(path)) return 3;

        for (int i = 0; i < 20; i++)
        {
            try
            {
                if (asImage)
                {
                    using (var img = System.Drawing.Image.FromFile(path))
                    {
                        Clipboard.SetImage(img);
                    }
                }
                else
                {
                    StringCollection files = new StringCollection();
                    files.Add(path);
                    Clipboard.SetFileDropList(files);
                }
                return 0;
            }
            catch (System.IO.FileNotFoundException)
            {
                return 3;
            }
            catch (Exception)
            {
                // 图片格式错误等不可恢复异常
                if (asImage && i > 0) return 4;
                Thread.Sleep(100);
            }
        }
        return 1;
    }
}
