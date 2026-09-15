$ErrorActionPreference='Continue'
foreach ($p in @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(chrome|firefox|msedge|brave|opera|iexplore|cmd)\.exe$' })) {
  $cl=[string]$p.CommandLine; if ($cl.Length -gt 200) { $cl=$cl.Substring(0,200) }
  Write-Output "PROC $($p.ProcessId) parent=$($p.ParentProcessId) $($p.Name) start=$($p.CreationDate) $cl"
}
$h = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice' -ErrorAction SilentlyContinue
Write-Output "DEFAULT_HTTP_PROGID $($h.ProgId)"
exit 0
