# 图4实验1：同规模工艺模式效率实验命令

## 是否必须补跑

当前稿件只对 8 片和 16 片作有边界的精确结论，因此不需要补跑。冻结主实验已经包含 6 个模式--规模构型，每个构型具有 5 个求解器种子与 5 个训练种子的完整交叉（25 次），合计 150 次；全部状态为 `optimal`，gap 为 0，同一构型的最优目标一致。

不得把这一结论外推到 24/32 片，除非纯 4x1、纯 2x2 和 1:1 混跑三个构型在对应规模上都达到可核查的零 gap。现有冻结结果不满足这个更强条件。

## 从冻结结果重画图4

```powershell
Set-Location D:\git\git\RDMCT-A3C
python JMS\figures\generate_result_figures.py
if ($LASTEXITCODE -ne 0) { throw 'Figure generation failed.' }
```

绘图脚本会读取冻结原始 CSV，并自动检查每个单元恰有 25 次运行、状态均为 `optimal`、gap 不超过 `1e-8`，且同一单元的最优目标极差不超过 `1e-3`；任一检查失败都会停止。

## 完整重跑 150 次 RDMCT-HBS 实验

需要 CUDA 可用，并保留 `cie/results/repro_manifest/selected_checkpoint_manifest.csv` 指向的五个冻结 Proposed 检查点。

```powershell
Set-Location D:\git\git\RDMCT-A3C

python -c "import torch; assert torch.cuda.is_available(), 'CUDA-enabled PyTorch is required'; print(torch.cuda.get_device_name(0))"
if ($LASTEXITCODE -ne 0) { throw 'CUDA preflight failed.' }

$checkpointRows = Import-Csv -LiteralPath 'cie\results\repro_manifest\selected_checkpoint_manifest.csv'
$outputRoot = 'cie\results\mode_efficiency_exact_reproduction'

foreach ($trainingSeed in 1..5) {
    $matches = @($checkpointRows | Where-Object {
        $_.family -eq 'proposed' -and [int]$_.training_seed -eq $trainingSeed
    })
    if ($matches.Count -ne 1) {
        throw "Expected exactly one frozen Proposed checkpoint for training seed $trainingSeed."
    }
    $checkpoint = $matches[0].checkpoint
    if (-not (Test-Path -LiteralPath $checkpoint -PathType Leaf)) {
        throw "Missing checkpoint: $checkpoint"
    }

    python cie\code\run_cie_benchmarks.py `
        --manifest JMS\mode_efficiency_exact_suites.json `
        --splits experiment1 `
        --suites all `
        --methods proposed `
        --seeds 1,2,3,4,5 `
        --training_seed $trainingSeed `
        --run_label "mode_efficiency_trainseed_$trainingSeed" `
        --time_limit 600 `
        --stability_profile full `
        --memory_limit_mb 2048 `
        --device cuda:0 `
        --warm_start auto `
        --proposed_model $checkpoint `
        --output_dir "$outputRoot\runs" `
        --solution_dir "$outputRoot\solutions" `
        --fail_on_empty_suite
    if ($LASTEXITCODE -ne 0) {
        throw "Benchmark failed for training seed $trainingSeed."
    }
}

python cie\code\combine_cie_runs.py `
    --input_dir "$outputRoot\runs" `
    --output_dir "$outputRoot\combined"
if ($LASTEXITCODE -ne 0) { throw 'Combining benchmark outputs failed.' }

python cie\code\analyze_cie_solutions.py `
    --input_dir "$outputRoot\runs" `
    --output_dir "$outputRoot\validation" `
    --validate `
    --fail_on_invalid
if ($LASTEXITCODE -ne 0) { throw 'Post-solve validation failed.' }
```

运行结束后，只能在六个单元全部达到零 gap、保存解全部通过验证、且每个单元的 25 次目标一致时替换稿件数值。若某个单元超时或未闭合 gap，应增加该单元求解预算后重跑，不得把 incumbent 当作精确最优值。