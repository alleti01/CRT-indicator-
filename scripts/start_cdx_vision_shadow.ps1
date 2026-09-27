# Shadow monitor only. Does not enable funded trading or order routing.
$ErrorActionPreference = "Stop"
$env:CDX_VISION_ENABLED = "true"
$env:CDX_VISION_SHADOW_ONLY = "true"
$env:CDX_VISION_EXECUTION_ENABLED = "false"
python -m cdx_vision.doctor
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m cdx_vision.shadow_monitor
