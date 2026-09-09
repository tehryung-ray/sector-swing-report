# 원격 PC 설치 전/후 점검. 무엇이 빠졌는지 알려준다.
#   powershell -ExecutionPolicy Bypass -File ops\preflight.ps1
#
# 이 파일은 UTF-8 BOM 으로 저장해야 한다(PowerShell 5.1 이 ANSI 로 읽어 한글이 깨진다).

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$fail = 0
$warn = 0

function OK($m)   { Write-Host "  [OK]   $m" }
function BAD($m)  { Write-Host "  [실패] $m"; $script:fail++ }
function WARN($m) { Write-Host "  [주의] $m"; $script:warn++ }

Write-Host ""
Write-Host "=== 1. 필수 프로그램 ==="
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) {
  $v = (& python --version 2>&1) -replace 'Python\s*',''
  $parts = $v.Split('.')
  if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 12) { OK "Python $v" }
  else { BAD "Python $v — 3.12 이상이 필요하다" }
} else { BAD "Python 없음 — python.org 에서 설치하고 PATH 에 추가할 것" }

if (Get-Command git -ErrorAction SilentlyContinue) {
  OK ("Git " + ((& git --version) -replace 'git version ',''))
} else { BAD "Git 없음 — git-scm.com 에서 설치" }

Write-Host ""
Write-Host "=== 2. 파이썬 패키지 ==="
$need = @("pandas","numpy","yaml","pyarrow","yfinance","FinanceDataReader","exchange_calendars")
$missing = @()
foreach ($m in $need) {
  & python -c "import $m" 2>$null
  if ($LASTEXITCODE -ne 0) { $missing += $m }
}
if ($missing.Count -eq 0) { OK "필요한 패키지 모두 설치됨" }
else { BAD ("누락: " + ($missing -join ", ") + "  ->  pip install -r requirements.txt") }

Write-Host ""
Write-Host "=== 3. 시간대 ==="
$tz = (Get-TimeZone).Id
$off = [int]([TimeZoneInfo]::Local.BaseUtcOffset.TotalHours)
if ($off -eq 9) { OK "$tz (UTC+9) — 스케줄 시각을 그대로 쓰면 된다" }
else { WARN "$tz (UTC$('{0:+#;-#;+0}' -f $off)) — KST 가 아니다. 06:50/09:10 을 현지 시각으로 환산해 걸 것" }

Write-Host ""
Write-Host "=== 4. 저장소 ==="
& git rev-parse --is-inside-work-tree 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { BAD "git 저장소가 아니다" }
else {
  OK ("브랜치 " + (& git rev-parse --abbrev-ref HEAD))
  $em = & git config user.email
  $nm = & git config user.name
  if ($em -and $nm) { OK "커밋 신원 $nm <$em>" }
  else { BAD "git config user.email / user.name 미설정" }
  if ($repo -match '[^\x00-\x7F]') { WARN "경로에 한글이 있다: $repo  (가능하면 C:\sector-swing 처럼 영문 경로 권장)" }
  else { OK "경로 $repo" }
}

Write-Host ""
Write-Host "=== 5. 원격 접근 (읽기/쓰기) ==="
& git ls-remote origin HEAD 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { OK "원격 읽기 가능" } else { BAD "원격 읽기 실패 — 네트워크 또는 자격증명 문제" }
& git push --dry-run origin HEAD 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { OK "원격 쓰기 가능 (push --dry-run 통과)" }
else { BAD "push 권한 없음 — 자격증명을 먼저 설정할 것 (아래 안내 참고)" }

Write-Host ""
Write-Host "=== 6. 외부 데이터 접근 ==="
foreach ($h in @("finance.naver.com","query1.finance.yahoo.com","news.google.com","api.telegram.org")) {
  try {
    $r = Invoke-WebRequest -Uri "https://$h" -Method Head -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
    OK "$h ($($r.StatusCode))"
  } catch {
    if ($_.Exception.Response) { OK "$h (응답 있음)" } else { BAD "$h 접근 불가" }
  }
}

Write-Host ""
Write-Host "=== 7. 토큰 파일 ==="
$envFile = Join-Path $repo "ops\.env"
if (-not (Test-Path $envFile)) {
  WARN "ops\.env 없음 — 리포트는 되지만 텔레그램 알림과 AI 뉴스 분류가 빠진다"
} else {
  $txt = Get-Content $envFile -Raw -Encoding utf8
  foreach ($k in @("TELEGRAM_BOT_TOKEN","TELEGRAM_CHAT_ID")) {
    if ($txt -match "$k\s*=\s*\S+") { OK "$k 설정됨" } else { WARN "$k 비어 있음 — 알림이 안 간다" }
  }
  if ($txt -match "GEMINI_API_KEY\s*=\s*\S+") { OK "GEMINI_API_KEY 설정됨" }
  else { WARN "GEMINI_API_KEY 비어 있음 — 뉴스가 키워드 분류로 폴백(리포트는 정상)" }
}

Write-Host ""
Write-Host "=== 8. 등록된 작업 ==="
$tasks = Get-ScheduledTask -TaskName "SectorSwing-*" -ErrorAction SilentlyContinue
if (-not $tasks) { WARN "SectorSwing-* 작업이 없다 — 아직 등록하지 않았다" }
else {
  foreach ($t in $tasks) {
    $i = $t | Get-ScheduledTaskInfo
    $r = if ($i.LastTaskResult -eq 0) { "성공" } elseif ($null -eq $i.LastRunTime) { "미실행" } else { "실패($($i.LastTaskResult))" }
    $logon = $t.Principal.LogonType
    $note = if ($logon -eq "Password" -or $logon -eq "S4U") { "" } else { "  <- 로그아웃 시 안 돌 수 있다" }
    OK "$($t.TaskName): 지난 실행 $r / 다음 $($i.NextRunTime) / LogonType=$logon$note"
  }
}

Write-Host ""
Write-Host ("=" * 60)
if ($fail -gt 0) { Write-Host "실패 $fail 건, 주의 $warn 건 — 실패를 먼저 해결할 것"; exit 1 }
Write-Host "실패 없음 (주의 $warn 건)"
exit 0
