# 원격 PC 설치 (처음부터)

24시간 켜져 있는 다른 PC에 설치하는 절차. **아무것도 깔려 있지 않은 상태**를 가정한다.

원격 PC의 핵심 제약은 하나다. **RDP 세션이 끊겨도 돌아야 한다.**
Windows 작업 스케줄러의 기본 설정은 "로그온했을 때만 실행"이라, 원격 접속을 끊으면
작업이 돌지 않는다. 이 문서는 그 문제를 해결하는 데 초점을 맞춘다.

---

## 0. 준비물

| | |
|---|---|
| GitHub 계정 접근 | `tehryung-ray/sector-swing-report` 에 push 권한 |
| 텔레그램 토큰 | 이미 만든 봇 토큰과 chat_id (기존 것 재사용) |
| Gemini 키 | 선택. 없으면 뉴스가 키워드 분류로 폴백 |
| 원격 PC 관리자 권한 | 작업 등록에 필요 |

---

## 1. Python 설치

[python.org](https://www.python.org/downloads/windows/) 에서 **3.12 이상** 설치.
설치 화면에서 **`Add python.exe to PATH` 를 반드시 체크**한다.

```powershell
python --version     # Python 3.12.x 이상
```

## 2. Git 설치

[git-scm.com](https://git-scm.com/download/win) 에서 설치. 기본 옵션으로 두면 된다
(Git Credential Manager 가 함께 깔린다 — 뒤에서 쓴다).

```powershell
git --version
```

## 3. 저장소 복제

설치 경로는 **`C:\apps\sector_invest`** 다. 영문 경로라 인코딩 문제가 없다.

```powershell
git clone https://github.com/tehryung-ray/sector-swing-report.git C:\apps\sector_invest
cd C:\apps\sector_invest
```

## 4. 패키지 설치

```powershell
cd C:\apps\sector_invest
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 5. git 신원 설정

```powershell
git config user.email "tehryungkim@gmail.com"
git config user.name  "tehryungkim"
```

## 6. push 자격증명 — 가장 중요한 단계

작업 스케줄러가 **비대화형 세션**에서 돌기 때문에, 여기서 방법 선택이 갈린다.

### 방법 A. Git Credential Manager (권장)

RDP 로 한 번 접속해 브라우저 인증을 통과시킨다. 자격증명은 Windows 자격증명 관리자에
**DPAPI 로 암호화**되어 저장되고, 같은 사용자로 실행되는 예약 작업에서도 쓸 수 있다.

```powershell
cd C:\apps\sector_invest
git push origin main        # 브라우저가 열리면 로그인
```

한 번 통과하면 이후로는 묻지 않는다.

> **주의**: 예약 작업을 **같은 사용자 계정**으로 등록해야 한다. `SYSTEM` 으로 등록하면
> 자격증명 관리자는 사용자별이라 접근하지 못하고 push 가 실패한다.

### 방법 B. Fine-grained PAT (브라우저를 못 쓸 때)

완전 헤드리스라면 토큰을 파일에 저장한다.

1. GitHub → Settings → Developer settings → **Personal access tokens → Fine-grained tokens**
2. **Repository access**: `sector-swing-report` **하나만** 선택
3. **Permissions**: `Contents` → **Read and write** (이것만)
4. 만료일 설정 (90일 권장)

```powershell
git config credential.helper store
git push origin main
# Username: tehryung-ray
# Password: <발급받은 PAT 붙여넣기>
```

`%USERPROFILE%\.git-credentials` 에 **평문으로** 저장된다. 사용자 프로필 폴더라
다른 사용자는 못 읽지만 암호화는 아니다. 그래서 A 를 먼저 시도하는 게 좋다.

> `Contents: write` 는 코드를 바꿀 수 있는 권한이다. 만료일을 꼭 걸고, 갱신 시점을
> 달력에 적어 둘 것. 만료되면 push 가 조용히 실패한다.

## 7. 토큰 파일

```powershell
Copy-Item ops\.env.example ops\.env
notepad ops\.env
```

```
GEMINI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### 보안 — 확인된 사실

| 확인 항목 | 결과 |
|---|---|
| `ops/.env` 가 `.gitignore` 로 무시되는가 | **예** |
| `git add -A` 에 걸리는가 | **아니오** |
| 과거에 커밋된 적 있는가 | **없음** |
| 커밋된 `.env.example` 에 값이 있는가 | 없음 (빈 템플릿) |
| 전송 실패 시 오류 메시지에 토큰이 실리는가 | **아니오** (`HTTP Error 401: Unauthorized` 만 남음) |
| `ops/logs/` 가 무시되는가 | 예 |

`.env` 뿐 아니라 **편집기가 만드는 사본까지** 막아 두었다.
`.env.bak`, `.env~`, `.env.txt`, `.env.save`, `env.txt` 가 모두 무시된다 —
메모장의 "다른 이름으로 저장"이 `.env.txt` 를 만들어 새는 경우를 방지한다.

`preflight.ps1` 8단계가 매번 유출을 점검한다. 추적 중이거나 커밋 대기 중인
토큰 파일이 있으면 `[실패]` 로 알린다. **토큰 파일을 편집한 뒤에는 한 번 돌려보면 좋다.**

> 만약 실수로 커밋해 push 했다면, 파일을 지우는 것만으로는 부족하다.
> **git 이력에 영구히 남으므로 토큰을 즉시 재발급**해야 한다
> (텔레그램은 @BotFather 에서 `/revoke`, Gemini 는 AI Studio 에서 키 삭제).

## 8. 사전 점검

```powershell
powershell -ExecutionPolicy Bypass -File ops\preflight.ps1
```

Python·Git·패키지·시간대·저장소·push 권한·외부 접근·토큰·유출 점검·작업 등록을 한 번에 확인한다.
**`[실패]` 가 하나도 없어야** 다음으로 넘어간다. `[주의]` 는 넘어가도 된다.

## 9. 손으로 한 번 실행

```powershell
powershell -ExecutionPolicy Bypass -File ops
un-daily.ps1
```

`=== 정상 종료 ===` 이 나와야 한다. 로그는 `ops\logs\daily-YYYY-MM-DD.log`.

## 10. 작업 스케줄러 등록

**관리자 PowerShell** 에서 실행한다. `$user` 는 이 PC 에서 6 번 자격증명을 설정한
계정이어야 한다.

```powershell
$repo = "C:\apps\sector_invest"
$ps   = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$user = "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

# 로그아웃 상태에서도 실행. 등록할 때 비밀번호를 한 번 묻는다.
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Password -RunLevel Limited

# 리포트 — 평일 06:50
Register-ScheduledTask -TaskName "SectorSwing-Daily" -Force `
  -Action    (New-ScheduledTaskAction -Execute $ps -WorkingDirectory $repo `
              -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\ops\run-daily.ps1`"") `
  -Trigger   (New-ScheduledTaskTrigger -Weekly `
              -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 06:50) `
  -Settings  $settings -Principal $principal

# 개장 점검 — 평일 09:10
Register-ScheduledTask -TaskName "SectorSwing-OpenBell" -Force `
  -Action    (New-ScheduledTaskAction -Execute $ps -WorkingDirectory $repo `
              -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\ops\run-openbell.ps1`"") `
  -Trigger   (New-ScheduledTaskTrigger -Weekly `
              -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 09:10) `
  -Settings  $settings -Principal $principal
```

`-LogonType Password` 가 **로그아웃 상태에서도 실행**되게 하는 부분이다.
등록할 때 계정 비밀번호를 묻는데, Windows 가 이를 암호화 보관한다.

> 비밀번호를 넣기 싫으면 `-LogonType S4U` 로 바꿀 수 있다. 비밀번호 없이 로그아웃
> 상태에서도 돌지만, **네트워크 자격증명에 접근하지 못해 push 가 실패할 수 있다.**
> 이 경우 6-B(PAT 파일 방식)를 쓰면 해결된다.

## 11. 즉시 실행해서 확인

```powershell
Start-ScheduledTask -TaskName "SectorSwing-Daily"
Start-Sleep -Seconds 90
Get-ScheduledTask -TaskName "SectorSwing-*" | Get-ScheduledTaskInfo |
  Format-Table TaskName,LastRunTime,LastTaskResult,NextRunTime -AutoSize
```

**`LastTaskResult` 가 `0`** 이면 성공이다. 0 이 아니면 `ops\logs\` 의 로그를 본다.

**진짜 검증은 로그아웃 후다.** RDP 를 끊고(로그아웃까지) 다시 실행해 본다:

```powershell
# RDP 재접속 후
Get-ScheduledTaskInfo -TaskName "SectorSwing-Daily" | Select LastRunTime,LastTaskResult
```

여기서 `0` 이 나오면 원격 PC 설정이 끝난 것이다.

---

## 12. 원격 PC 에서 꼭 챙길 것

**절전·최대 절전 끄기** — 꺼지면 아무것도 안 돈다.

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 10
```

**Windows Update 자동 재시작** — 새벽에 재부팅되면 그날은 놓친다.
설정 → Windows Update → 고급 옵션에서 **활성 시간**을 06:00~10:00 으로 지정해
그 시간대에 재시작하지 않게 한다.

**시간대 확인** — KST 가 아니면 스케줄 시각을 환산해야 한다.

```powershell
Get-TimeZone
Set-TimeZone -Id "Korea Standard Time"    # 필요하면
```

**PAT 만료** — 6-B 를 썼다면 만료일에 push 가 조용히 실패한다.
`preflight.ps1` 이 `push --dry-run` 으로 확인하니 가끔 돌려보면 된다.

---

## 13. 중복 걱정은 없다

GitHub Actions 와 이 PC 가 동시에 돌아도 문제가 없다. 여러 PC 에 걸어도 된다.

| | 먼저 도는 쪽 | 나중에 도는 쪽 |
|---|---|---|
| 리포트 | 생성·커밋·푸시 | `SKIP_IF_DONE` 으로 즉시 종료 |
| 개장 점검 | 알림 발송 + 기록 커밋 | 같은 내용이면 재발송 안 함 |

**GitHub 쪽을 끄지 말 것.** 이 PC 가 꺼지거나 인터넷이 끊긴 날의 보험이다.

---

## 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `LastTaskResult` 가 0 이 아니고 로그에 push 실패 | 비대화형 세션에서 자격증명 접근 실패 | 6-B(PAT 파일 방식)로 전환 |
| 로그온했을 때만 성공 | `LogonType` 이 `Interactive` | 10 번의 `-LogonType Password` 로 재등록 |
| 한글 주석 구문 오류 | `.ps1` 의 UTF-8 BOM 이 사라짐 | 편집기에서 `UTF-8 with BOM` 으로 저장 |
| `python` 을 못 찾음 | 작업이 PATH 없는 세션에서 실행 | 10 번 `-Execute` 를 `python.exe` 절대경로로 바꾸거나 PATH 를 시스템 변수에 추가 |
| 알림이 안 옴 | `ops\.env` 누락 또는 할 일이 없던 날 | 로그의 `시크릿 토큰` 줄 확인 |
| 리포트가 안 갱신됨 | 이미 다른 쪽이 만들었음 | 정상. 로그에 "변경 없음" 이 찍힌다 |
| `cd` 가 안 됨 | 경로 오타 | `C:\apps\sector_invest` (언더바, 하이픈 아님) |

---

## 부록. 한 번에 붙여넣기

Python 과 Git 을 설치한 뒤(1·2 단계), **일반 PowerShell** 에서 아래를 통째로 실행하면
3~5·8 단계가 끝난다.

```powershell
git clone https://github.com/tehryung-ray/sector-swing-report.git C:\apps\sector_invest
cd C:\apps\sector_invest
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
git config user.email "tehryungkim@gmail.com"
git config user.name  "tehryungkim"
Copy-Item ops\.env.example ops\.env
notepad ops\.env          # 토큰 채우고 저장
git push origin main      # 브라우저 인증 한 번 통과 (6-A)
powershell -ExecutionPolicy Bypass -File ops\preflight.ps1
```

`preflight.ps1` 에 `[실패]` 가 없으면, **관리자 PowerShell** 에서 작업을 등록한다.

```powershell
$repo = "C:\apps\sector_invest"
$ps   = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$user = "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -MultipleInstances IgnoreNew `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Password -RunLevel Limited
$days = @("Monday","Tuesday","Wednesday","Thursday","Friday")

Register-ScheduledTask -TaskName "SectorSwing-Daily" -Force -Settings $settings -Principal $principal `
  -Action  (New-ScheduledTaskAction -Execute $ps -WorkingDirectory $repo `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\ops\run-daily.ps1`"") `
  -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At 06:50)

Register-ScheduledTask -TaskName "SectorSwing-OpenBell" -Force -Settings $settings -Principal $principal `
  -Action  (New-ScheduledTaskAction -Execute $ps -WorkingDirectory $repo `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\ops\run-openbell.ps1`"") `
  -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At 09:10)

powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

Start-ScheduledTask -TaskName "SectorSwing-Daily"
Start-Sleep -Seconds 90
Get-ScheduledTask -TaskName "SectorSwing-*" | Get-ScheduledTaskInfo |
  Format-Table TaskName,LastRunTime,LastTaskResult,NextRunTime -AutoSize
```

`LastTaskResult` 가 **0** 이면 성공이다. 마지막으로 **RDP 를 끊고(로그오프) 재접속해**
같은 명령으로 다시 확인한다. 거기서도 0 이면 설정이 끝났다.
