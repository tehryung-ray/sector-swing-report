# 개장 점검 + 텔레그램 알림. 09:10 에 호출한다.
#   powershell -ExecutionPolicy Bypass -File ops\run-openbell.ps1
#
# PowerShell 5.1 주의사항이 두 가지 있다.
#  1) 이 파일은 UTF-8 BOM 으로 저장해야 한다. BOM 이 없으면 ANSI 로 읽어 한글이 깨지고
#     구문 오류가 난다. (tools/fix-bom.py 로 다시 붙일 수 있다)
#  2) ErrorActionPreference = "Stop" 을 쓰면 git 이 stderr 에 쓰는 진행 메시지가
#     종료 오류로 잡힌다. 그래서 쓰지 않고 종료 코드를 직접 확인한다.

# 파이썬은 UTF-8 로 출력하는데 PowerShell 5.1 은 기본적으로 시스템 ANSI 코드페이지로
# 읽는다. 그대로 두면 한글 로그가 전부 깨져 원격 PC 에서 진단이 불가능해진다.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$logDir = Join-Path $repo "ops\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("openbell-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

function Say($m) {
  $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m
  Write-Host $line
  Add-Content -Path $log -Value $line -Encoding utf8
}

function Run($file, $arguments) {
  # 네이티브 명령을 돌리고 출력을 로그로 넘긴다. 반환값은 종료 코드뿐이어야 하므로
  # Say 는 Write-Host 를 쓴다(Write-Output 이면 반환값에 섞인다).
  Say ("  > " + $file + " " + ($arguments -join " "))
  & $file @arguments | ForEach-Object { Say "    $_" }
  return $LASTEXITCODE
}

function LoadEnv($required) {
  $f = Join-Path $repo "ops\.env"
  if (-not (Test-Path $f)) {
    if ($required) { Say "!! ops\.env 가 없습니다"; return $false }
    return $true
  }
  Get-Content $f -Encoding utf8 | ForEach-Object {
    if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') {
      [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), "Process")
    }
  }
  Say "ops\.env 로드됨"
  return $true
}

Say "=== 개장 점검 시작 ==="
if (-not (LoadEnv $true)) { Say "텔레그램 토큰이 필요합니다"; exit 1 }

Say "원격 동기화 (오늘 리포트와 발송 기록을 받아온다)"
Run "git" @("pull","--rebase","--autostash","origin","main") | Out-Null

$rc = Run "python" @("-m","pipeline.check_open")

# 발송했으면 기록을 올려 GitHub 쪽 실행이 중복 발송하지 않게 한다
& git add docs/data/openbell.json 2>$null | Out-Null
& git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  $d = Get-Date -Format "yyyy-MM-dd"
  Run "git" @("commit","-q","-m","openbell: $d 발송 기록 (local)") | Out-Null
  Run "git" @("pull","--rebase","--autostash","origin","main") | Out-Null
  Run "git" @("push","-q","origin","main") | Out-Null
  Say "발송 기록 푸시"
}
Say "=== 종료 (exit $rc) ==="
exit $rc
