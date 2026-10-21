# CHANGELOG

สรุปความสามารถตามวัน (รายละเอียดเต็มดู `git log`) · ใหม่สุดอยู่บน

## 2026-10-21
- **สถานะ `DENIED`**: opencode (โหมดไม่โต้ตอบ) ปฏิเสธสิทธิ์เอง เช่น อ่านไฟล์นอกโปรเจกต์ที่ `permission.external_directory` เป็น `ask` → เดิมบันทึกเป็น OK เพราะ exit 0 · ตอนนี้ตรวจ stderr `auto-rejecting` + tool error "ปฏิเสธสิทธิ์" → `FLASH_RUN=DENIED` + บรรทัด `DENIED:` บอก path + ทางแก้ 2 ทาง (`external_dirs` ใน `.flash.json` / `opencode.json`) · มี commit/`DONE` = คง OK แต่ `WARN:` · `wait` คืน 1 · หน้าเว็บป้าย DENIED + 🚫 path + ทางแก้ในกล่อง log · `.flash.json` ช่อง `external_dirs` → flashq ส่งสิทธิ์ผ่าน `OPENCODE_CONFIG_CONTENT` (ไม่แตะไฟล์ผู้ใช้) + ตรวจก่อนรันว่า `opencode.json`/server สดอนุญาตแล้วหรือยัง (`PERM:`/`WARN:`) + เตือน `opencode.json` อ่านไม่ได้ · บรรทัดคำสั่งที่กฎ agent บล็อกเปลี่ยนชื่อเป็น `RULE_DENIED:`

## 2026-10-20
- **มิเตอร์ token Claude ต่อแผน**: `flashq usage <แผน|โปรเจกต์> [--since วัน]` สแกน transcript ของ Claude Code (โฟลเดอร์ที่ cwd ตรงกับโปรเจกต์ + worktree · อ่านทีละบรรทัด) รวม token แยกขั้นวางแผน/ตรวจ/รอบแก้ + โมเดล · USD โดยประมาณ (ทับราคาได้ใน `config.json` ช่อง `prices`) · บรรทัด `USAGE=…` · เก็บ `~/.flashq/usage/<แผน>.json` → การ์ดงาน/การ์ดธงโชว์ "🪙 Claude ใช้ ~Nk token (~$x) · วางแผน a% · ตรวจ b%"
- **ประหยัด token Claude**: `flashq run` ตรวจขนาดแผน (เตือน 300/100/30 · ปฏิเสธ 600/200/60 บรรทัด · ห้ามภาคผนวกโค้ด) · 1 แผน = 1 session (`flashq wait` + subagent `flash-checker`) · hook `image_guard` + `flashq shrink` กันรูปใหญ่ · `install --hooks`
- **โหมดเป้าหมาย `/flash-goal`**: ตั้งธงเกณฑ์วัดได้แล้ววนให้ Flash ทำจนผ่าน · `flashq goal check/verify/status/human` · เบรกเมื่อพังซ้ำ/ครบงบ/หลุดขอบเขต/แก้ไฟล์ล็อก/ย้ายเสาประตู · ตรวจขอบเขตเฉพาะช่วงที่งาน Flash ของเป้าหมายรัน
- **หน้าเว็บ — เป้าหมาย**: แผง 🚩 (สถานะ · แถบรอบ/เวลา · เกณฑ์ ✅/❌ · เหตุเบรก) · ปุ่มตรวจใหม่ / ✅❌ คนตรวจ / ให้ Claude ทำต่อ · บอก session เจ้าของธง · แถบขั้นตอน · บอกรอบที่กำลังทำ + เตือนรอบที่ยังไม่ verify
- **หน้าเว็บ — การ์ดงาน**: บอกผู้ช่วยย่อย (subagent) และไม่เตือน log เงียบเมื่อยังทำงาน · ป้ายยาม/ผู้ตรวจไม่ค้าง · ผังโต๊ะ ≤5 ช่องแถวเดียว · ปุ่ม ▤ ย่อ/▦ ขยาย · แถบขั้น สืบ → แผน → Flash ทำ → ตรวจ → ผล + งานที่เกี่ยวข้อง (ผู้สืบ · รอบเดิม · ผู้ตรวจ)
- **กล่องข้อความ `ask()`** แทน confirm/prompt ของเบราว์เซอร์ทุกจุด
- **ตัวเฝ้า shell**: วัด CPU/I/O ของคำสั่งที่ opencode รัน · ฆ่าเฉพาะคำสั่งที่นิ่งหรือลูกกำพร้าถือ handle (งานทำต่อ) · ยาม 🛡 ในออฟฟิศ
- **งานค้าง**: เกณฑ์ปรับตามจังหวะ log จริง · ถาม tool/subagent จาก server ก่อนฆ่า · abort session บน server · `flashq why` + ปุ่ม 🔍 ตรวจสาเหตุ · ลองใหม่เองหนึ่งครั้ง
- **ผู้ตรวจ/ผู้สืบ**: `flashq investigate` · ย้าย provider เมื่อโควตาหมด · timeout 30 นาที · ตรวจ CITATIONS · เตือนเมื่อไฟล์เปลี่ยนระหว่างงานอ่านอย่างเดียว
- **กติกา Flash/Claude**: แผน = สเปก (Claude ห้ามเขียนโค้ดแทน) · งานแบบเทสต์ก่อน (แดง → เขียว) · `flash-check` ห้ามแก้โค้ดเอง · merge ขัดแย้ง = abort แล้วรายงาน
- แก้ path ไทย/`.flash.json` มี BOM ในโปรเจกต์อื่น · `review start` รับหลายงาน

## 2026-10-19
- **`flashq verify`** ผู้ตรวจอิสระ (`--agent` `--readonly` `--title`) + สถิติแยกชนิดงาน · ติดตั้ง agent `flash-verifier` `flash-investigator` แบบ global
- **ป้ายผู้ตรวจ `/flash-check`** (`review start/done`) + แจ้งเตือนผลตรวจ
- ออฟฟิศ: ผู้ตรวจ/ผู้สืบแต่งตัวต่างกัน · ตกแต่งห้อง · โมเดล/บัญชีบนโต๊ะและการ์ด · เสียงเตือนเมื่องานจบ
- ตรวจ branch หลักก่อนส่งงาน · ตรวจโควตาเฉพาะ error จริง · agent หาไม่เจอ/เป็น subagent = FAIL

## 2026-10-18
- **เริ่มต้น**: คิวกลางส่งงาน opencode (DeepSeek Flash) ทุกโปรเจกต์ · กัน pid ถูกใช้ซ้ำ
- `/flash-plan` `/flash-check` แบบ global + `flashq install` · `flashq init` (+ `--commit` · `/flash-init`) ตรวจ branch หลัก/remote เอง
- **รันคู่ขนาน** `max_parallel` + ปุ่มรันเลย (ตรวจไฟล์ซ้อน) · **จัดคิวอัตโนมัติ** `schedule auto` + กันอดตาย + `flashq-files` ในแผน
- **หน้าเว็บ `flashq ui`**: dashboard · ส่งงาน/สั่งซ้ำ · หยุดงาน (ยืนยัน 2 ชั้น) · ป้ายงาน process ตาย · ฟอนต์ตามจอ · แท็บ 🏢 ออฟฟิศการ์ตูน (หน้าแรก) + ประมาณเวลาเสร็จ · `flashq-ui.bat`
