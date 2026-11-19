# คู่มือติดตั้ง flashq แบบ exe (ชุดแจกจ่าย)

> สำหรับผู้ที่ได้รับโฟลเดอร์ `dist\` ของ flashq — **ไม่ต้องมี Python และไม่ต้อง clone repo**
> คู่มือการใช้งานเต็ม → `README.md` ในชุดเดียวกัน · คนที่แก้โค้ด flashq เอง → [AGENTS.md](../AGENTS.md)

## 1. ในชุดแจกมีอะไร

| ไฟล์/โฟลเดอร์ | หน้าที่ |
|---|---|
| `flashq-gui.exe` | **ดับเบิลคลิก = เปิดหน้าต่างแอป** (dashboard: คิวงาน ออฟฟิศ ประวัติ ค่าใช้จ่าย) ไม่ใช้เบราว์เซอร์ |
| `flashq.exe` | แบบ console สำหรับพิมพ์คำสั่ง (`install` `status` `run` `models` `init` ...) และเป็นตัวที่คำสั่ง/hook ที่ติดตั้งเรียกใช้ |
| `claude\` `opencode\` `hooks\` `templates\` `oc_desktop_open.mjs` | ต้นฉบับคำสั่ง `/flash-*` ที่ `install` / `init` คัดลอกไปใช้ — **ต้องวางข้าง exe เสมอ ห้ามลบ ห้ามเปลี่ยนชื่อ** |
| `accounts.json` | รายการบัญชีโมเดลตั้งต้น (แก้ได้ ใช้ก่อนค่าที่ฝังในตัว exe) |
| `README.md` `CHANGELOG.md` | คู่มือเต็ม และรายการสิ่งที่เปลี่ยน |

## 2. สิ่งที่ต้องมีในเครื่อง

| รายการ | จำเป็นไหม | หมายเหตุ |
|---|---|---|
| Windows 10 / 11 | จำเป็น | ตัวเฝ้า shell, toast และ launcher พัฒนาบน Windows |
| WebView2 Runtime | จำเป็นสำหรับ `flashq-gui.exe` | Windows 11 มีมาให้แล้ว · Windows 10 เก่า → ติดตั้ง "Evergreen Runtime" จาก Microsoft |
| [opencode](https://opencode.ai) | จำเป็นถ้าจะส่งงานให้โมเดลทำ | ต้องอยู่ใน PATH และตั้ง provider/โมเดลไว้แล้ว (flashq สั่งโมเดลผ่าน opencode) |
| Git | จำเป็นถ้าจะส่งงาน | flashq ตรวจงานจาก commit/diff จริง |
| [Claude Code](https://claude.com/claude-code) | ไม่บังคับ | ใช้ถ้าจะสั่งงานด้วย `/flash-plan` `/flash-check` ฯลฯ |
| Node.js | ไม่บังคับ | ใช้กับปุ่ม "เปิด session ใน opencode desktop" |
| Python 3 | ไม่ต้องมี (ยกเว้นถ้าจะใช้ `--hooks`) | hook ของ Claude Code เป็นสคริปต์ `.py` ที่ `settings.json` สั่ง `python <hook>.py` — ไม่มี Python ก็ข้าม `--hooks` ได้ คำสั่ง `/flash-*` และหน้าต่างแอปทำงานปกติ |

ตรวจเร็ว ๆ ใน PowerShell: `opencode --version` · `git --version` · `claude --version`

## 3. ติดตั้ง (ทำครั้งเดียวต่อเครื่อง)

### 3.1 วางโฟลเดอร์ในที่ถาวร
คัดลอกโฟลเดอร์ชุดแจกไปไว้ที่ที่จะไม่ย้ายอีก เช่น `C:\Tools\flashq\` (path ที่ไม่มีช่องว่างจะเรียบร้อยที่สุด แต่มีช่องว่างก็ใช้ได้)

> ⚠ path ของ `flashq.exe` ถูกเขียนลงในคำสั่งที่ติดตั้งแล้ว — **ย้ายโฟลเดอร์ภายหลัง = ต้องรัน `install` ใหม่**

### 3.2 ปลดบล็อกไฟล์ (ถ้าได้ไฟล์มาจากอินเทอร์เน็ตหรืออีเมล)
คลิกขวา `flashq.exe` และ `flashq-gui.exe` → Properties → ติ๊ก **Unblock** → OK
หรือใน PowerShell: `Get-ChildItem C:\Tools\flashq -Recurse | Unblock-File`

### 3.3 ติดตั้งคำสั่ง `/flash-*`
เปิด PowerShell ในโฟลเดอร์นั้น:

```powershell
cd C:\Tools\flashq
.\flashq.exe install            # ไม่มี Python / ไม่อยากแก้ settings.json
.\flashq.exe install --hooks    # มี Python 3 และใช้ Claude Code → ลง hook ด้วย (แนะนำ)
```

สิ่งที่เกิดขึ้น:
- คัดลอก `/flash` `/flash-queue` `/flash-switch` และ agent ของ flashq ไปที่ `~\.config\opencode\command\` และ `agent\`
- คัดลอก `/flash-plan` `/flash-check` `/flash-goal` ฯลฯ และ agent `flash-checker` ไปที่ `~\.claude\commands\` และ `agents\`
- `--hooks` (ไม่บังคับ **และต้องมี Python 3 ใน PATH**) ลงทะเบียน hook ใน `~\.claude\settings.json`: ยามรูปภาพใหญ่ · ตัวแจ้งผลงานจบเข้า Claude · ยามเฝ้าคำสั่ง shell · ยามมอบงานสืบ · แจ้งของใหม่ — ถ้าไม่มี Python หรือไม่อยากให้แตะ `settings.json` ให้รันแบบไม่ใส่ `--hooks`
- ถามให้เลือกโมเดลของแต่ละบทบาท (ผู้ทำ/ผู้ตรวจ/ผู้สืบ/นักทดสอบ/ช่างเอกสาร) — ข้ามได้ด้วย `--models skip`

ไฟล์ของคุณเองที่ชื่อซ้ำจะ **ไม่ถูกทับ** (ใช้ `--force` ถ้าต้องการทับ · จะสำรองเป็น `.bak-flashq` ก่อน)

ถ้าไม่ใช้ Claude Code ก็รันได้เหมือนเดิม — ไฟล์ฝั่ง Claude จะถูกวางไว้เฉย ๆ ไม่มีผล

### 3.4 เลือกโมเดล
`accounts.json` ตั้งต้นเป็นชื่อ provider ของผู้จัดทำ **เครื่องคุณอาจไม่มี** ให้เลือกใหม่จากที่เครื่องคุณมีจริง:

```powershell
.\flashq.exe models --list                 # ดูโมเดลทั้งหมด + สถานะ "ใช้ได้"
.\flashq.exe models --auto                 # ให้ระบบเลือกตัวแนะนำให้บทบาทที่ยังไม่ตั้ง
.\flashq.exe models --all <provider>/<model>   # หรือตั้งทุกบทบาทเป็นโมเดลเดียว
```

provider ต้องมีใน `~\.config\opencode\opencode.json` ของเครื่องคุณ (เพิ่มผ่าน opencode ก่อน)

### 3.5 ตรวจผลการติดตั้ง
```powershell
.\flashq.exe install --check
```
ต้องได้ `INSTALL=OK  ตรงต้นฉบับครบ 30 ไฟล์` (ถ้าขึ้น `INSTALL=FAIL ไม่พบโฟลเดอร์ต้นฉบับ` = แตกไฟล์ไม่ครบ — ต้องมีโฟลเดอร์ `claude/ opencode/ hooks/ templates/` อยู่ข้าง exe) → จากนั้น **เปิด session ใหม่ของ Claude Code / รีโหลด opencode** จึงจะเห็นคำสั่ง `/flash-*`

## 4. ใช้งาน

### 4.1 เปิดหน้าต่างแอป
ดับเบิลคลิก `flashq-gui.exe` (สร้าง shortcut ไปวางบน Desktop/Start ได้) — ปิดหน้าต่าง = ปิดโปรแกรม
ข้อมูลของแต่ละคนอยู่ที่ `%USERPROFILE%\.flashq\` สร้างเองตอนเปิดครั้งแรก (ไม่อยู่ในโฟลเดอร์ชุดแจก)

### 4.2 ตั้งค่าโปรเจกต์ (ทำต่อโปรเจกต์)
```powershell
cd <โฟลเดอร์โปรเจกต์ที่เป็น git repo>
C:\Tools\flashq\flashq.exe init --install
```
สร้าง `.flash.json` · เพิ่ม `.tmp/` ใน `.gitignore` · คัดลอกแม่แบบแผน — แล้วค่อย commit ไฟล์เหล่านี้เอง
(`--commit` จะ commit และ push ให้เลย ใช้เมื่อมั่นใจเท่านั้น) · หรือพิมพ์ `/flash-init` ใน Claude Code ที่โปรเจกต์นั้น

### 4.3 ทดสอบการเชื่อมต่อ
```powershell
.\flashq.exe run --message "ตอบแค่คำว่า PONG" --project <โฟลเดอร์โปรเจกต์>
.\flashq.exe status
```

### 4.4 ส่งงานจริง
- ใน Claude Code: `/flash-plan <งานที่ต้องการ>` แล้วรอระบบแจ้งผล → `/flash-check` ตรวจผล
- ใน opencode: `/flash` · ดูคิว `/flash-queue` · สลับบัญชี `/flash-switch`
- ผ่านคำสั่งตรง: `.\flashq.exe run <แผน.md> T-01..T-03`

## 5. อัปเดตเวอร์ชัน
1. ปิด `flashq-gui.exe` และงานที่กำลังรัน
2. คัดลอกชุดใหม่ทับโฟลเดอร์เดิม (path เดิม)
3. รัน `.\flashq.exe install --check` → ถ้าขึ้น `INSTALL=STALE` ให้รัน `.\flashq.exe install` อีกครั้ง → เปิด session ใหม่
ข้อมูลใน `~\.flashq\` ไม่หาย

## 6. ถอนการติดตั้ง
1. ลบโฟลเดอร์ชุดแจก
2. ลบไฟล์ `flash-*.md` ใน `~\.claude\commands\` `~\.claude\agents\` `~\.config\opencode\command\` `agent\` และ hook `image_guard.py` `inbox_notify.py` `run_guard.py` `delegate_guard.py` `whatsnew.py` ใน `~\.claude\hooks\` (ที่มีบรรทัด `flashq:managed`)
3. ถ้าเคยใช้ `--hooks`: เปิด `~\.claude\settings.json` ลบรายการ hook ที่ชี้ไป flashq
4. (ไม่บังคับ) ลบ `%USERPROFILE%\.flashq\` — ประวัติงานและค่าตั้งค่าทั้งหมดจะหาย

## 7. แก้ปัญหา

| อาการ | สาเหตุ / วิธีแก้ |
|---|---|
| Windows SmartScreen ขึ้น "Windows protected your PC" | ไฟล์ยังไม่ได้เซ็นรับรอง → More info → Run anyway (หรือ Unblock ตามข้อ 3.2) |
| Defender/antivirus ลบหรือบล็อก exe | exe ที่สร้างจาก PyInstaller/Nuitka โดนแจ้งผิดบ่อย → เพิ่มโฟลเดอร์ชุดแจกใน exclusion · แจ้งผู้จัดทำให้เซ็นไฟล์ |
| `flashq-gui.exe` เปิดแล้วจอขาว/ไม่ขึ้น | ไม่มี WebView2 Runtime → ติดตั้งจาก Microsoft แล้วเปิดใหม่ |
| หน้าต่างขึ้น "This page is having a problem" (`RESULT_CODE_KILLED`) | ตัวเรนเดอร์ของหน้าต่างถูกปิด (หรือ exe ถูกฆ่าไปแล้ว) → ปิดหน้าต่างแล้วเปิด `flashq-gui.exe` ใหม่ |
| พิมพ์ `/flash-plan` แล้วไม่เจอคำสั่ง | ยังไม่ได้ `install` หรือยังไม่เปิด session ใหม่ → ตรวจด้วย `install --check` |
| `FAIL: ... opencode` / ส่งงานไม่ได้ | opencode ไม่อยู่ใน PATH หรือ provider ไม่มี → `opencode --version` · `flashq.exe models --list` |
| คำสั่งที่ติดตั้งชี้ path เก่า (ย้ายโฟลเดอร์แล้ว) | รัน `flashq.exe install` ใหม่จาก path ปัจจุบัน |
| `INSTALL=STALE` | ต้นฉบับใหม่กว่าที่ติดตั้ง → `flashq.exe install` |
| ข้อความไทยเพี้ยนใน PowerShell | `chcp 65001` ก่อนรัน หรือใช้ Windows Terminal |
| พอร์ตชน (เปิดหน้าต่างไม่ได้) | ปิดโปรแกรมที่ใช้พอร์ตนั้น หรือ `flashq-gui.exe` ตัวเก่ายังค้างอยู่ใน Task Manager |

## 8. ความปลอดภัยโดยสรุป
- หน้าต่างแอปเปิดเซิร์ฟเวอร์ในเครื่องที่ `127.0.0.1` เท่านั้น (ไม่รับการเชื่อมต่อจากเครื่องอื่น) และทุกปุ่มที่เปลี่ยนสถานะตรวจ token
- `install` แก้เฉพาะไฟล์ที่ flashq สร้าง (มีบรรทัด `flashq:managed`) — ไฟล์ของคุณเองไม่ถูกทับถ้าไม่ใส่ `--force`
- flashq ไม่ส่งข้อมูลออกอินเทอร์เน็ตเอง การเรียกโมเดลทั้งหมดผ่าน opencode ตามที่คุณตั้งไว้
