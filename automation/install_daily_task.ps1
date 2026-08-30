[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$CustomSourceWorkbook,

    [Parameter(Mandatory = $true)]
    [string]$BaselineSourceWorkbook,

    [string]$RepositoryPath = (Split-Path -Parent $PSScriptRoot),

    [string]$TaskName = "ERC Dashboard Daily Refresh",

    [ValidatePattern("^([01]\d|2[0-3]):[0-5]\d$")]
    [string]$At = "17:00"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$customSourcePath = (Resolve-Path -LiteralPath $CustomSourceWorkbook).Path
$baselineSourcePath = (Resolve-Path -LiteralPath $BaselineSourceWorkbook).Path
$repositoryPathResolved = (Resolve-Path -LiteralPath $RepositoryPath).Path
$refreshScript = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "update_all_erc_data.ps1")).Path
$powerShellExecutable = (Get-Command powershell.exe -ErrorAction Stop).Source
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$triggerTime = [DateTime]::Today.Add([TimeSpan]::ParseExact($At, "hh\:mm", $null))

$arguments = @(
    "-NoProfile",
    "-NonInteractive",
    "-WindowStyle Hidden",
    "-ExecutionPolicy Bypass",
    "-File `"$refreshScript`"",
    "-CustomSourceWorkbook `"$customSourcePath`"",
    "-BaselineSourceWorkbook `"$baselineSourcePath`"",
    "-RepositoryPath `"$repositoryPathResolved`"",
    "-VisibleExcel"
) -join " "

$action = New-ScheduledTaskAction -Execute $powerShellExecutable -Argument $arguments -WorkingDirectory $repositoryPathResolved
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $triggerTime
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Refresh custom and baseline ERC data at $At on configured A-share trading days."

if ($PSCmdlet.ShouldProcess($TaskName, "Register daily ERC refresh task for $At")) {
    Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
}

$registeredTask = Get-ScheduledTask -TaskName $TaskName
$taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
[PSCustomObject]@{
    TaskName = $registeredTask.TaskName
    State = $registeredTask.State
    User = $currentUser
    Schedule = "A-share trading days at $At (weekday trigger plus calendar gate)"
    NextRunTime = $taskInfo.NextRunTime
    CustomSourceWorkbook = $customSourcePath
    BaselineSourceWorkbook = $baselineSourcePath
    RepositoryPath = $repositoryPathResolved
}
