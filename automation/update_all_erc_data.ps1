[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CustomSourceWorkbook,

    [Parameter(Mandatory = $true)]
    [string]$BaselineSourceWorkbook,

    [string]$RepositoryPath = (Split-Path -Parent $PSScriptRoot),

    [ValidateRange(1, 60)]
    [int]$TimeoutMinutes = 12,

    [ValidateRange(1, 31)]
    [int]$MaxDataAgeDays = 12,

    [ValidateRange(2, 20)]
    [int]$StablePollCount = 4,

    [switch]$SkipGitPush,

    [switch]$VisibleExcel
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryPathResolved = (Resolve-Path -LiteralPath $RepositoryPath).Path
$customSourcePath = (Resolve-Path -LiteralPath $CustomSourceWorkbook).Path
$baselineSourcePath = (Resolve-Path -LiteralPath $BaselineSourceWorkbook).Path
$singleUpdater = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "update_erc_data.ps1")).Path
$customRelativePath = "data/$([IO.Path]::GetFileName($customSourcePath))"

$commonArguments = @{
    RepositoryPath = $repositoryPathResolved
    TimeoutMinutes = $TimeoutMinutes
    MaxDataAgeDays = $MaxDataAgeDays
    StablePollCount = $StablePollCount
}
if ($VisibleExcel) {
    $commonArguments.VisibleExcel = $true
}

Write-Host "Refreshing custom ERC workbook first."
& $singleUpdater @commonArguments `
    -SourceWorkbook $customSourcePath `
    -ExpectedAssetCount 29 `
    -SkipGitPush

Write-Host "Refreshing baseline ERC workbook, then publishing both datasets."
$baselineArguments = @{
    SourceWorkbook = $baselineSourcePath
    ExpectedAssetCount = 6
    AdditionalPublishPaths = @($customRelativePath)
}
if ($SkipGitPush) {
    $baselineArguments.SkipGitPush = $true
}
& $singleUpdater @commonArguments @baselineArguments
