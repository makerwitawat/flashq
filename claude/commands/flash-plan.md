---
description: >-
  (Claude Code · ทุกโปรเจกต์) วางแผนให้ DeepSeek Flash ทำ (ยืนยันจุดแก้ → แผน T-xx → ส่งเข้าคิวกลาง flashq) · /flash-plan <งาน>. Triggers: ให้ deepseek ทำ, ส่งงานให้ deepseek, ส่งงานให้ flash
---
<!-- flashq:managed — ติดตั้งโดย `flashq.py install` (ต้นฉบับ {{FLASHQ}}/claude/commands/) -->

งาน: $ARGUMENTS · ว่าง → ถาม user (AskUserQuestion)

**ขั้นแรก — โปรเจกต์มีคำสั่งของตัวเองไหม**: มีไฟล์ `.claude/commands/flash-plan.md` หรือ `.opencode/command/flash-plan.md` ในโปรเจกต์ (และไม่มีบรรทัด `flashq:managed`) → **อ่านไฟล์นั้นแล้วทำตามแทนไฟล์นี้ทั้งหมด** (เช่น IRIS_CODE_1.2)

คุณ = **ผู้วางแผน** · DeepSeek Flash จะทำตามแผนแบบไม่คิดเอง → **ทุกข้อในแผนต้องถูกจุดและพิสูจน์แล้ว** · ห้ามแก้โค้ดเองในคำสั่งนี้

## 0. ค่าโปรเจกต์
- อ่าน `.flash.json` ที่รากโปรเจกต์ (ถ้ามี): `main_branch` (ค่าเริ่มต้น `master`) · `remote` (`origin`) · `plan_dir` (`docs/plans`) · `rules`
- อ่าน `AGENTS.md`/`CLAUDE.md` ของโปรเจกต์ → กติกา build/test/commit/encoding ที่ต้องใส่ใน §0 ของแผน

## 1. สำรวจ + ยืนยัน (ห้ามเดา)
- ทุกจุดแก้ต้องมี: file:line จริง · โค้ด "ก่อน" ตรงตัว (copy จากไฟล์) · เหตุผล/หลักฐานว่าผิด · คำสั่งยืนยันที่รันได้
- ค้นหลายไฟล์ → ส่ง subagent ค้นได้ แต่ผลต้องตรวจซ้ำเองที่ file:line
- ยืนยันไม่ได้ → ใส่เป็นงาน 🟡 พร้อมขั้น "พิสูจน์" หรือย้ายไป §5 นอกแผน — **ห้ามใส่งานเดาให้ Flash แก้**

## 2. ตัดงาน
- 1 งาน = 1 จุดแก้เล็ก (≤3 ไฟล์) + "ก่อน/หลัง" ตรงตัว + ยืนยัน + ข้อความ commit
- งานที่ต้องออกแบบ/เลือกทาง/รอ user → §2 (ห้ามทำเอง) · เรียงให้ build ผ่านได้ทุกงาน · DoD ต่อกลุ่ม
- เทสต์ใน DoD = เร็วแต่ครอบจุดที่แตะ · FAIL → rerun เฉพาะจุดนั้น 1 ครั้ง · ห้ามเริ่มทั้งชุดใหม่
- **บังคับ "หลักฐานชี้ขาด" ทุกงาน** = path log/ไฟล์ผลที่ DeepSeek สร้างตอนรันยืนยัน + บรรทัด/ค่าที่ต้องเห็น + ค่าก่อนแก้ (แยกได้ว่าแก้จริง) — `/flash-check` ตัดสินจากหลักฐานนี้อย่างเดียว ไม่รันซ้ำ · ออกแบบหลักฐานไม่ได้ = ยังไม่พร้อมส่ง

## 3. เขียนแผน
- คัดลอก `{{FLASHQ}}/templates/FLASH_PLAN_TEMPLATE.md` → `<plan_dir>/PLAN_FLASH_<เรื่อง>.md` · เติม base commit (`git rev-parse --short HEAD`) + กติกาโปรเจกต์ใน §0
- commit เฉพาะไฟล์แผน + push เข้า `<remote>/<main_branch>` (อยู่ worktree/branch อื่น → merge แล้ว `git push <remote> HEAD:<main_branch>` · **ห้าม rebase**) — ทำตามกติกา commit ของโปรเจกต์ถ้ามี
- **ยืนยัน**: `git fetch <remote> <main_branch>; git merge-base --is-ancestor <hash แผน> <remote>/<main_branch>` ต้อง exit 0

## 4. ส่งเข้าคิวกลาง (อัตโนมัติ)
- รัน **ใน background** ที่โฟลเดอร์โปรเจกต์ (Bash `run_in_background: true` · ไม่ poll):
  `python {{FLASHQ}}/flashq.py run <path แผน> T-01..T-NN --switch-on-quota 4`
  (worktree → ใช้ checkout หลักเอง · ตรวจแผนใน remote · มีงานอื่นทั้งเครื่อง = รอคิว · โควตาหมด = สลับบัญชีแล้วสั่งซ้ำ)
- บอก user สั้น ๆ: จำนวนงาน · งานที่รอ user ตัดสิน · "DeepSeek กำลังทำ — ดูใน opencode desktop session `flash <ชื่อแผน> <งาน>` · ดูคิว `python {{FLASHQ}}/flashq.py` · เสร็จแล้วผมตรวจต่อเอง"
- **ได้แจ้งว่าจบ → เรียก `/flash-check <path แผน>` ทันที** พร้อมบรรทัด `FLASH_RUN=...`
- สำรอง: ให้บรรทัด `/flash <path แผน> T-01..T-NN` ไปวางใน opencode (เปิดที่ checkout หลัก) แล้วกลับมาสั่ง `/flash-check <path แผน>`
