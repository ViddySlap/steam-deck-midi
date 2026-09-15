$ErrorActionPreference='Continue'
$orphan='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$wg='C:\Users\Ben\AppData\Local\Temp\sdwin\wg'
$h = & git --no-optional-locks -C $orphan rev-parse HEAD; Write-Output "orphan_head=$h exit=$LASTEXITCODE"
$st=@(& git --no-optional-locks -C $orphan status --porcelain -- windows config deck protocol); Write-Output "orphan_scoped_porcelain_lines=$($st.Count) exit=$LASTEXITCODE"; $st | ForEach-Object { Write-Output "  P $_" }
$a=@(& git --no-optional-locks -C $orphan ls-tree -r d136787 -- windows config deck protocol); Write-Output "orphan_lstree_exit=$LASTEXITCODE n=$($a.Count)"
$b=@(& git -C $clone ls-tree -r e66ff44 -- windows config deck protocol); Write-Output "tag_lstree_exit=$LASTEXITCODE n=$($b.Count)"
[IO.File]::WriteAllLines("$wg\lstree-d136787.txt",$a); [IO.File]::WriteAllLines("$wg\lstree-e66ff44.txt",$b)
# engine configs as installed: presence and value SHAPE only
$cfg='C:\Program Files\STEAMDECK MIDI Receiver 2\config'
foreach ($dir in @('engines','engines.factory')) {
  foreach ($name in @('osc_sync.json','stageflow_bridge.json')) {
    $p=Join-Path (Join-Path $cfg $dir) $name
    if (-not (Test-Path -LiteralPath $p)) { Write-Output "cfg $dir\$name FILE ABSENT"; continue }
    $j=[IO.File]::ReadAllText($p) | ConvertFrom-Json
    foreach ($key in @('osc_preset_path','comp_path')) {
      $found=$null
      function Find($o,$k,$path){ if ($o -is [pscustomobject]) { foreach ($pr in $o.PSObject.Properties) { if ($pr.Name -eq $k) { $script:found=@($path+'.'+$pr.Name,[string]$pr.Value) }; Find $pr.Value $k ($path+'.'+$pr.Name) } } elseif ($o -is [array]) { foreach ($x in $o) { Find $x $k $path } } }
      $script:found=$null; Find $j $key '$'
      if ($script:found) {
        $v=$script:found[1]
        $shape = $v -replace '^([A-Za-z]:[\\/]Users[\\/])([^\\/]+)', { param($m) $m.Groups[1].Value + $(if ($m.Groups[2].Value -eq 'USERNAME') {'USERNAME'} else {'<user>'}) }
        $leaf = Split-Path -Leaf $v
        $shape = ($shape -replace '[\\/][^\\/]+[\\/]', '/.../') 
        Write-Output ("cfg {0}\{1} key {2} PRESENT at {3}; shape prefix={4} names_USERNAME_placeholder={5} ext={6} length={7}" -f $dir,$name,$key,$script:found[0], ($(if($v -match '^[A-Za-z]:[\\/]Users[\\/]USERNAME'){'C:/Users/USERNAME/...'}elseif($v -match '^[A-Za-z]:[\\/]Users[\\/]'){'C:/Users/<user>/...'}elseif($v -eq ''){'<empty>'}else{'<other>'})), ($v -match 'USERNAME'), [IO.Path]::GetExtension($v), $v.Length)
      } else { Write-Output "cfg $dir\$name key $key ABSENT" }
    }
  }
}
exit 0
