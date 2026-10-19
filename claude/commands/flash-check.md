---
description: >-
  (Claude Code · ทุกโปรเจกต์) ตรวจงาน DeepSeek Flash จากหลักฐานในแผน (ไม่ build ซ้ำ) · /flash-check <แผน>. Triggers: deepseek ทำเสร็จแล้ว, ตรวจงาน flash
---
<!-- flashq:managed — ติดตั้งโดย `flashq.py install` (ต้นฉบับ {{FLASHQ}}/claude/commands/) -->

แผน: $ARGUMENTS · ว่าง → หา `PLAN_*FLASH*` ที่ §4 มีแถวยังไม่ตรวจ แล้วถาม user (AskUserQuestion)

**ขั้นแรก — โปรเจกต์มีคำสั่งของตัวเองไหม**: มีไฟล์ `.claude/commands/flash-check.md` หรือ `.opencode/command/flash-check.md` ในโปรเจกต์ (และไม่มีบรรทัด `flashq:managed`) → **อ่านไฟล์นั้นแล้วทำตามแทนไฟล์นี้ทั้งหมด**

คุณ = **ผู้ตรวจ** · **ห้ามเชื่อรายงานของ DeepSeek โดยไม่มีหลักฐาน** · ค่าโปรเจกต์จาก `.flash.json` (`main_branch`/`remote` ไม่ตั้ง = ตรวจจาก git: `git symbolic-ref --short refs/remotes/<remote>/HEAD` → `origin/main`/`origin/master` ที่มีจริง · โปรเจกต์ใหม่ให้รัน `flashq.py init`)

## 0. ผลจาก flashq
- `FLASH_RUN=OK` → ข้อ 1
- `QUOTA` (สลับบัญชีครบแล้ว) → หยุด บอก user · `NOSTART` (ลองใหม่แล้ว) → หยุด บอก user
- `BUSY` / `QUEUE_TIMEOUT` → มีงานอื่นในคิวกลาง ห้ามรันซ้อน บอก user (`python {{FLASHQ}}/flashq.py`)
- `FAIL` / `TIMEOUT` → อ่าน §4 ของแผน + ท้าย log (path ในบรรทัด `START … log=` · `python {{FLASHQ}}/flashq.py log <job>`) แล้วตรวจงานที่ทำเสร็จตามปกติ

## 1. รวบรวม
- อ่าน §0 + งานที่ระบุ + §4 (Grep → Read เฉพาะช่วง) → งานที่ผล ✅/🟡 แต่ช่อง "ตรวจ Claude" ว่าง
- ที่ checkout หลัก: `git log --oneline --no-merges <remote>/<main_branch>..<main_branch>` เทียบกับ hash ใน §4 · commit ที่ไม่ใช่ของแผนนี้ → แจ้ง user ห้ามแตะ

## 2. ตรวจทีละงาน
- `git show <hash> --stat` แตะเฉพาะไฟล์ของงาน? · `git show <hash>` ตรง "หลัง" ในแผน? ไม่มีส่วนเกิน/encoding เพี้ยน?
- ตรวจ flow รอบจุดแก้ (caller/ข้อมูล) ไม่เพี้ยน · ใช้ skill รีวิวของโปรเจกต์ถ้ามี
- งาน ⛔/🟡: ตัดสินว่าแผนผิด (แก้แผน) หรือ Flash ทำผิด

## 3. ยืนยันจาก "หลักฐานชี้ขาด" — **ห้าม build/รันเทสต์ซ้ำเอง**
- อ่าน path ที่ DeepSeek จดใน §4 → บรรทัด/ค่าตรงกับแผน และเป็นค่าหลังแก้?
- เวลาไฟล์ log ใหม่กว่า commit แก้โค้ด (`git log -1 --format=%ci <hash>`)
- ขาด/ไม่ตรง/เก่ากว่า → `❌ หลักฐานไม่ครบ → T-xxR` (ไม่รันเอง)

## 4. บันทึก + ปิด
- เติมช่อง "ตรวจ Claude" ใน §4: `✅ผ่าน` หรือ `❌ <เหตุผล> → T-xxR` · ไม่ผ่าน → เพิ่ม `T-xxR` (ก่อน/หลัง/ยืนยัน ตรงตัว) · **ห้าม revert/reset เอง**
- **วนอัตโนมัติ**: commit+push แผน → `python {{FLASHQ}}/flashq.py run <แผน> <T-xxR...> --switch-on-quota 4` ใน background → จบแล้ว `/flash-check` ซ้ำ · **สูงสุด 2 รอบต่อแผน** แล้วยังไม่ผ่าน = หยุด รายงาน
- ผ่านทั้งชุด → ที่ checkout หลัก: `git fetch <remote> <main_branch>` → แยกทาง = `git merge --no-edit <remote>/<main_branch>` (**ห้าม rebase**) → `git push <remote> <main_branch>` · มีไฟล์ค้างของ session อื่นชน → หยุด รายงาน user
- สรุปให้ user: ผ่าน/ไม่ผ่านกี่งาน · รอบแก้ที่ส่งไปแล้ว

## 5. 1 แผน = 1 session
- จบแผนแล้ว **ห้ามต่อเรื่องใหม่เองใน session นี้** · มีคิวงานที่ user สั่งไว้ → ถาม user: เปิด session ใหม่ด้วย `/flash-plan <เรื่องถัดไป>` (แนะนำ) / ต่อที่นี่ / หยุดก่อน
