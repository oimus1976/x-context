[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedTestHead,

    [Parameter(Mandatory = $true)]
    [string]$TopicBranch,

    [string]$LogPrefix = "validation"
)

$ErrorActionPreference = "Stop"

$scriptRoot = $PSScriptRoot
$profile = Join-Path (Split-Path $scriptRoot -Parent) "PROJECT_PROFILE.toml"
$guard = Join-Path $scriptRoot "validation_workspace.py"

if (-not (Test-Path -LiteralPath $profile)) {
    throw "PROJECT_PROFILE.toml not found beside validation tooling: $profile"
}
if (-not (Test-Path -LiteralPath $guard)) {
    throw "Validation workspace guard not found: $guard"
}

$policyJson = & python $guard --profile $profile paths
if ($LASTEXITCODE -ne 0) {
    throw "Failed to load validation workspace policy from $profile"
}
$policy = $policyJson | ConvertFrom-Json

$repo = [string]$policy.canonical_repo
$worktreeRoot = [string]$policy.worktree_root
$logDir = [string]$policy.durable_log_dir
$expectedFinalBranch = [string]$policy.final_branch

& python $guard --profile $profile check-repo $repo
if ($LASTEXITCODE -ne 0) {
    throw "Canonical repository policy check failed: $repo"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$verify = Join-Path $worktreeRoot "$LogPrefix-$timestamp"
$log = Join-Path $logDir "$LogPrefix-$timestamp.log"

& python $guard --profile $profile check-disposable --kind worktree $verify
if ($LASTEXITCODE -ne 0) {
    throw "Disposable worktree policy check failed: $verify"
}
& python $guard --profile $profile check-log $log
if ($LASTEXITCODE -ne 0) {
    throw "Durable log policy check failed: $log"
}

New-Item -ItemType Directory -Force -Path $worktreeRoot | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($log, "", $utf8NoBom)

$failure = $null
$worktreeAdded = $false

function Write-Log {
    param([string]$Message = "")
    Write-Host $Message
    [System.IO.File]::AppendAllText(
        $log,
        $Message + [Environment]::NewLine,
        $utf8NoBom
    )
}

function Invoke-LoggedNative {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandLine
    )

    & cmd.exe /d /c $CommandLine 2>&1 |
        ForEach-Object {
            Write-Log ([string]$_)
        }

    return [int]$LASTEXITCODE
}

function Add-Failure {
    param([string]$Message)
    if ($null -eq $script:failure) {
        $script:failure = $Message
    }
    else {
        $script:failure = "$($script:failure) | $Message"
    }
    Write-Log "FAIL: $Message"
}

function Get-RepoRelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Child
    )

    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $childFull = [System.IO.Path]::GetFullPath($Child)
    $rootUri = New-Object System.Uri($rootFull)
    $childUri = New-Object System.Uri($childFull)
    $relativeUri = $rootUri.MakeRelativeUri($childUri)
    return [System.Uri]::UnescapeDataString($relativeUri.ToString()).Replace('/', '/')
}

$logRelative = Get-RepoRelativePath -Root $repo -Child $log

try {
    Write-Log "=== x-context exact-head validation ==="
    $utf8Probe = "UTF8_PROBE=" + [char]0x65E5 + [char]0x672C + [char]0x8A9E
    Write-Log $utf8Probe
    Write-Log "START_TIME=$(Get-Date -Format o)"
    Write-Log "PROFILE=$profile"
    Write-Log "CANONICAL_REPO=$repo"
    Write-Log "TOPIC_BRANCH=$TopicBranch"
    Write-Log "EXPECTED_TEST_HEAD=$ExpectedTestHead"
    Write-Log "VERIFY_WORKTREE=$verify"
    Write-Log "LOG_PATH=$log"

    if (-not (Test-Path -LiteralPath $repo)) {
        throw "Canonical repository does not exist: $repo"
    }

    Set-Location $repo

    Write-Log ""
    Write-Log "=== preflight canonical checkout ==="

    $preBranch = (git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { throw "git branch --show-current failed" }

    $preStatus = @(git status --short --untracked-files=all)
    if ($LASTEXITCODE -ne 0) { throw "git status --short failed" }

    # The durable log may be ignored by local/global Git configuration; if it is
    # visible as untracked, only this exact current log entry is permitted.
    $unexpectedPre = @($preStatus | Where-Object {
        $_ -and $_ -ne "?? $logRelative"
    })

    Write-Log "PREFLIGHT_BRANCH=$preBranch"
    Write-Log "PREFLIGHT_STATUS_BEGIN"
    if ($preStatus.Count -eq 0) { Write-Log "<clean>" }
    else { $preStatus | ForEach-Object { Write-Log $_ } }
    Write-Log "PREFLIGHT_STATUS_END"

    if ($preBranch -ne $expectedFinalBranch) {
        throw "Canonical checkout is not on $expectedFinalBranch. Actual: $preBranch"
    }
    if ($unexpectedPre.Count -ne 0) {
        throw "Canonical checkout has unexpected preflight status entries: $($unexpectedPre -join ' | ')"
    }

    Write-Log ""
    Write-Log "=== git fetch origin ==="
    $fetchExit = Invoke-LoggedNative "git fetch origin 2>&1"
    Write-Log "FETCH_EXIT=$fetchExit"
    if ($fetchExit -ne 0) { throw "git fetch origin failed with exit code $fetchExit" }

    $originMain = (git rev-parse origin/main).Trim()
    if ($LASTEXITCODE -ne 0) { throw "git rev-parse origin/main failed" }

    $canonicalHead = (git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "git rev-parse HEAD failed in canonical repo" }

    Write-Log "ORIGIN_MAIN=$originMain"
    Write-Log "CANONICAL_HEAD=$canonicalHead"

    if ($canonicalHead -ne $originMain) {
        throw "Canonical local main is not synchronized with origin/main. HEAD=$canonicalHead origin/main=$originMain"
    }

    $originTopic = (git rev-parse "origin/$TopicBranch").Trim()
    if ($LASTEXITCODE -ne 0) { throw "Cannot resolve origin/$TopicBranch" }
    Write-Log "ORIGIN_TOPIC_HEAD=$originTopic"

    if ($originTopic -ne $ExpectedTestHead) {
        throw "Topic branch drifted. Expected $ExpectedTestHead, actual $originTopic"
    }

    Write-Log ""
    Write-Log "=== create exact-head worktree ==="
    if (Test-Path -LiteralPath $verify) {
        throw "Verification worktree path already exists: $verify"
    }

    $worktreeExit = Invoke-LoggedNative "git worktree add --detach `"$verify`" $ExpectedTestHead 2>&1"
    Write-Log "WORKTREE_ADD_EXIT=$worktreeExit"
    if ($worktreeExit -ne 0) { throw "git worktree add failed with exit code $worktreeExit" }
    $worktreeAdded = $true

    Set-Location $verify
    $actualTestHead = (git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "git rev-parse HEAD failed in verification worktree" }
    Write-Log "ACTUAL_TEST_HEAD=$actualTestHead"
    if ($actualTestHead -ne $ExpectedTestHead) { throw "Verification HEAD mismatch" }

    Write-Log ""
    Write-Log "=== tests ==="
    $testExit = Invoke-LoggedNative "python -m unittest discover -s tests -v 2>&1"
    Write-Log "TEST_EXIT=$testExit"
    if ($testExit -ne 0) { throw "Full unittest regression failed with exit code $testExit" }

    Write-Log ""
    Write-Log "=== diff check ==="
    $diffExit = Invoke-LoggedNative "git diff --check origin/main...HEAD 2>&1"
    Write-Log "DIFF_EXIT=$diffExit"
    if ($diffExit -ne 0) { throw "git diff --check failed with exit code $diffExit" }

    $verifyStatus = @(git status --short --untracked-files=all)
    if ($LASTEXITCODE -ne 0) { throw "git status failed in verification worktree" }
    Write-Log "VERIFY_STATUS_BEGIN"
    if ($verifyStatus.Count -eq 0) { Write-Log "<clean>" }
    else { $verifyStatus | ForEach-Object { Write-Log $_ } }
    Write-Log "VERIFY_STATUS_END"
    if ($verifyStatus.Count -ne 0) { throw "Verification worktree became dirty" }

    Set-Location $repo
    Write-Log ""
    Write-Log "=== remove verification worktree ==="
    $removeExit = Invoke-LoggedNative "git worktree remove `"$verify`" 2>&1"
    Write-Log "WORKTREE_REMOVE_EXIT=$removeExit"
    if ($removeExit -ne 0) {
        throw "Normal verification worktree removal failed; no force removal attempted"
    }
    $worktreeAdded = $false
}
catch {
    $failure = $_.Exception.Message
    try {
        Write-Log ""
        Write-Log "=== primary failure ==="
        Write-Log "PRIMARY_FAILURE=$failure"
    }
    catch {}
}
finally {
    try {
        Set-Location $repo
    }
    catch {
        Add-Failure "Could not return to canonical repo: $($_.Exception.Message)"
    }

    try {
        Write-Log ""
        Write-Log "=== final canonical state ==="

        $finalLocation = (Get-Location).Path
        $finalBranch = (git branch --show-current).Trim()
        $branchExit = $LASTEXITCODE
        $finalHead = (git rev-parse HEAD).Trim()
        $headExit = $LASTEXITCODE
        $finalOriginMain = (git rev-parse origin/main).Trim()
        $originExit = $LASTEXITCODE
        $finalStatus = @(git status --short --untracked-files=all)
        $statusExit = $LASTEXITCODE

        Write-Log "FINAL_LOCATION=$finalLocation"
        Write-Log "FINAL_BRANCH=$finalBranch"
        Write-Log "FINAL_HEAD=$finalHead"
        Write-Log "FINAL_ORIGIN_MAIN=$finalOriginMain"
        Write-Log "FINAL_STATUS_BEGIN"
        if ($finalStatus.Count -eq 0) { Write-Log "<clean>" }
        else { $finalStatus | ForEach-Object { Write-Log $_ } }
        Write-Log "FINAL_STATUS_END"

        if ($finalLocation -ne $repo) { Add-Failure "Final working directory mismatch" }
        if ($branchExit -ne 0 -or $finalBranch -ne $expectedFinalBranch) { Add-Failure "Final branch mismatch" }
        if ($headExit -ne 0 -or $originExit -ne 0 -or $finalHead -ne $finalOriginMain) { Add-Failure "Final HEAD/origin mismatch" }

        if ($statusExit -ne 0) {
            Add-Failure "Final git status failed"
        }
        else {
            $unexpectedFinal = @($finalStatus | Where-Object {
                $_ -and $_ -ne "?? $logRelative"
            })
            if ($unexpectedFinal.Count -ne 0) {
                Add-Failure "Unexpected final status entries: $($unexpectedFinal -join ' | ')"
            }
        }

        if ($worktreeAdded) {
            Write-Log "VERIFY_WORKTREE_RETAINED_FOR_DIAGNOSIS=$verify"
        }

        if (-not (Test-Path -LiteralPath $log)) {
            Add-Failure "Durable verification log does not exist: $log"
        }
        else {
            $logInfo = Get-Item -LiteralPath $log
            Write-Log "LOG_EXISTS=1"
            Write-Log "LOG_SIZE_BYTES=$($logInfo.Length)"
            Write-Log "LOG_PATH=$log"
            if ($logInfo.Length -le 0) { Add-Failure "Durable verification log is empty" }
        }
    }
    catch {
        Add-Failure "Final verification failed: $($_.Exception.Message)"
    }

    if ($null -eq $failure) {
        Write-Log ""
        Write-Log "FINAL_RESULT=PASS"
        Write-Log "END_TIME=$(Get-Date -Format o)"
        Write-Host ""
        Write-Host "PASS"
        Write-Host "Final folder : $repo"
        Write-Host "Final branch : $expectedFinalBranch"
        Write-Host "Final HEAD   : $finalHead"
        Write-Host "Tested HEAD  : $ExpectedTestHead"
        Write-Host "Log          : $log"
    }
    else {
        try {
            Write-Log ""
            Write-Log "FINAL_RESULT=FAIL"
            Write-Log "FAIL_REASON=$failure"
            Write-Log "END_TIME=$(Get-Date -Format o)"
        }
        catch {}
        Write-Host ""
        Write-Host "FAILED"
        Write-Host "Reason : $failure"
        Write-Host "Folder : $repo"
        Write-Host "Log    : $log"
        throw $failure
    }
}
