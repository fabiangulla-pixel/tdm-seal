# Instala las herramientas externas OPCIONALES de TDM Seal en
# %LOCALAPPDATA%\TDMSeal\tools (sin permisos de administrador, sin tocar el PATH):
#
#   - Java (Eclipse Temurin JRE 21, portable)  -> requerido por veraPDF y EPUBCheck
#   - EPUBCheck (ultima version, W3C)           -> valida los EPUB sellados
#   - veraPDF (instalacion desatendida)         -> valida los PDF/A sellados
#   - Ghostscript (solo con -ConGhostscript)    -> genera PDF/A para las pruebas de desarrollo
#
# TDM Seal las encuentra solo en esa carpeta (ver src\tdmseal\tools.py).
# Comprobar despues con:  tdmseal tools
#
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\instalar_herramientas.ps1 [-ConGhostscript]
#
# Las descargas usan curl.exe (incluido en Windows 10/11): algunos antivirus
# interceptan el TLS de otros clientes.

param([switch]$ConGhostscript)
$ErrorActionPreference = "Stop"

$tools = Join-Path $env:LOCALAPPDATA "TDMSeal\tools"
$dl = Join-Path $tools "_descargas"
New-Item -ItemType Directory -Force $tools, $dl | Out-Null

function Get-File($url, $dest) {
    Write-Host "  descargando $url"
    & curl.exe -sSL --fail -o $dest $url
    if ($LASTEXITCODE -ne 0) { throw "No se pudo descargar $url" }
}

function Get-LatestAsset($repo, $pattern) {
    $json = Join-Path $dl "$($repo -replace '/', '_').json"
    Get-File "https://api.github.com/repos/$repo/releases/latest" $json
    $release = Get-Content $json -Raw | ConvertFrom-Json
    $asset = $release.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
    if (-not $asset) { throw "No hay un archivo que coincida con $pattern en $repo" }
    return $asset.browser_download_url
}

# 1. Java -----------------------------------------------------------------
$java = Join-Path $tools "jre\bin\java.exe"
if (Test-Path $java) {
    Write-Host "[ok] Java ya instalado"
} else {
    Write-Host "[1/3] Java (Temurin JRE 21)"
    $zip = Join-Path $dl "jre.zip"
    Get-File "https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jre/hotspot/normal/eclipse" $zip
    $tmp = Join-Path $dl "jre"
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive $zip $tmp
    Move-Item (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName (Join-Path $tools "jre")
}

# 2. EPUBCheck ------------------------------------------------------------
if (Get-ChildItem $tools -Directory -Filter "epubcheck-*" -ErrorAction SilentlyContinue) {
    Write-Host "[ok] EPUBCheck ya instalado"
} else {
    Write-Host "[2/3] EPUBCheck"
    $zip = Join-Path $dl "epubcheck.zip"
    Get-File (Get-LatestAsset "w3c/epubcheck" '^epubcheck-[\d.]+\.zip$') $zip
    Expand-Archive $zip $tools
}

# 3. veraPDF --------------------------------------------------------------
$verapdf = Join-Path $tools "verapdf"
if (Test-Path (Join-Path $verapdf "verapdf.bat")) {
    Write-Host "[ok] veraPDF ya instalado"
} else {
    Write-Host "[3/3] veraPDF (instalacion desatendida)"
    $zip = Join-Path $dl "verapdf-installer.zip"
    Get-File "https://software.verapdf.org/releases/verapdf-installer.zip" $zip
    $tmp = Join-Path $dl "verapdf-installer"
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive $zip $tmp
    $jar = Get-ChildItem $tmp -Recurse -Filter "verapdf-izpack-installer-*.jar" | Select-Object -First 1
    $auto = Join-Path $dl "auto-install.xml"
    @"
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<AutomatedInstallation langpack="eng">
  <com.izforge.izpack.panels.htmlhello.HTMLHelloPanel id="welcome"/>
  <com.izforge.izpack.panels.target.TargetPanel id="install_dir">
    <installpath>$verapdf</installpath>
  </com.izforge.izpack.panels.target.TargetPanel>
  <com.izforge.izpack.panels.packs.PacksPanel id="sdk_pack_select">
    <pack index="0" name="veraPDF GUI" selected="true"/>
    <pack index="1" name="veraPDF Mac and *nix Scripts" selected="false"/>
    <pack index="2" name="veraPDF Validation model" selected="false"/>
    <pack index="3" name="veraPDF Documentation" selected="false"/>
    <pack index="4" name="veraPDF Sample Plugins" selected="false"/>
  </com.izforge.izpack.panels.packs.PacksPanel>
  <com.izforge.izpack.panels.install.InstallPanel id="install"/>
  <com.izforge.izpack.panels.finish.FinishPanel id="finish"/>
</AutomatedInstallation>
"@ | Out-File $auto -Encoding utf8
    & $java -jar $jar.FullName $auto
    if (-not (Test-Path (Join-Path $verapdf "verapdf.bat"))) { throw "La instalacion de veraPDF fallo" }
}

# 4. Ghostscript (opcional, solo desarrollo) -------------------------------
if ($ConGhostscript) {
    $gs = Join-Path $tools "gs"
    if (Test-Path (Join-Path $gs "bin\gswin64c.exe")) {
        Write-Host "[ok] Ghostscript ya instalado"
    } else {
        Write-Host "[extra] Ghostscript"
        $exe = Join-Path $dl "gs-setup.exe"
        Get-File (Get-LatestAsset "ArtifexSoftware/ghostpdl-downloads" 'w64\.exe$') $exe
        Write-Host "  El instalador puede pedir permisos y dejar abierta su ventana final: cierrela."
        Start-Process $exe -ArgumentList "/S", "/D=$gs" -Wait
    }
}

Remove-Item $dl -Recurse -Force -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "Listo. Herramientas en: $tools"
Write-Host "Compruebe con: tdmseal tools"
