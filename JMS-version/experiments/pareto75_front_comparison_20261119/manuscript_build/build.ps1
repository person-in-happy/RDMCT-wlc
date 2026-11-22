$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
1..3 | ForEach-Object {
    & xelatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
    if ($LASTEXITCODE -ne 0) { throw 'XeLaTeX failed; inspect main.log.' }
}
