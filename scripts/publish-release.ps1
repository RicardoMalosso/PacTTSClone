param([switch]$AppOnly)
$ErrorActionPreference = 'Stop'

$identity = @{}
$lines = python scripts/release-identity.py
if ($LASTEXITCODE -ne 0) { throw 'Could not derive release identity.' }
foreach ($line in $lines) {
    $key, $value = $line -split '=', 2
    $identity[$key] = $value
}
$tag = $identity.tag
$target = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the release commit.' }
$wheels = @(Get-ChildItem dist/*.whl)
if ($wheels.Count -ne 1 -or $wheels[0].Name -ne "pacttsclone-$($identity.version)-py3-none-any.whl") {
    throw 'Expected exactly one canonical wheel.'
}
$files = @($wheels[0], (Get-Item dist/SHA256SUMS.txt))
if (!$AppOnly) {
    $files += @(Get-Item "dist/PacTTSClone-Setup-$($identity.installer_version).exe", dist/FFmpeg-provenance.zip)
}

$existing = @(gh release list --json tagName --limit 100 | ConvertFrom-Json) | Where-Object tagName -eq $tag
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect releases.' }
if ($existing) { throw "Release $tag already exists; refusing to replace it." }
$noteArgs = @('--generate-notes')
$notes = "docs/release-$($identity.installer_version).md"
if (Test-Path $notes) { $noteArgs = @('--notes-file', $notes) }
$assets = @($files.FullName)
gh release create $tag --draft "--prerelease=$($identity.prerelease)" --target $target --title "PacTTSClone $($identity.version)" @noteArgs @assets
if ($LASTEXITCODE -ne 0) { throw 'Could not create draft release.' }

if ($env:PACTTS_PUBLISH -ne 'true') { return }
$releases = gh api "repos/$env:GITHUB_REPOSITORY/releases?per_page=100" | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Could not verify draft release.' }
$matches = @($releases | Where-Object tag_name -eq $tag)
if ($matches.Count -ne 1) { throw 'Expected exactly one draft release.' }
$release = $matches[0]
if (!$release.draft -or $release.prerelease -ne [bool]::Parse($identity.prerelease) -or
    $release.target_commitish -ne $target) {
    throw 'Unexpected draft release target or state.'
}
$uploaded = @($release.assets)
if ($uploaded.Count -ne $files.Count) { throw 'Unexpected release assets.' }
foreach ($file in $files) {
    $asset = @($uploaded | Where-Object name -eq $file.Name)
    $digest = 'sha256:' + (Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLower()
    if ($asset.Count -ne 1 -or $asset[0].size -ne $file.Length -or $asset[0].digest -ne $digest) {
        throw "Asset integrity mismatch: $($file.Name)"
    }
}
gh api --method PATCH "repos/$env:GITHUB_REPOSITORY/releases/$($release.id)" -F draft=false -f "make_latest=$($identity.make_latest)"
if ($LASTEXITCODE -ne 0) { throw 'Could not publish accepted release.' }
