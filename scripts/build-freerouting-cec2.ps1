# SPDX-License-Identifier: Apache-2.0
# Rebuild the hash-pinned CEC Freerouting 1.7.0-cec2 artifact.
[CmdletBinding()]
param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).ProviderPath
if (-not $OutputPath) {
    $OutputPath = Join-Path $repoRoot "build\fr-fork\freerouting-1.7.0-cec2.jar"
}

$jdkUrl = "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20%2B8/OpenJDK17U-jdk_x64_windows_hotspot_17.0.20_8.zip"
$jdkSha256 = "418497be5cf585bdd2203d6486a565d66d3f5e992d5630d45104cb873fab8122"
$jarSha256 = "149cebd88169be77f5ddc7e1d50284451204f10c088e5d7380859ab0395b7ce5"
$baseCommit = "ba0b23e89858bbfe7113df38f9de8dab090a0079"
$patchPath = Join-Path $repoRoot "scripts\patches\freerouting-1.7.0-cec2.patch"

$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$tempRoot = Join-Path $tempBase ("cec-fr-cec2-" + [guid]::NewGuid().ToString("N"))
$tempFull = [IO.Path]::GetFullPath($tempRoot)
if (-not $tempFull.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing unsafe temporary directory: $tempFull"
}

$sourceDir = Join-Path $tempRoot "source"
$jdkArchive = Join-Path $tempRoot "jdk17.zip"
$jdkExtract = Join-Path $tempRoot "jdk"
$gradleHome = Join-Path $tempRoot "gradle-home"
$oldJavaHome = $env:JAVA_HOME
$oldGradleHome = $env:GRADLE_USER_HOME
$hadJavaHome = Test-Path Env:JAVA_HOME
$hadGradleHome = Test-Path Env:GRADLE_USER_HOME

try {
    if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
        throw "git.exe is required"
    }
    if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
        throw "curl.exe is required"
    }

    New-Item -ItemType Directory -Force -Path $tempRoot, $jdkExtract, $gradleHome | Out-Null

    & git.exe clone --filter=blob:none --depth 1 --branch v1.7.0 `
        https://github.com/freerouting/freerouting.git $sourceDir
    if ($LASTEXITCODE -ne 0) {
        throw "Freerouting clone failed with exit $LASTEXITCODE"
    }
    $actualCommit = (& git.exe -C $sourceDir rev-parse HEAD).Trim()
    if ($actualCommit -ne $baseCommit) {
        throw "Freerouting base mismatch: expected $baseCommit, got $actualCommit"
    }

    & git.exe -C $sourceDir apply $patchPath
    if ($LASTEXITCODE -ne 0) {
        throw "CEC patch failed to apply with exit $LASTEXITCODE"
    }

    & curl.exe -fL --retry 3 -o $jdkArchive $jdkUrl
    if ($LASTEXITCODE -ne 0) {
        throw "Temurin download failed with exit $LASTEXITCODE"
    }
    $actualJdkSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $jdkArchive).Hash.ToLowerInvariant()
    if ($actualJdkSha -ne $jdkSha256) {
        throw "Temurin archive hash mismatch: expected $jdkSha256, got $actualJdkSha"
    }
    Expand-Archive -LiteralPath $jdkArchive -DestinationPath $jdkExtract
    $jdkDir = (Get-ChildItem -LiteralPath $jdkExtract -Directory | Select-Object -First 1).FullName
    if (-not (Test-Path -LiteralPath (Join-Path $jdkDir "bin\javac.exe"))) {
        throw "Temurin JDK extraction did not produce javac.exe"
    }

    $env:JAVA_HOME = $jdkDir
    $env:GRADLE_USER_HOME = $gradleHome
    Push-Location $sourceDir
    try {
        & .\gradlew.bat executableJar --rerun-tasks --no-daemon --console=plain
        if ($LASTEXITCODE -ne 0) {
            throw "Gradle build failed with exit $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    $artifact = Join-Path $sourceDir "build\libs\freerouting-executable.jar"
    $actualJarSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifact).Hash.ToLowerInvariant()
    if ($actualJarSha -ne $jarSha256) {
        throw "Freerouting JAR hash mismatch: expected $jarSha256, got $actualJarSha"
    }

    $outputParent = Split-Path -Parent $OutputPath
    New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
    Copy-Item -LiteralPath $artifact -Destination $OutputPath -Force
    Write-Output "Built $OutputPath"
    Write-Output "sha256 $actualJarSha"
}
finally {
    if ($hadJavaHome) { $env:JAVA_HOME = $oldJavaHome } else { Remove-Item Env:JAVA_HOME -ErrorAction SilentlyContinue }
    if ($hadGradleHome) { $env:GRADLE_USER_HOME = $oldGradleHome } else { Remove-Item Env:GRADLE_USER_HOME -ErrorAction SilentlyContinue }
    if ((Test-Path -LiteralPath $tempFull) -and
        $tempFull.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase)) {
        # PowerShell 5.1 Remove-Item cannot reliably delete Gradle's paths once
        # they exceed MAX_PATH. Use the Win32 extended-path form and retry the
        # exact validated temp target so a successful rebuild never strands the
        # downloaded JDK, source clone, or Gradle cache.
        $extendedTemp = "\\?\" + $tempFull
        for ($attempt = 1; $attempt -le 10; $attempt++) {
            try {
                # Git marks pack files read-only. Directory.Delete honors that
                # attribute even when the caller is an administrator.
                foreach ($file in [IO.Directory]::EnumerateFiles(
                    $extendedTemp, "*", [IO.SearchOption]::AllDirectories)) {
                    [IO.File]::SetAttributes($file, [IO.FileAttributes]::Normal)
                }
                [IO.Directory]::Delete($extendedTemp, $true)
                break
            }
            catch {
                if ($attempt -eq 10) { throw }
                Start-Sleep -Milliseconds 500
            }
        }
    }
}
