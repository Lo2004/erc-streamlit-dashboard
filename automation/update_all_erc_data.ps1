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

    [string]$TradingCalendarWorkbook = "",

    [switch]$ForceRun,

    [switch]$SkipGitPush,

    [switch]$VisibleExcel
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryPathResolved = (Resolve-Path -LiteralPath $RepositoryPath).Path
if ([string]::IsNullOrWhiteSpace($TradingCalendarWorkbook)) {
    $TradingCalendarWorkbook = Join-Path $repositoryPathResolved "data\A股交易日历_2026-2028.xlsx"
}
$tradingCalendarPath = (Resolve-Path -LiteralPath $TradingCalendarWorkbook).Path
$customSourcePath = (Resolve-Path -LiteralPath $CustomSourceWorkbook).Path
$baselineSourcePath = (Resolve-Path -LiteralPath $BaselineSourceWorkbook).Path
$singleUpdater = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "update_erc_data.ps1")).Path
$customRelativePath = "data/$([IO.Path]::GetFileName($customSourcePath))"

function Test-IsConfiguredTradingDay {
    param(
        [Parameter(Mandatory = $true)][string]$CalendarPath,
        [Parameter(Mandatory = $true)][DateTime]$Date
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($CalendarPath)
    try {
        $entry = $archive.GetEntry("xl/worksheets/sheet1.xml")
        if ($null -eq $entry) {
            throw "Trading calendar workbook does not contain xl/worksheets/sheet1.xml."
        }
        $reader = New-Object IO.StreamReader($entry.Open())
        try {
            [xml]$xml = $reader.ReadToEnd()
        }
        finally {
            $reader.Dispose()
        }

        $namespace = New-Object Xml.XmlNamespaceManager($xml.NameTable)
        $namespace.AddNamespace("main", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
        $nodes = $xml.SelectNodes("//main:sheetData/main:row/main:c[starts-with(@r, 'A')]/main:v", $namespace)
        $targetSerial = [int][Math]::Floor($Date.Date.ToOADate())
        foreach ($node in $nodes) {
            $serial = 0
            if ([int]::TryParse([string]$node.InnerText, [ref]$serial) -and $serial -eq $targetSerial) {
                return $true
            }
        }
        return $false
    }
    finally {
        $archive.Dispose()
    }
}

$today = (Get-Date).Date
if (-not $ForceRun -and -not (Test-IsConfiguredTradingDay -CalendarPath $tradingCalendarPath -Date $today)) {
    Write-Host "$($today.ToString('yyyy-MM-dd')) is not in the configured A-share trading calendar; no ERC refresh is required."
    exit 0
}

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
