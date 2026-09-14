param([string]$Label = 'baseline')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work = Join-Path $PSScriptRoot $Label
New-Item -ItemType Directory -Path $work | Out-Null
$stub = Join-Path $work 'argv-stub.exe'
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Diagnostics;
using System.Web.Script.Serialization;
public class ArgvOnly {
    public static int Main(string[] args) {
        var record = new { pid = Process.GetCurrentProcess().Id, argv = args, executable = Process.GetCurrentProcess().MainModule.FileName };
        File.AppendAllText(Environment.GetEnvironmentVariable("ARGV_CAPTURE"), new JavaScriptSerializer().Serialize(record) + "\n");
        return 0;
    }
}
'@ -ReferencedAssemblies 'System.Web.Extensions.dll' -OutputAssembly $stub -OutputType ConsoleApplication
$env:PYSTRAY_BACKEND = 'dummy'
$env:BROWSER = 'C:/Windows/System32/cmd.exe /c rem %s'
$env:TEMP = $work
$env:TMP = $work
function Inventory {
    @(Get-Process | Where-Object { $_.ProcessName -like 'STEAMDECK*' -or $_.ProcessName -in @('python','pythonw') } | Sort-Object Id | ForEach-Object {
        [ordered]@{pid=$_.Id; name=$_.ProcessName; path=$_.Path; started=$_.StartTime.ToUniversalTime().ToString('o')}
    })
}
$results = @()
foreach ($name in @('start_receiver.ps1','start_installed_receiver.ps1','start_installed_receiver_v2.ps1')) {
    foreach ($arm in @('missing-key','grandma','absent-file')) {
        $root = Join-Path $work ($name.Replace('.ps1','') + '-' + $arm)
        $config = Join-Path $root 'config'
        New-Item -ItemType Directory -Path $config | Out-Null
        $exeRelative = switch ($name) {
            'start_receiver.ps1' { '.venv\Scripts\python.exe' }
            'start_installed_receiver.ps1' { 'STEAMDECK-MIDI-RECEIVER.exe' }
            'start_installed_receiver_v2.ps1' { 'STEAMDECK-MIDI-RECEIVER-2.exe' }
        }
        $target = Join-Path $root $exeRelative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $stub -Destination $target
        # No receiver or MIDI library is placed in the isolated layout.
        $defaults = Get-Content -LiteralPath (Join-Path $clone 'config\windows_receiver_settings.example.json') -Raw | ConvertFrom-Json
        $defaults.listen = '127.0.0.1:45282'
        $defaults.ui_port = 7782
        $defaults.no_ui = $true
        $defaults.midi_port = 'SDWIN_ARGV_ONLY_NO_MIDI'
        $defaults.feedback_port = ''
        # Check these ports free even though the executable can never bind them.
        if (@(Get-NetUDPEndpoint | Where-Object LocalPort -eq 45282).Count -or @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 7782).Count) { throw 'Arm ports in use' }
        $example = Join-Path $config 'windows_receiver_settings.example.json'
        $defaults | ConvertTo-Json | Set-Content -LiteralPath $example -Encoding UTF8
        '{}' | Set-Content -LiteralPath (Join-Path $config 'windows_midi_map.json') -Encoding UTF8
        $local = Join-Path $config 'windows_receiver_settings.local.json'
        if ($arm -ne 'absent-file') {
            Copy-Item -LiteralPath 'C:\Users\Ben\AppData\Local\Temp\sdwin\fixtures\windows-installed\windows_receiver_settings.local.json' -Destination $local
            (Get-Item -LiteralPath $local).IsReadOnly = $false
            $inputSettings = [IO.File]::ReadAllText($local) | ConvertFrom-Json
            $inputSettings.listen = $defaults.listen
            $inputSettings.ui_port = $defaults.ui_port
            $inputSettings.no_ui = $defaults.no_ui
            $inputSettings.midi_port = $defaults.midi_port
            $inputSettings.feedback_port = $defaults.feedback_port
            $inputSettings.PSObject.Properties.Remove('preset_section')
            if ($arm -eq 'grandma') { Add-Member -InputObject $inputSettings -MemberType NoteProperty -Name 'preset_section' -Value 'grandma' }
            $inputSettings | ConvertTo-Json | Set-Content -LiteralPath $local -Encoding UTF8
        }
        $beforeHash = if (Test-Path -LiteralPath $local) { (Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash.ToLowerInvariant() } else { 'ABSENT' }
        $before = @(Inventory)
        $capture = Join-Path $root 'argv.jsonl'
        $env:ARGV_CAPTURE = $capture
        $parameter = if ($name -eq 'start_receiver.ps1') { '-RepoRoot' } else { '-InstallRoot' }
        $launcher = Join-Path $clone ('scripts\windows\' + $name)
        $stdout = Join-Path $root 'stdout.txt'
        $stderr = Join-Path $root 'stderr.txt'
        $child = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File', ('"' + $launcher + '"'), $parameter, ('"' + $root + '"')) -PassThru -NoNewWindow -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        $null = $child.Handle
        if (-not $child.WaitForExit(30000)) {
            Stop-Process -Id $child.Id -ErrorAction Stop
            $child.WaitForExit()
            throw "Launcher timed out: $($child.Id)"
        }
        $code = $child.ExitCode
        if (Get-Process -Id $child.Id -ErrorAction SilentlyContinue) { throw "Launcher remains $($child.Id)" }
        $argv = if (Test-Path -LiteralPath $capture) { @(Get-Content -LiteralPath $capture | ForEach-Object { $_ | ConvertFrom-Json }) } else { @() }
        foreach ($call in $argv) { if (Get-Process -Id $call.pid -ErrorAction SilentlyContinue) { throw "Stub remains $($call.pid)" } }
        $after = @(Inventory)
        if ((ConvertTo-Json -InputObject $before -Compress) -ne (ConvertTo-Json -InputObject $after -Compress)) { throw 'Receiver/Python inventory changed' }
        $afterHash = if (Test-Path -LiteralPath $local) { (Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash.ToLowerInvariant() } else { 'ABSENT' }
        $saved = if (Test-Path -LiteralPath $local) { Get-Content -LiteralPath $local -Raw | ConvertFrom-Json } else { $null }
        $results += [ordered]@{launcher=$name; arm=$arm; launcher_sha256=(Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash.ToLowerInvariant(); settings_sha256_before=$beforeHash; settings_sha256_after=$afterHash; saved=$saved; calls=@($argv); exit_code=$code; powershell_pid=$child.Id; all_child_pids_gone=$true; before=$before; after=$after; receiver_started=$false; stderr=([IO.File]::ReadAllText($stderr))}
        [IO.File]::WriteAllText((Join-Path $PSScriptRoot ($Label + '-arms.json')), (ConvertTo-Json -InputObject $results -Depth 8))
        Write-Output "$name $arm exit=$code calls=$(@($argv).Count) before=$beforeHash after=$afterHash"
    }
}
ConvertTo-Json -InputObject $results -Depth 12 | Set-Content -LiteralPath (Join-Path $PSScriptRoot ($Label + '-arms.json')) -Encoding UTF8
exit 0
