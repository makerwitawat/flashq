flashq — อ่านก่อนใช้
======================

เริ่มเร็ว (ละเอียดดู "คู่มือติดตั้ง.md" ในโฟลเดอร์นี้)
  1) วางโฟลเดอร์นี้ในที่ถาวร เช่น C:\Tools\flashq  (ย้ายทีหลัง = ต้องรัน install ใหม่)
  2) PowerShell ในโฟลเดอร์นี้:   .\flashq.exe install        (มี Python 3 + ใช้ Claude Code ใส่ --hooks เพิ่มได้)
  3) เลือกโมเดล:                 .\flashq.exe models --auto
  4) ตรวจ:                       .\flashq.exe install --check   → ต้องได้ INSTALL=OK
  5) เปิด session ใหม่ของ Claude Code / รีโหลด opencode แล้วจึงเห็นคำสั่ง /flash-*
  6) หน้าต่างแอป: ดับเบิลคลิก flashq-gui.exe

ในชุดมี: flashq-gui.exe (หน้าต่างแอป) · flashq.exe (คำสั่ง) · claude\ opencode\ hooks\ templates\ (ต้นฉบับคำสั่ง ห้ามลบ)
ต้องมีในเครื่อง: Windows 10/11 + WebView2 · opencode (ตั้ง provider แล้ว) · Git
