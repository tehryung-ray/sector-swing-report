# 로컬 실행 (GitHub 크론 이중화)

GitHub Actions 크론은 신뢰할 수 없다. 2026-09-09 실측으로 리포트 06:50 예정이 **누락**됐고,
개장 점검 09:10 예정이 **13:35(+266분)** 에 돌았다. GitHub 공식 문서도
"부하가 높으면 일부 대기 작업이 버려질 수 있다"고 명시하며, **유료 플랜으로도 해결되지 않는다.**

여기 스크립트는 그 이중화다. **GitHub 쪽을 끄지 않는다.** 둘 중 먼저 도는 쪽이 일을 하고,
늦게 도는 쪽은 스스로 빠진다.

| | 먼저 돌면 | 나중에 돌면 |
|---|---|---|
| 리포트 | 생성·커밋·푸시 | `SKIP_IF_DONE` 으로 즉시 종료 |
| 개장 점검 | 알림 발송 + 기록 커밋 | 같은 내용이면 재발송 안 함 |

---

## 준비 (한 번만)

### 1. 토큰 파일

```powershell
Copy-Item ops\.env.example ops\.env
notepad ops\.env
```

```
GEMINI_API_KEY=...        # 없으면 뉴스가 키워드 분류로 폴백. 리포트는 정상 생성됨
TELEGRAM_BOT_TOKEN=...    # 개장 점검 알림에 필요
TELEGRAM_CHAT_ID=...
```

`ops/.env` 는 `.gitignore` 에 있어 커밋되지 않는다. **절대 커밋하지 말 것.**

### 2. 동작 확인

```powershell
powershell -ExecutionPolicy Bypass -File ops\run-daily.ps1
powershell -ExecutionPolicy Bypass -File ops\run-openbell.ps1
```

둘 다 `=== 정상 종료 ===` 와 `EXIT=0` 이 나와야 한다.
로그는 `ops/logs/daily-YYYY-MM-DD.log` 에 쌓인다.

### 3. 작업 스케줄러 등록

관리자 PowerShell에서:

```powershell
$repo = "D:\문서\현제연\표선희\sector_invest"
$ps   = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

# 리포트 — 평일 06:50
$a1 = New-ScheduledTaskAction -Execute $ps `
      -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\ops\run-daily.ps1`""
$t1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 06:50
# 절전에서 깨우고, 놓쳤으면 최대한 빨리 실행
$s  = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
      -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
      -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
Register-ScheduledTask -TaskName "SectorSwing-Daily" -Action $a1 -Trigger $t1 -Settings $s -Force

# 개장 점검 — 평일 09:10
$a2 = New-ScheduledTaskAction -Execute $ps `
      -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\ops\run-openbell.ps1`""
$t2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 09:10
Register-ScheduledTask -TaskName "SectorSwing-OpenBell" -Action $a2 -Trigger $t2 -Settings $s -Force
```

확인·수동 실행:

```powershell
Get-ScheduledTask -TaskName "SectorSwing-*" | Get-ScheduledTaskInfo | Format-Table TaskName,LastRunTime,LastTaskResult,NextRunTime
Start-ScheduledTask -TaskName "SectorSwing-Daily"
```

`LastTaskResult` 가 **0** 이면 성공이다.

---

## 다른 PC에 설치

**처음부터 설치하는 상세 절차는 [SETUP-REMOTE.md](SETUP-REMOTE.md) 를 보라.**
원격 PC는 RDP 세션이 끊겨도 돌아야 하므로 자격증명과 LogonType 설정이 핵심이다.

간단 요약:

24시간 켜진 PC가 여러 대면 **여러 대에 걸어도 된다.** 중복 방지가 이미 있어서
먼저 도는 쪽이 이기고 나머지는 빠진다. 오히려 한 대가 꺼져도 다른 대가 덮어주므로 더 안전하다.

```powershell
git clone https://github.com/tehryung-ray/sector-swing-report.git
cd sector-swing-report
pip install -r requirements.txt
Copy-Item ops\.env.example ops\.env    # 값 채우기
powershell -ExecutionPolicy Bypass -File ops\run-daily.ps1   # 동작 확인
```

**필요한 것**

| | |
|---|---|
| Python | 3.12 이상 |
| Git | 푸시 권한이 있는 자격증명이 설정돼 있어야 함 |
| 시간대 | **한국 시간(KST)** 이어야 한다. 다르면 스케줄 시각을 환산해 걸 것 |
| 네트워크 | 네이버 금융·Yahoo·구글뉴스·GitHub·텔레그램 접근 |

**첫 푸시 전에 자격증명을 확인**한다. 안 되어 있으면 스크립트가 push 단계에서 실패한다:

```powershell
git config user.email "본인메일"
git config user.name  "본인이름"
git push origin main     # 브라우저 인증이 뜨면 한 번 통과시켜 둔다
```

시간대 확인:

```powershell
powershell -ExecutionPolicy Bypass -File ops\preflight.ps1
```

`preflight.ps1` 이 Python·Git·패키지·시간대·저장소·push 권한·외부 접근·토큰·작업 등록을
한 번에 점검한다. `[실패]` 가 없어야 설치가 끝난 것이다.

---

## 알아둘 것

- **PC가 꺼져 있으면 안 돈다.** `-WakeToRun` 은 절전에서만 깨우고 완전 종료 상태에서는 못 깨운다.
  그래서 GitHub 크론을 백업으로 남겨둔다.
- **스크립트는 UTF-8 BOM 으로 저장돼 있다.** PowerShell 5.1 은 BOM 이 없으면 ANSI 로 읽어
  한글 주석이 깨지고 구문 오류가 난다. 편집기에서 저장할 때 인코딩을 바꾸지 말 것.
- **`ErrorActionPreference = "Stop"` 을 넣지 말 것.** git 이 stderr 에 쓰는 진행 메시지가
  종료 오류로 잡혀 정상 실행이 실패한다. 스크립트는 종료 코드를 직접 확인하는 방식이다.
- 로그는 날짜별로 쌓이고 자동 삭제되지 않는다. 가끔 `ops/logs` 를 비워도 된다.
