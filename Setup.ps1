$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or newer and retry.' }
}
& '.venv/Scripts/python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
New-Item -ItemType Directory -Path 'models/bge' -Force | Out-Null
$revision = 'aa8f8b060edb00e03bfdd08813a2949946c8ba55'
foreach ($file in @('config.json','model_optimized.onnx','special_tokens_map.json','tokenizer_config.json','tokenizer.json','vocab.txt')) {
    $destination = Join-Path $PSScriptRoot ('models/bge/' + $file)
    if (-not (Test-Path -LiteralPath $destination)) {
        curl.exe --fail --location --retry 2 --output $destination "https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q/resolve/$revision/$file"
        if ($LASTEXITCODE -ne 0) { throw "Could not download $file. Retry Setup.ps1." }
    }
}
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
New-Item -ItemType Directory -Path 'demo/papers' -Force | Out-Null
foreach ($paper in (Get-Content -LiteralPath 'demo/manifest.json' -Raw | ConvertFrom-Json)) {
    $destination = Join-Path $PSScriptRoot ('demo/papers/' + $paper.id + '.pdf')
    if (-not (Test-Path -LiteralPath $destination)) {
        curl.exe --fail --location --retry 2 --output $destination $paper.source_url
        if ($LASTEXITCODE -ne 0) { throw ('Could not download ' + $paper.id) }
    }
    if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $paper.pdf_sha256) {
        throw ('PDF differs from the pinned source hash: ' + $paper.id)
    }
}
& '.venv/Scripts/python.exe' scripts/seed_demo.py
if ($LASTEXITCODE -ne 0) { throw 'Demo indexing failed.' }
Write-Host 'Setup complete. Set your key in .env, then double-click Start.cmd.'
