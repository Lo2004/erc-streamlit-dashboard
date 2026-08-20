[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceWorkbook,

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

$xlUp = -4162
$xlToLeft = -4159
$sourcePath = (Resolve-Path -LiteralPath $SourceWorkbook).Path
$repositoryPathResolved = (Resolve-Path -LiteralPath $RepositoryPath).Path
$destinationFileName = [IO.Path]::GetFileName($sourcePath)
$destinationRelativePath = "data/$destinationFileName"
$destinationPath = Join-Path $repositoryPathResolved ($destinationRelativePath -replace "/", "\")
$logDirectory = Join-Path $repositoryPathResolved "automation\logs"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$logPath = Join-Path $logDirectory ("erc-refresh-{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Write-Log {
    param([Parameter(Mandatory = $true)][string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $logPath -Value $line -Encoding utf8
}

function Get-LastDataState {
    param([Parameter(Mandatory = $true)]$Worksheet)

    $lastRow = [int]$Worksheet.Cells.Item($Worksheet.Rows.Count, 1).End($xlUp).Row
    $lastColumn = [int]$Worksheet.Cells.Item(4, $Worksheet.Columns.Count).End($xlToLeft).Column
    $lastDate = $null
    $dataRow = $lastRow

    while ($dataRow -ge 5 -and $null -eq $lastDate) {
        $rawDate = $Worksheet.Cells.Item($dataRow, 1).Value2
        if ($rawDate -is [double] -or $rawDate -is [int] -or $rawDate -is [decimal]) {
            try {
                $lastDate = [DateTime]::FromOADate([double]$rawDate).Date
            }
            catch {
                $lastDate = $null
            }
        }
        elseif ($rawDate -is [DateTime]) {
            $lastDate = ([DateTime]$rawDate).Date
        }
        elseif (-not [string]::IsNullOrWhiteSpace([string]$rawDate)) {
            $parsedDate = [DateTime]::MinValue
            if ([DateTime]::TryParse([string]$rawDate, [ref]$parsedDate)) {
                $lastDate = $parsedDate.Date
            }
        }
        if ($null -eq $lastDate) {
            $dataRow--
        }
    }

    $populatedValues = 0
    if ($null -ne $lastDate) {
        for ($column = 2; $column -le $lastColumn; $column++) {
            $value = $Worksheet.Cells.Item($dataRow, $column).Value2
            if ($null -ne $value -and -not [string]::IsNullOrWhiteSpace([string]$value)) {
                $populatedValues++
            }
        }
    }

    [PSCustomObject]@{
        LastDate = $lastDate
        LastRow = $dataRow
        LastColumn = $lastColumn
        PopulatedValues = $populatedValues
        Signature = "{0}|{1}|{2}|{3}" -f $lastDate, $dataRow, $lastColumn, $populatedValues
    }
}

function Get-WindFormulaError {
    param([Parameter(Mandatory = $true)]$Worksheet)

    # This workbook's WSD control formula lives in B5.  Wind can finish the
    # Excel calculation while returning a quota/permission error there, so the
    # data-date check alone is not sufficient on weekends or long holidays.
    $value = [string]$Worksheet.Range("B5").Value2
    $errorPattern = "\u8D85\u9650|\u5931\u8D25|\u9519\u8BEF|\u8BF7\u8054\u7CFB|\u65E0\u6743\u9650|#N/A|#VALUE|#REF|#NAME|#NUM"
    if ($value -match $errorPattern) {
        return $value
    }
    return ""
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [int[]]$AllowedExitCodes = @(0),
        [switch]$Quiet
    )

    # Windows PowerShell 5.1 turns native stderr into ErrorRecord objects and,
    # with the script-wide Stop preference, can throw even when git exits 0
    # (for example, `git pull` writes its normal "From ..." line to stderr).
    $previousErrorActionPreference = $ErrorActionPreference
    $hasNativePreference = $null -ne (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue)
    if ($hasNativePreference) {
        $previousNativePreference = $PSNativeCommandUseErrorActionPreference
    }
    try {
        $ErrorActionPreference = "Continue"
        if ($hasNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $false
        }
        $output = & $script:gitExecutable -C $script:repositoryPathResolved @ArgumentList 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        if ($hasNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $previousNativePreference
        }
    }
    if (-not $Quiet -and $output) {
        foreach ($line in $output) {
            Write-Log "git: $line"
        }
    }
    if ($AllowedExitCodes -notcontains $exitCode) {
        throw "git $($ArgumentList -join ' ') failed with exit code $exitCode."
    }
    return @($output)
}

$mutex = New-Object System.Threading.Mutex($false, "Local\ERC_Dashboard_Daily_Refresh")
$mutexAcquired = $false
$excel = $null
$workbook = $null
$worksheet = $null
$windComAddIn = $null

function Close-RefreshMutex {
    if ($script:mutexAcquired) {
        try { [void]$script:mutex.ReleaseMutex() } catch {}
        $script:mutexAcquired = $false
    }
    if ($null -ne $script:mutex) {
        try { $script:mutex.Dispose() } catch {}
        $script:mutex = $null
    }
}

try {
    # The outer scope owns the refresh lock and error log.  Excel itself is
    # cleaned up by the nested try/finally below.
    try {
    try {
        $mutexAcquired = $mutex.WaitOne(0)
    }
    catch [System.Threading.AbandonedMutexException] {
        $mutexAcquired = $true
        Write-Log "Recovered an abandoned refresh lock from an earlier interrupted run."
    }
    if (-not $mutexAcquired) {
        throw "Another ERC refresh is already running."
    }

    Write-Log "Starting ERC refresh. Source: $sourcePath"
    Write-Log "Repository: $repositoryPathResolved"

    if (-not (Test-Path -LiteralPath (Join-Path $repositoryPathResolved ".git"))) {
        throw "Repository path is not a Git checkout: $repositoryPathResolved"
    }
    if (-not (Test-Path -LiteralPath (Split-Path -Parent $destinationPath))) {
        throw "Destination data directory does not exist: $(Split-Path -Parent $destinationPath)"
    }

    if (-not $SkipGitPush) {
        $script:gitExecutable = (Get-Command git.exe -ErrorAction Stop).Source
        $statusLines = Invoke-Git -ArgumentList @("-c", "core.quotepath=false", "status", "--porcelain", "--untracked-files=no") -Quiet
        $unexpectedChanges = @(
            $statusLines | Where-Object {
                $line = [string]$_
                $line -and -not $line.EndsWith($destinationRelativePath)
            }
        )
        if ($unexpectedChanges.Count -gt 0) {
            throw "Repository has unrelated tracked changes. Resolve them before the scheduled refresh: $($unexpectedChanges -join '; ')"
        }
    }

    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = [bool]$VisibleExcel
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false

    try {
        $windComAddIn = $excel.COMAddIns.Item("WDF.Addin")
        if (-not $windComAddIn.Connect) {
            $windComAddIn.Connect = $true
        }
        Start-Sleep -Seconds 5
        if (-not $windComAddIn.Connect) {
            throw "WDF.Addin remained disconnected."
        }
        Write-Log "Wind Excel add-in is connected."
    }
    catch {
        throw "Wind Excel add-in WDF.Addin could not be loaded in this Excel instance: $($_.Exception.Message)"
    }

    Write-Log "Opening Excel workbook and requesting Wind refresh."
    $workbook = $excel.Workbooks.Open($sourcePath, 3, $false)
    if ($workbook.ReadOnly) {
        throw "Source workbook opened read-only. Close any other copy and retry."
    }
    $worksheet = $workbook.Worksheets.Item(1)
    $initialState = Get-LastDataState -Worksheet $worksheet
    Write-Log "Initial last data date: $($initialState.LastDate); rows: $($initialState.LastRow); populated values: $($initialState.PopulatedValues)."

    $workbook.RefreshAll()
    $excel.CalculateFullRebuild()

    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    $stableCount = 0
    $lastSignature = ""
    $finalState = $null
    $refreshStarted = Get-Date

    while ((Get-Date) -lt $deadline) {
        try {
            $excel.CalculateUntilAsyncQueriesDone()
        }
        catch {
            # Wind's Excel add-in may not expose an async-query handle; polling below remains authoritative.
        }

        $currentState = Get-LastDataState -Worksheet $worksheet
        $calculationDone = ([int]$excel.CalculationState -eq 0)
        $dataAge = if ($null -ne $currentState.LastDate) {
            ((Get-Date).Date - $currentState.LastDate).Days
        }
        else {
            [int]::MaxValue
        }
        $dateDidNotRegress = $null -eq $initialState.LastDate -or (
            $null -ne $currentState.LastDate -and $currentState.LastDate -ge $initialState.LastDate
        )
        $windFormulaError = Get-WindFormulaError -Worksheet $worksheet
        $dataLooksValid = (
            $null -ne $currentState.LastDate -and
            $dataAge -le $MaxDataAgeDays -and
            $dateDidNotRegress -and
            $currentState.PopulatedValues -ge 5 -and
            [string]::IsNullOrWhiteSpace($windFormulaError)
        )

        if ($calculationDone -and $dataLooksValid -and $currentState.Signature -eq $lastSignature) {
            $stableCount++
        }
        else {
            $stableCount = 0
        }
        $lastSignature = $currentState.Signature

        $elapsedSeconds = [int]((Get-Date) - $refreshStarted).TotalSeconds
        if ($stableCount -ge $StablePollCount -and $elapsedSeconds -ge 30) {
            $finalState = $currentState
            break
        }

        if (($elapsedSeconds % 30) -lt 5) {
            $windStatus = if ([string]::IsNullOrWhiteSpace($windFormulaError)) { "OK" } else { $windFormulaError }
            Write-Log "Waiting for Wind. CalculationDone=$calculationDone; LastDate=$($currentState.LastDate); DataAge=$dataAge; FormulaStatus=$windStatus; Stable=$stableCount/$StablePollCount."
        }
        Start-Sleep -Seconds 5
    }

    if ($null -eq $finalState) {
        $lastObserved = Get-LastDataState -Worksheet $worksheet
        throw "Wind refresh did not reach a valid stable state within $TimeoutMinutes minutes. Last observed date: $($lastObserved.LastDate)."
    }

    Write-Log "Wind refresh completed. Last data date: $($finalState.LastDate); rows: $($finalState.LastRow); populated values: $($finalState.PopulatedValues)."
    $workbook.Save()
    Write-Log "Saved refreshed source workbook."
    }
    finally {
        if ($null -ne $workbook) {
            try { $workbook.Close($false) } catch { Write-Log "Warning while closing workbook: $($_.Exception.Message)" }
        }
        if ($null -ne $excel) {
            try { $excel.Quit() } catch { Write-Log "Warning while quitting Excel: $($_.Exception.Message)" }
        }
        if ($null -ne $worksheet) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($worksheet) }
        if ($null -ne $workbook) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($workbook) }
        if ($null -ne $windComAddIn) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($windComAddIn) }
        if ($null -ne $excel) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) }
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
    }

    $temporaryDestination = "$destinationPath.refreshing"
    Copy-Item -LiteralPath $sourcePath -Destination $temporaryDestination -Force
    Move-Item -LiteralPath $temporaryDestination -Destination $destinationPath -Force
    Write-Log "Copied refreshed workbook to $destinationPath."

    if ($SkipGitPush) {
        Write-Log "SkipGitPush was set; refresh finished without publishing."
    }
    else {
        $branchOutput = Invoke-Git -ArgumentList @("branch", "--show-current") -Quiet | Select-Object -First 1
        $branch = if ($null -eq $branchOutput) { "" } else { ([string]$branchOutput).Trim() }
        if ([string]::IsNullOrWhiteSpace($branch)) {
            throw "Cannot publish from a detached HEAD."
        }

        $gitName = (Invoke-Git -ArgumentList @("config", "user.name") -AllowedExitCodes @(0, 1) -Quiet | Select-Object -First 1)
        if ([string]::IsNullOrWhiteSpace([string]$gitName)) {
            Invoke-Git -ArgumentList @("config", "user.name", "ERC Dashboard Updater") | Out-Null
        }
        $gitEmail = (Invoke-Git -ArgumentList @("config", "user.email") -AllowedExitCodes @(0, 1) -Quiet | Select-Object -First 1)
        if ([string]::IsNullOrWhiteSpace([string]$gitEmail)) {
            Invoke-Git -ArgumentList @("config", "user.email", "erc-dashboard-updater@users.noreply.github.com") | Out-Null
        }

        Invoke-Git -ArgumentList @("add", "--", $destinationRelativePath) | Out-Null
        & $gitExecutable -C $repositoryPathResolved diff --cached --quiet -- $destinationRelativePath
        $diffExitCode = $LASTEXITCODE
        if ($diffExitCode -eq 0) {
            Write-Log "No workbook changes to publish."
        }
        elseif ($diffExitCode -eq 1) {
            $commitMessage = "Update ERC data through $($finalState.LastDate.ToString('yyyy-MM-dd'))"
            Invoke-Git -ArgumentList @("commit", "-m", $commitMessage, "--", $destinationRelativePath) | Out-Null
            Write-Log "Created data update commit."
        }
        else {
            throw "git diff failed with exit code $diffExitCode."
        }

        $pulled = $false
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            try {
                Invoke-Git -ArgumentList @("pull", "--rebase", "--autostash", "origin", $branch) | Out-Null
                $pulled = $true
                break
            }
            catch {
                if ($attempt -ge 3) { throw }
                Write-Log "Pull attempt $attempt failed; retrying. $($_.Exception.Message)"
                Start-Sleep -Seconds (20 * $attempt)
            }
        }

        if (-not $pulled) {
            throw "Failed to update the local branch before publishing."
        }

        $published = $false
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            try {
                Invoke-Git -ArgumentList @("push", "origin", "HEAD:$branch") | Out-Null
                $published = $true
                break
            }
            catch {
                if ($attempt -ge 3) { throw }
                Write-Log "Push attempt $attempt failed; retrying. $($_.Exception.Message)"
                Start-Sleep -Seconds (20 * $attempt)
            }
        }

        if (-not $published) {
            throw "Failed to publish refreshed ERC data."
        }

        Write-Log "Published refreshed data to origin/$branch. Streamlit will redeploy automatically."
    }
}
catch {
    try { Write-Log "ERROR: $($_.Exception.Message)" } catch {}
    throw
}
finally {
    Close-RefreshMutex
}
