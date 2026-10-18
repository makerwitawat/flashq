---
description: >-
  (Claude Code · ทุกโปรเจกต์) ตั้งค่าโปรเจกต์นี้ให้ใช้ flashq ได้ในคำสั่งเดียว (ตรวจ branch หลัก → .flash.json · commit + push) · /flash-init. Triggers: ตั้งค่า flashq, โปรเจกต์ใหม่ใช้ flashq
---
<!-- flashq:managed — ติดตั้งโดย `flashq.py install` (ต้นฉบับ {{FLASHQ}}/claude/commands/) -->

รันที่รากโปรเจกต์ปัจจุบัน (ไม่ต้องถามอะไร):

```
python {{FLASHQ}}/flashq.py init --install --commit
```

แล้วรายงานผลเป็นไทยสั้น ๆ: ค่าที่ตรวจเจอ (`main_branch` · `remote`) · commit/push สำเร็จไหม · ส่วน "ขั้นต่อไป" ที่เหลือ (เช่น ติดตั้ง opencode · ตั้งโมเดล flash-worker · อยู่ผิด branch)

- ผลบอกว่า push ไม่ได้/อยู่ branch อื่น → บอก user ตรง ๆ ห้าม force push
- สำเร็จทั้งหมด → ทดสอบต่อด้วย `python {{FLASHQ}}/flashq.py run --message "ตอบแค่คำว่า PONG"` ได้ถ้า user ต้องการ
