[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceWorkbook,

    [string]$RepositoryPath = (Split-Path -Parent $PSScriptRoot),

    [string]$TaskName = "ERC Dashboard Daily Refresh",

    [ValidatePattern("^([01]\d|2[0-3]):[0-5]\d$")]
    [string]$At = "17:00"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$sourcePath = (Resolve-Path -LiteralPath $SourceWorkbook).Path
$repositoryPathResolved = (Resolve-Path -LiteralPath $RepositoryPath).Path
$refreshScript = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "update_erc_data.ps1")).Path
$powerShellExecutable = (Get-Command powershell.exe -ErrorAction Stop).Source
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$triggerTime = [DateTime]::Today.Add([TimeSpan]::ParseExact($At, "hh\:mm", $null))

$arguments = @(
    "-NoProfile",
    "-NonInteractive",
    "-WindowStyle Hidden",
    "-ExecutionPolicy Bypass",
    "-File `"$refreshScript`"",
    "-SourceWorkbook `"$sourcePath`"",
    "-RepositoryPath `"$repositoryPathResolved`"",
    "-VisibleExcel"
) -join " "

$action = New-ScheduledTaskAction -Execute $powerShellExecutable -Argument $arguments -WorkingDirectory $repositoryPathResolved
$trigger = New-ScheduledTaskTrigger -Daily -At $triggerTime
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Refresh the Wind-backed ERC workbook and publish it to Streamlit every day at $At."

if ($PSCmdlet.ShouldProcess($TaskName, "Register daily ERC refresh task for $At")) {
    Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
}

$registeredTask = Get-ScheduledTask -TaskName $TaskName
$taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
[PSCustomObject]@{
    TaskName = $registeredTask.TaskName
    State = $registeredTask.State
    User = $currentUser
    Schedule = "Daily $At"
    NextRunTime = $taskInfo.NextRunTime
    SourceWorkbook = $sourcePath
    RepositoryPath = $repositoryPathResolved
}
