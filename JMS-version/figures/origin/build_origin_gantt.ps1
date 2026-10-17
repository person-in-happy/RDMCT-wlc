[CmdletBinding()]
param(
    [switch]$Visible
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# This script is intentionally ASCII-only. Chinese strings are decoded from
# JSON Unicode escapes so Windows PowerShell 5.1 can load the file reliably.
function Convert-UnicodeJson([string]$Text) {
    return ('"' + $Text + '"' | ConvertFrom-Json)
}

function Escape-LabTalk([string]$Text) {
    return $Text.Replace('\\', '\\').Replace('"', '\"')
}

function Get-OriginColumnName([int]$OneBasedIndex) {
    $name = ''
    $n = $OneBasedIndex
    while ($n -gt 0) {
        $n--
        $name = [char][int](65 + ($n % 26)) + $name
        $n = [math]::Floor($n / 26)
    }
    return $name
}

function Hex-ToRgb([string]$Hex) {
    $value = $Hex.TrimStart('#')
    return @(
        [convert]::ToInt32($value.Substring(0, 2), 16),
        [convert]::ToInt32($value.Substring(2, 2), 16),
        [convert]::ToInt32($value.Substring(4, 2), 16)
    )
}

function Get-SourceData([string]$CaseDirectory) {
    $source = @(Get-ChildItem -LiteralPath $CaseDirectory -Filter '*_resources_gantt.svg' -File)
    if ($source.Count -ne 1) {
        throw "Expected one resource Gantt SVG in $CaseDirectory, found $($source.Count)."
    }

    $raw = Get-Content -LiteralPath $source.FullName -Raw -Encoding UTF8
    [xml]$xml = $raw
    $tasks = [System.Collections.Generic.List[object]]::new()
    foreach ($group in $xml.SelectNodes("//*[local-name()='g' and @class='task']")) {
        $tip = [string]$group.GetAttribute('data-tooltip')
        $laneMatch = [regex]::Match($tip, '(?m)^lane\s*[:=]\s*(.+)$')
        $startMatch = [regex]::Match($tip, '(?m)^start\s*[:=]\s*([-+0-9.eE]+)$')
        $endMatch = [regex]::Match($tip, '(?m)^end\s*[:=]\s*([-+0-9.eE]+)$')
        $rect = $group.SelectSingleNode("./*[local-name()='rect']")
        if (-not ($laneMatch.Success -and $startMatch.Success -and $endMatch.Success -and $rect)) {
            continue
        }
        $tasks.Add([pscustomobject]@{
            Lane = $laneMatch.Groups[1].Value.Trim()
            Start = [double]::Parse($startMatch.Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture)
            End = [double]::Parse($endMatch.Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture)
            SourceColor = ([string]$rect.GetAttribute('fill')).ToUpperInvariant()
            SourceY = [double]::Parse(([string]$rect.GetAttribute('y')), [Globalization.CultureInfo]::InvariantCulture)
        })
    }
    if ($tasks.Count -eq 0) {
        throw "No task records were parsed from $($source.FullName)."
    }

    $lanes = @($tasks | Group-Object Lane | ForEach-Object {
        [pscustomobject]@{ Name = $_.Name; SourceY = ($_.Group | Measure-Object SourceY -Minimum).Minimum }
    } | Sort-Object SourceY | Select-Object -ExpandProperty Name)

    $metricPatterns = @{
        Horizon = 'horizon=([-+0-9.eE]+)'
        Cmax = 'c_max=([-+0-9.eE]+)'
        Wph = 'WPH=([-+0-9.eE]+)'
        Completed = 'completed=([0-9]+)'
    }
    $metrics = @{}
    foreach ($entry in $metricPatterns.GetEnumerator()) {
        $match = [regex]::Match($raw, $entry.Value)
        if (-not $match.Success) { throw "Metric $($entry.Key) is missing in $($source.FullName)." }
        $metrics[$entry.Key] = $match.Groups[1].Value
    }

    return [pscustomobject]@{
        Source = $source.FullName
        Tasks = @($tasks)
        Lanes = $lanes
        Metrics = [pscustomobject]@{
            Horizon = [double]::Parse($metrics.Horizon, [Globalization.CultureInfo]::InvariantCulture)
            Cmax = [double]::Parse($metrics.Cmax, [Globalization.CultureInfo]::InvariantCulture)
            Wph = [double]::Parse($metrics.Wph, [Globalization.CultureInfo]::InvariantCulture)
            Completed = [int]$metrics.Completed
        }
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$figureRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$figureExportPath = Escape-LabTalk (($figureRoot + '\').Replace('\', '/'))
$projectPath = Join-Path $PSScriptRoot 'JMS_gantt_figures_origin.opju'

$laneCn = @{
    'ATR robot' = Convert-UnicodeJson 'ATR\u673a\u68b0\u624b'
    'AL' = Convert-UnicodeJson '\u5bf9\u51c6\u5668 AL'
    'LLupper slot 1' = Convert-UnicodeJson '\u4e0a\u88c5\u8f7d\u9501\u69fd1'
    'LLupper slot 2' = Convert-UnicodeJson '\u4e0a\u88c5\u8f7d\u9501\u69fd2'
    'VTR robot' = Convert-UnicodeJson 'VTR\u673a\u68b0\u624b'
    'CH2 PM' = Convert-UnicodeJson '\u65cb\u8f6c\u8154 CH2'
    'CH3 PM' = Convert-UnicodeJson '\u65cb\u8f6c\u8154 CH3'
    'LLlower slot 1' = Convert-UnicodeJson '\u4e0b\u88c5\u8f7d\u9501\u69fd1'
    'LLlower slot 2' = Convert-UnicodeJson '\u4e0b\u88c5\u8f7d\u9501\u69fd2'
}

$styles = @(
    [pscustomobject]@{ Source='#4C78A8'; Target='#0F4D92'; En='ATR pick'; Cn=(Convert-UnicodeJson 'ATR\u6293\u53d6') },
    [pscustomobject]@{ Source='#72B7B2'; Target='#5B8FD6'; En='ATR loaded move'; Cn=(Convert-UnicodeJson 'ATR\u5e26\u7247\u642c\u8fd0') },
    [pscustomobject]@{ Source='#9C755F'; Target='#9A4D8E'; En='ATR place / AL'; Cn=(Convert-UnicodeJson 'ATR\u653e\u7247/AL\u6821\u51c6') },
    [pscustomobject]@{ Source='#D37295'; Target='#C45AD6'; En='AL wafer exchange'; Cn=(Convert-UnicodeJson 'AL\u6362\u7247') },
    [pscustomobject]@{ Source='#59A14F'; Target='#4E8A65'; En='LL pump'; Cn=(Convert-UnicodeJson 'LL\u62bd\u6c14') },
    [pscustomobject]@{ Source='#8CD17D'; Target='#AADCA9'; En='LL vacuum wait'; Cn=(Convert-UnicodeJson 'LL\u771f\u7a7a\u7b49\u5f85') },
    [pscustomobject]@{ Source='#B279A2'; Target='#B86F6F'; En='LL vent'; Cn=(Convert-UnicodeJson 'LL\u653e\u6c14') },
    [pscustomobject]@{ Source='#D4A6C8'; Target='#E4CCD8'; En='LL atmosphere wait'; Cn=(Convert-UnicodeJson 'LL\u5927\u6c14\u7b49\u5f85') },
    [pscustomobject]@{ Source='#F58518'; Target='#E28E2C'; En='VTR / LL load'; Cn=(Convert-UnicodeJson 'VTR/LL\u88c5\u7247') },
    [pscustomobject]@{ Source='#76B7B2'; Target='#33B5A5'; En='VTR loaded / bridge'; Cn=(Convert-UnicodeJson 'VTR\u5e26\u7247/\u6865\u63a5\u642c\u8fd0') },
    [pscustomobject]@{ Source='#FF9DA6'; Target='#D9544D'; En='VTR unload'; Cn=(Convert-UnicodeJson 'VTR\u5378\u7247') },
    [pscustomobject]@{ Source='#E45756'; Target='#B64342'; En='PM process / PEC support'; Cn=(Convert-UnicodeJson '\u8154\u5ba4\u52a0\u5de5/\u8f85\u52a9\u7247\u652f\u6491') },
    [pscustomobject]@{ Source='#2A9D8F'; Target='#188977'; En='Chamber clean'; Cn=(Convert-UnicodeJson '\u8154\u5ba4\u6e05\u6d01') },
    [pscustomobject]@{ Source='#F2A09A'; Target='#F6CFCB'; En='Chamber wait'; Cn=(Convert-UnicodeJson '\u8154\u5ba4\u7b49\u5f85') },
    [pscustomobject]@{ Source='#BAB0AC'; Target='#A8A8A8'; En='Empty move / reset / bridge'; Cn=(Convert-UnicodeJson '\u7a7a\u8f7d\u79fb\u52a8/\u590d\u4f4d/\u94fe\u95f4\u6865\u63a5') }
)

$cases = @(
    [pscustomobject]@{ Directory='JMS-version\results\wafer_multiscale_gantt\gantt\wafer16_41_clean10_20260826'; Base='fig_resource_gantt_cleanH10_w16_41'; RouteWait=1632.0 },
    [pscustomobject]@{ Directory='JMS-version\results\wafer_multiscale_gantt\gantt_2x2half_20260827\wafer16_22_clean10_2x2half_20260827'; Base='fig_resource_gantt_cleanH10_w16_22'; RouteWait=1302.0 },
    [pscustomobject]@{ Directory='JMS-version\results\wafer_multiscale_gantt\3xclean\gantt\wafer16_41_clean3_20260826'; Base='fig_resource_gantt_cleanH3_w16_41'; RouteWait=1632.0 },
    [pscustomobject]@{ Directory='JMS-version\results\wafer_multiscale_gantt\gantt_cleaning_regime_representatives\wafer16_22_clean3_productcmax_20260903'; Base='fig_resource_gantt_cleanH3_w16_22'; RouteWait=536.0 }
)

$app = New-Object -ComObject Origin.ApplicationCOMSI
try {
    $app.Visible = [int]$Visible.IsPresent
    $app.NewProject()
    $figureIndex = 0

    foreach ($case in $cases) {
        $data = Get-SourceData (Join-Path $repoRoot $case.Directory)
        $laneCount = $data.Lanes.Count
        $lanePosition = @{}
        for ($i = 0; $i -lt $laneCount; $i++) {
            $lanePosition[$data.Lanes[$i]] = $laneCount - $i
        }

        foreach ($language in @('cn', 'en')) {
            $figureIndex++
            $createdBook = $app.CreatePage(2, "Data$figureIndex", 'Origin', 2)
            if (-not $createdBook) { throw 'Origin failed to create a workbook.' }
            $sheet = $app.FindWorksheet("[$createdBook]1")
            if (-not $sheet) { throw 'Origin failed to activate the new worksheet.' }
            $book = $sheet.Parent
            $sheet.Name = 'Tasks'

            # Fifteen X/start/end triplets, a categorical label column, and an
            # X/Y pair for the product-completion line.
            $sheet.Cols = 48
            $designations = ('XYY' * $styles.Count) + 'NXY'
            [void]$sheet.SetColDesignations($designations, $false, 0, 47)
            $plotIndex = 0
            $activeColors = [System.Collections.Generic.List[object]]::new()

            foreach ($style in $styles) {
                $filtered = @($data.Tasks | Where-Object {
                    $_.SourceColor -eq $style.Source -and $_.Start -lt $data.Metrics.Cmax -and $_.End -gt 0
                })
                if ($filtered.Count -eq 0) { continue }

                $x = [double[]]@($filtered | ForEach-Object { [double]$lanePosition[$_.Lane] })
                $start = [double[]]@($filtered | ForEach-Object { [math]::Max(0.0, $_.Start) })
                $end = [double[]]@($filtered | ForEach-Object { [math]::Min($data.Metrics.Cmax, $_.End) })
                $baseColumn = $plotIndex * 3
                [void]$sheet.Columns($baseColumn).SetData($x, 0)
                [void]$sheet.Columns($baseColumn + 1).SetData($start, 0)
                [void]$sheet.Columns($baseColumn + 2).SetData($end, 0)
                $label = if ($language -eq 'cn') { $style.Cn } else { $style.En }
                $labelEsc = Escape-LabTalk $label
                [void]$sheet.Execute(('col({0})[L]$="{1}";' -f ($baseColumn + 3), $labelEsc))
                $activeColors.Add([pscustomobject]@{ Plot=$plotIndex + 1; Style=$style })
                $plotIndex++
            }

            if ($plotIndex -eq 0) { throw "No recognized action colors in $($data.Source)." }
            $lastTaskColumn = $plotIndex * 3
            $labelColumn = $lastTaskColumn + 1
            $lineXColumn = $lastTaskColumn + 2
            $lineYColumn = $lastTaskColumn + 3
            $sheet.Cols = $lineYColumn
            $designationUsed = ('XYY' * $plotIndex) + 'NXY'
            [void]$sheet.SetColDesignations($designationUsed, $false, 0, $lineYColumn - 1)

            $reversedLanes = @($data.Lanes)
            [array]::Reverse($reversedLanes)
            $labelsBottomToTop = @($reversedLanes | ForEach-Object {
                if ($language -eq 'cn' -and $laneCn.ContainsKey($_)) { $laneCn[$_] } else { $_ }
            })
            [void]$sheet.Columns($labelColumn - 1).SetData([string[]]$labelsBottomToTop, 0)
            [void]$sheet.Columns($lineXColumn - 1).SetData([double[]]@(0.5, $laneCount + 0.5), 0)
            [void]$sheet.Columns($lineYColumn - 1).SetData([double[]]@($data.Metrics.Cmax, $data.Metrics.Cmax), 0)

            # Hidden square-symbol plots provide exact-color legend keys. The
            # task intervals themselves are editable rectangle objects.
            $legendXColumn = $lineYColumn + 1
            $legendYFirstColumn = $legendXColumn + 1
            $sheet.Cols = $legendXColumn + $activeColors.Count
            $designationUsed = ('XYY' * $plotIndex) + 'NXYX' + ('Y' * $activeColors.Count)
            [void]$sheet.SetColDesignations($designationUsed, $false, 0, $sheet.Cols - 1)
            [void]$sheet.Columns($legendXColumn - 1).SetData([double[]]@(-1000000.0), 0)
            for ($p = 0; $p -lt $activeColors.Count; $p++) {
                $legendYColumn = $legendYFirstColumn + $p
                [void]$sheet.Columns($legendYColumn - 1).SetData([double[]]@(-1000000.0), 0)
                $legendLabel = if ($language -eq 'cn') { $activeColors[$p].Style.Cn } else { $activeColors[$p].Style.En }
                $labelEsc = Escape-LabTalk $legendLabel
                [void]$sheet.Execute(('col({0})[L]$="{1}";' -f $legendYColumn, $labelEsc))
            }

            $createdGraph = $app.CreatePage(3, "Gantt$figureIndex", 'Origin', 2)
            if (-not $createdGraph) { throw 'Origin failed to create the Gantt graph page.' }
            $graph = $app.FindGraphLayer("[$createdGraph]1")
            if (-not $graph) { throw 'Origin failed to find the Gantt graph layer.' }
            $page = $graph.Parent
            $graphName = $page.Name
            [void]$page.Activate()

            $labelColName = Get-OriginColumnName $labelColumn
            $timeLabel = if ($language -eq 'cn') { Convert-UnicodeJson '\u65f6\u95f4 (s)' } else { 'Time (s)' }
            $metricText = if ($language -eq 'cn') {
                $perHour = Convert-UnicodeJson '\u7247/h'
                $waitText = Convert-UnicodeJson '\u8def\u7ebf\u603b\u7b49\u5f85'
                ('WPH {0:F2} {1}  |  C\-(max) {2:F0} s  |  {3} {4:F0} s' -f $data.Metrics.Wph, $perHour, $data.Metrics.Cmax, $waitText, $case.RouteWait)
            } else {
                ('WPH {0:F2} wafers/h  |  C\-(max) {1:F0} s  |  Total route wait {2:F0} s' -f $data.Metrics.Wph, $data.Metrics.Cmax, $case.RouteWait)
            }
            $metricEsc = Escape-LabTalk $metricText
            $timeEsc = Escape-LabTalk $timeLabel
            $tickStep = [math]::Ceiling(($data.Metrics.Cmax / 4.0) / 50.0) * 50.0

            [void]$graph.Execute(@"
layer.unit=1;
layer.left=25;
layer.top=4;
layer.width=72;
layer.height=57;
layer.x.from=0;
layer.x.to=$($data.Metrics.Cmax);
layer.x.inc=$tickStep;
layer.x.label.decPlaces=0;
layer.y.from=0.5;
layer.y.to=$($laneCount + 0.5);
layer.y.inc=1;
axis -ps X A 1;
axis -ps Y A 1;
axis -ps X M 0;
axis -ps Y M 0;
range __laneLabels=[$($book.Name)]Tasks!col($labelColName);
axis -ps Y T __laneLabels;
label -r yl;
label -xb "$timeEsc";
xb.fsize=8;
layer.x.label.pt=7;
layer.y.label.pt=7;
label -p 50 113 -j 1 -n metrics "\b($metricEsc)";
metrics.fsize=7.5;
metrics.background=0;
metrics.attach=0;
label -p 98 2 -j 2 -n cmax "\b(C\-(max))";
cmax.fsize=6.5;
cmax.background=0;
cmax.attach=0;
"@)

            $styleBySource = @{}
            foreach ($entry in $activeColors) { $styleBySource[$entry.Style.Source] = $entry.Style }
            $visibleTasks = @($data.Tasks | Where-Object {
                $styleBySource.ContainsKey($_.SourceColor) -and $_.Start -lt $data.Metrics.Cmax -and $_.End -gt 0
            })
            $drawCommands = [System.Collections.Generic.List[string]]::new()
            for ($taskIndex = 0; $taskIndex -lt $visibleTasks.Count; $taskIndex++) {
                $drawCommands.Add(('draw -n B{0:D4} -b;' -f ($taskIndex + 1)))
            }
            [void]$graph.Execute(($drawCommands -join ''))
            for ($taskIndex = 0; $taskIndex -lt $visibleTasks.Count; $taskIndex++) {
                $task = $visibleTasks[$taskIndex]
                $objectName = 'B{0:D4}' -f ($taskIndex + 1)
                $rect = $graph.GraphObjects($objectName)
                if (-not $rect) { throw "Origin failed to create task rectangle $objectName." }
                $start = [math]::Max(0.0, $task.Start)
                $end = [math]::Min($data.Metrics.Cmax, $task.End)
                $rgb = Hex-ToRgb $styleBySource[$task.SourceColor].Target
                $edge = @(
                    [math]::Max(0, [math]::Round($rgb[0] * 0.72)),
                    [math]::Max(0, [math]::Round($rgb[1] * 0.72)),
                    [math]::Max(0, [math]::Round($rgb[2] * 0.72))
                )
                [void]$rect.SetNumProp('attach', 2)
                $rect.X = ($start + $end) / 2.0
                $rect.Y = [double]$lanePosition[$task.Lane]
                $rect.DX = [math]::Max(0.10, $end - $start)
                $rect.DY = 0.58
                [void]$rect.SetNumProp('fillcolor', $app.Evaluate("color($($rgb[0]),$($rgb[1]),$($rgb[2]))"))
                [void]$rect.SetNumProp('color', $app.Evaluate("color($($edge[0]),$($edge[1]),$($edge[2]))"))
                [void]$rect.SetNumProp('width', 0.35)
            }

            # Draw the product-completion boundary as a scale-attached object.
            [void]$graph.Execute("draw -n CmaxLine -l -v $($data.Metrics.Cmax);")
            $cmaxLine = $graph.GraphObjects('CmaxLine')
            if ($cmaxLine) {
                [void]$cmaxLine.SetNumProp('attach', 2)
                [void]$cmaxLine.SetNumProp('color', $app.Evaluate('color(45,45,45)'))
                [void]$cmaxLine.SetNumProp('width', 0.8)
                [void]$cmaxLine.SetNumProp('style', 1)
            }

            # Add off-scale square-symbol plots solely as three-column legend keys.
            for ($p = 0; $p -lt $activeColors.Count; $p++) {
                $legendYColumn = $legendYFirstColumn + $p
                [void]$sheet.Execute("plotxy iy:=($legendXColumn,$legendYColumn) plot:=203 ogl:=[$graphName]1! legend:=0;")
                $rgb = Hex-ToRgb $activeColors[$p].Style.Target
                $edge = @(
                    [math]::Max(0, [math]::Round($rgb[0] * 0.72)),
                    [math]::Max(0, [math]::Round($rgb[1] * 0.72)),
                    [math]::Max(0, [math]::Round($rgb[2] * 0.72))
                )
                $legendYName = Get-OriginColumnName $legendYColumn
                $legendDataset = "$($book.Name)_$legendYName"
                [void]$graph.Execute("set $legendDataset -k 1; set $legendDataset -z 8; set $legendDataset -csfr color($($rgb[0]),$($rgb[1]),$($rgb[2])); set $legendDataset -cser color($($edge[0]),$($edge[1]),$($edge[2])); set $legendDataset -cr color($($edge[0]),$($edge[1]),$($edge[2]));")
            }

            $legendText = [System.Collections.Generic.List[string]]::new()
            for ($p = 0; $p -lt $activeColors.Count; $p++) {
                $legendLabel = if ($language -eq 'cn') { $activeColors[$p].Style.Cn } else { $activeColors[$p].Style.En }
                $legendText.Add("\L($($p + 1)) $legendLabel")
            }
            $legendEsc = Escape-LabTalk ($legendText -join '\n')
            [void]$graph.Execute(('label -p 3 133 -sa -n legend "{0}"; label -al 3; legend.fsize=5.4; legend.background=0; legend.attach=0; legend.vgap=8;' -f $legendEsc))

            # A compact single-column page with generous space for a 3-column legend.
            $page.Units = 0
            $page.Width = 3.5
            $page.Height = 4.25
            [void]$page.Activate()

            $baseName = $case.Base + '_' + $language + '_origin'
            $baseOut = Join-Path $figureRoot $baseName
            [void]$app.Execute(('expGraph type:=pdf export:=specified pages:="{2}" path:="{0}" filename:="{1}.pdf" overwrite:=replace tr.Margin:=0;' -f $figureExportPath, $baseName, $graphName))
            [void]$app.Execute(('expGraph type:=png export:=specified pages:="{2}" path:="{0}" filename:="{1}.png" overwrite:=replace tr1.Unit:=2 tr1.Width:=2100 tr.Margin:=0;' -f $figureExportPath, $baseName, $graphName))
            [void]$app.Execute(('expGraph type:=tif export:=specified pages:="{2}" path:="{0}" filename:="{1}.tif" overwrite:=replace tr2.TIF.DotsPerInch:=600 tr.Margin:=0;' -f $figureExportPath, $baseName, $graphName))
            [void]$app.Execute(('expGraph type:=svg export:=specified pages:="{2}" path:="{0}" filename:="{1}.svg" overwrite:=replace tr.Margin:=0;' -f $figureExportPath, $baseName, $graphName))

            Write-Host ("Origin export: {0} [{1} tasks, {2} lanes, Cmax={3:F0}]" -f $baseOut, $data.Tasks.Count, $laneCount, $data.Metrics.Cmax)
        }
    }

    [void]$app.Save($projectPath)
    Write-Host "Origin project: $projectPath"
}
finally {
    try { $app.Exit() } catch {}
    [Runtime.InteropServices.Marshal]::FinalReleaseComObject($app) | Out-Null
}
