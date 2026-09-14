param([string]$Value, [string]$Out)
[IO.File]::WriteAllText($Out, $Value)
Write-Output $Value
exit 0
