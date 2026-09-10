# 리포트 생성 + 푸시. GitHub 크론이 지연·누락될 때의 이중화다.
#   powershell -ExecutionPolicy Bypass -File ops\run-daily.ps1
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
$log = Join-Path $logDir ("daily-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

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

Say "=== 리포트 생성 시작 ==="
LoadEnv $false | Out-Null

Say "원격 동기화"
if ((Run "git" @("pull","--rebase","--autostash","origin","main")) -ne 0) {
  Say "!! git pull 실패"; exit 1
}

# GitHub Actions 가 이미 오늘 리포트를 만들었으면 다시 만들지 않는다.
# 없거나 신선도가 나쁘면 새로 만든다.
$env:SKIP_IF_DONE = "1"
Say "파이프라인 실행"
if ((Run "python" @("-m","pipeline.main")) -ne 0) {
  Say "!! pipeline.main 실패"; exit 1
}

& git add docs/data | Out-Null
& git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
  Say "변경 없음 - 커밋 생략 (이미 생성됐거나 휴장일)"
  Say "=== 정상 종료 ==="
  exit 0
}

$d = Get-Date -Format "yyyy-MM-dd"
if ((Run "git" @("commit","-q","-m","report: $d (local)")) -ne 0) { Say "!! commit 실패"; exit 1 }
Run "git" @("pull","--rebase","--autostash","origin","main") | Out-Null
if ((Run "git" @("push","-q","origin","main")) -ne 0) { Say "!! push 실패"; exit 1 }
Say "푸시 완료"
Say "=== 정상 종료 ==="
exit 0
