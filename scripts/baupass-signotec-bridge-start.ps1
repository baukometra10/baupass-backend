# BauPass — start Signotec STPadServer if already installed (no download).
param()

$ErrorActionPreference = 'Stop'
$Port = 49494
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $scriptDir 'baupass-signotec-bridge-setup.ps1') -SkipInstall
