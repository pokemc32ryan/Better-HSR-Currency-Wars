using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace HsrCurrencyWarsCleanWpf.Services;

/// <summary>
/// macOS 平台下的鼠标控制服务，通过 Karabiner Virtual HID 发送真实硬件级鼠标事件。
/// 参考 pokemc32ryan/ZenlessZoneZero-OneDragon-mac 的实现。
/// </summary>
public sealed class MacVirtualHidClickService : IClickService, IDisposable
{
	[StructLayout(LayoutKind.Sequential)]
	private struct CGPoint
	{
		public double X;
		public double Y;

		public CGPoint(double x, double y)
		{
			X = x;
			Y = y;
		}
	}

	private const string CoreGraphicsLib = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics";

	[DllImport(CoreGraphicsLib, EntryPoint = "CGWarpMousePosition")]
	private static extern void CGWarpMousePosition(CGPoint newCursorPosition);

	[DllImport(CoreGraphicsLib, EntryPoint = "CGEventCreateKeyboardEvent")]
	private static extern nint CGEventCreateKeyboardEvent(nint source, ushort virtualKey, bool keyDown);

	[DllImport(CoreGraphicsLib, EntryPoint = "CGEventPost")]
	private static extern void CGEventPost(uint tap, nint evt);

	[DllImport("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation", EntryPoint = "CFRelease")]
	private static extern void CFRelease(nint cf);

	private const uint CGHIDEventTap = 0u;

	// macOS 虚拟键码
	private const ushort MacVkEscape = 53;
	private const ushort MacVkV = 9;
	private const ushort MacVkReturn = 36;
	private const ushort MacVkOption = 58;

	private readonly SemaphoreSlim _lock = new SemaphoreSlim(1, 1);
	private Process? _vhidProcess;
	private readonly string _clientPath;

	public MacVirtualHidClickService(string? clientPath = null)
	{
		if (string.IsNullOrWhiteSpace(clientPath))
		{
			string baseDir = AppContext.BaseDirectory;
			_clientPath = Path.Combine(baseDir, ".install", "macos-vhid", "vhid-click-client");
			if (!File.Exists(_clientPath))
			{
				// 尝试项目根目录下的路径
				string projectClient = Path.GetFullPath(Path.Combine(baseDir, "..", "..", "..", ".install", "macos-vhid", "vhid-click-client"));
				if (File.Exists(projectClient))
				{
					_clientPath = projectClient;
				}
			}
		}
		else
		{
			_clientPath = clientPath;
		}
	}

	public async Task<ClickResult> ClickAsync(ClickRequest request, nint windowHandle, CancellationToken cancellationToken = default(CancellationToken))
	{
		cancellationToken.ThrowIfCancellationRequested();
		await EnsureClientStartedAsync(cancellationToken);

		// 1. 移动系统鼠标指针
		MoveCursor(request.ScreenX, request.ScreenY);
		await Task.Delay(50, cancellationToken);

		// 2. 发送微小微移 (+1,0)/(-1,0) 触发 PlayCover 同步游标位置
		await NudgeCursorAsync(cancellationToken);
		await Task.Delay(50, cancellationToken);

		// 3. 通过 Karabiner 虚拟 HID 发送左键点击
		await SendCommandAsync("click 1 100", cancellationToken);

		return new ClickResult(Performed: true, $"Karabiner 虚拟 HID 点击：{request.Reason} @ {request.ScreenX},{request.ScreenY}");
	}

	public async Task<ClickResult> DragAsync(DragRequest request, nint windowHandle, CancellationToken cancellationToken = default(CancellationToken))
	{
		cancellationToken.ThrowIfCancellationRequested();
		await EnsureClientStartedAsync(cancellationToken);

		// 1. 移动至起点并微移同步
		MoveCursor(request.StartScreenX, request.StartScreenY);
		await Task.Delay(80, cancellationToken);
		await NudgeCursorAsync(cancellationToken);
		await Task.Delay(50, cancellationToken);

		// 2. 按下左键
		await SendCommandAsync("press 1 0", cancellationToken);
		await Task.Delay(100, cancellationToken);

		// 3. 分步移动至终点
		const int steps = 12;
		for (int i = 1; i <= steps; i++)
		{
			cancellationToken.ThrowIfCancellationRequested();
			int x = request.StartScreenX + (int)Math.Round((double)((request.EndScreenX - request.StartScreenX) * i) / steps);
			int y = request.StartScreenY + (int)Math.Round((double)((request.EndScreenY - request.StartScreenY) * i) / steps);
			MoveCursor(x, y);
			await Task.Delay(25, cancellationToken);
		}

		await Task.Delay(100, cancellationToken);
		// 4. 释放左键
		await SendCommandAsync("release 1 0", cancellationToken);

		return new ClickResult(Performed: true, $"Karabiner 虚拟 HID 拖拽：{request.Reason} @ {request.StartScreenX},{request.StartScreenY} -> {request.EndScreenX},{request.EndScreenY}");
	}

	public async Task<ClickResult> ScrollAsync(int screenX, int screenY, int wheelDelta, nint windowHandle, CancellationToken cancellationToken = default(CancellationToken))
	{
		cancellationToken.ThrowIfCancellationRequested();
		await EnsureClientStartedAsync(cancellationToken);

		MoveCursor(screenX, screenY);
		await Task.Delay(50, cancellationToken);
		await NudgeCursorAsync(cancellationToken);
		await Task.Delay(50, cancellationToken);

		int verticalWheel = Math.Clamp(wheelDelta / 120, -127, 127);
		await SendCommandAsync($"wheel {verticalWheel} 0", cancellationToken);

		return new ClickResult(Performed: true, $"Karabiner 虚拟 HID 滚轮：{wheelDelta} @ {screenX},{screenY}");
	}

	public async Task<ClickResult> PressKeyAsync(string key, nint windowHandle, CancellationToken cancellationToken = default(CancellationToken))
	{
		cancellationToken.ThrowIfCancellationRequested();
		ushort keyCode;
		string displayName;

		if (string.Equals(key, "esc", StringComparison.OrdinalIgnoreCase) || string.Equals(key, "escape", StringComparison.OrdinalIgnoreCase))
		{
			keyCode = MacVkEscape;
			displayName = "Esc";
		}
		else if (string.Equals(key, "v", StringComparison.OrdinalIgnoreCase))
		{
			keyCode = MacVkV;
			displayName = "V";
		}
		else
		{
			throw new InvalidOperationException("macOS 当前只支持按键 Esc 和 V，不支持：" + key);
		}

		SendMacKeyEvent(keyCode, true);
		await Task.Delay(50, cancellationToken);
		SendMacKeyEvent(keyCode, false);

		return new ClickResult(Performed: true, "macOS 真实按键：" + displayName);
	}

	public async Task<ClickResult> PressAltEnterAsync(nint windowHandle, CancellationToken cancellationToken = default(CancellationToken))
	{
		cancellationToken.ThrowIfCancellationRequested();
		SendMacKeyEvent(MacVkOption, true);
		try
		{
			await Task.Delay(200, cancellationToken);
			SendMacKeyEvent(MacVkReturn, true);
			await Task.Delay(50, cancellationToken);
			SendMacKeyEvent(MacVkReturn, false);
		}
		finally
		{
			SendMacKeyEvent(MacVkOption, false);
		}

		return new ClickResult(Performed: true, "macOS 组合键：Option + Return");
	}

	private static void MoveCursor(int x, int y)
	{
		try
		{
			if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
			{
				CGWarpMousePosition(new CGPoint(x, y));
			}
		}
		catch
		{
		}
	}

	private static void SendMacKeyEvent(ushort keyCode, bool isDown)
	{
		try
		{
			if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
			{
				nint evt = CGEventCreateKeyboardEvent(IntPtr.Zero, keyCode, isDown);
				if (evt != IntPtr.Zero)
				{
					CGEventPost(CGHIDEventTap, evt);
					CFRelease(evt);
				}
			}
		}
		catch
		{
		}
	}

	private async Task NudgeCursorAsync(CancellationToken cancellationToken)
	{
		await SendCommandAsync("move -1 0", cancellationToken);
		await SendCommandAsync("move 1 0", cancellationToken);
	}

	private async Task EnsureClientStartedAsync(CancellationToken cancellationToken)
	{
		if (_vhidProcess != null && !_vhidProcess.HasExited)
		{
			return;
		}

		await _lock.WaitAsync(cancellationToken);
		try
		{
			if (_vhidProcess != null && !_vhidProcess.HasExited)
			{
				return;
			}

			if (!File.Exists(_clientPath))
			{
				throw new FileNotFoundException($"找不到 Karabiner 虚拟 HID 客户端：{_clientPath}。请先执行 Tools/macos/build_vhid_click_client.sh 或运行 启动_mac.command。");
			}

			ProcessStartInfo startInfo = new ProcessStartInfo
			{
				FileName = "/usr/bin/sudo",
				Arguments = $"-n \"{_clientPath}\"",
				UseShellExecute = false,
				RedirectStandardInput = true,
				RedirectStandardOutput = true,
				RedirectStandardError = true,
				CreateNoWindow = true,
				StandardInputEncoding = Encoding.UTF8,
				StandardOutputEncoding = Encoding.UTF8,
			};

			_vhidProcess = Process.Start(startInfo) ?? throw new InvalidOperationException("无法启动 Karabiner 虚拟 HID 客户端进程。");

			using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(10));
			using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, cts.Token);

			string? readyLine = await _vhidProcess.StandardOutput.ReadLineAsync(linkedCts.Token);
			if (readyLine != "READY")
			{
				string err = readyLine ?? "客户端无输出";
				if (err.Contains("password is required", StringComparison.OrdinalIgnoreCase))
				{
					throw new UnauthorizedAccessException("启动 Karabiner 虚拟 HID 客户端需要管理员授权，请先运行 启动_mac.command 并输入一次密码缓存 sudo。");
				}
				throw new InvalidOperationException($"Karabiner 虚拟 HID 客户端启动失败：{err}");
			}
		}
		finally
		{
			_lock.Release();
		}
	}

	private async Task SendCommandAsync(string command, CancellationToken cancellationToken)
	{
		await _lock.WaitAsync(cancellationToken);
		try
		{
			if (_vhidProcess == null || _vhidProcess.HasExited || _vhidProcess.StandardInput == null || _vhidProcess.StandardOutput == null)
			{
				throw new InvalidOperationException("Karabiner 虚拟 HID 客户端未运行。");
			}

			await _vhidProcess.StandardInput.WriteLineAsync(command.AsMemory(), cancellationToken);
			await _vhidProcess.StandardInput.FlushAsync(cancellationToken);

			using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(10));
			using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, cts.Token);

			string? response = await _vhidProcess.StandardOutput.ReadLineAsync(linkedCts.Token);
			if (response != "OK")
			{
				throw new InvalidOperationException($"Karabiner 虚拟 HID 执行失败：{response ?? "无响应"}");
			}
		}
		finally
		{
			_lock.Release();
		}
	}

	public void Dispose()
	{
		try
		{
			if (_vhidProcess != null && !_vhidProcess.HasExited)
			{
				try
				{
					_vhidProcess.StandardInput.WriteLine("quit");
					_vhidProcess.StandardInput.Flush();
				}
				catch
				{
				}

				if (!_vhidProcess.WaitForExit(2000))
				{
					_vhidProcess.Kill();
				}
			}
		}
		catch
		{
		}
		finally
		{
			_vhidProcess?.Dispose();
			_vhidProcess = null;
			_lock.Dispose();
		}
	}
}
