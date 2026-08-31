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
$wrapperLogDirectory = Join-Path $repositoryPathResolved "automation\logs"
New-Item -ItemType Directory -Force -Path $wrapperLogDirectory | Out-Null
$wrapperLogPath = Join-Path $wrapperLogDirectory ("erc-all-refresh-{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Write-WrapperLog {
    param([Parameter(Mandatory = $true)][string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $wrapperLogPath -Value $line -Encoding utf8
}

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

try {
    Write-WrapperLog "Starting combined ERC refresh."
    if ([string]::IsNullOrWhiteSpace($TradingCalendarWorkbook)) {
        $TradingCalendarWorkbook = Join-Path $repositoryPathResolved "data\A股交易日历_2026-2028.xlsx"
    }
    $tradingCalendarPath = (Resolve-Path -LiteralPath $TradingCalendarWorkbook).Path
    $customSourcePath = (Resolve-Path -LiteralPath $CustomSourceWorkbook).Path
    $baselineSourcePath = (Resolve-Path -LiteralPath $BaselineSourceWorkbook).Path
    $singleUpdater = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "update_erc_data.ps1")).Path
    $customRelativePath = "data/$([IO.Path]::GetFileName($customSourcePath))"

    $today = (Get-Date).Date
    if (-not $ForceRun -and -not (Test-IsConfiguredTradingDay -CalendarPath $tradingCalendarPath -Date $today)) {
        Write-WrapperLog "$($today.ToString('yyyy-MM-dd')) is not in the configured A-share trading calendar; no ERC refresh is required."
        exit 0
    }
    Write-WrapperLog "$($today.ToString('yyyy-MM-dd')) is a configured A-share trading day."

    $commonArguments = @{
        RepositoryPath = $repositoryPathResolved
        TimeoutMinutes = $TimeoutMinutes
        MaxDataAgeDays = $MaxDataAgeDays
        StablePollCount = $StablePollCount
    }
    if ($VisibleExcel) {
        $commonArguments.VisibleExcel = $true
    }

    Write-WrapperLog "Refreshing custom ERC workbook first."
    & $singleUpdater @commonArguments `
        -SourceWorkbook $customSourcePath `
        -ExpectedAssetCount 29 `
        -SkipGitPush

    Write-WrapperLog "Refreshing baseline ERC workbook, then publishing both datasets."
    $baselineArguments = @{
        SourceWorkbook = $baselineSourcePath
        ExpectedAssetCount = 6
        AdditionalPublishPaths = @($customRelativePath)
    }
    if ($SkipGitPush) {
        $baselineArguments.SkipGitPush = $true
    }
    & $singleUpdater @commonArguments @baselineArguments
    Write-WrapperLog "Combined ERC refresh completed successfully."
}
catch {
    try { Write-WrapperLog "ERROR: $($_.Exception.Message)" } catch {}
    throw
}
