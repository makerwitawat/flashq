# โครงสร้าง flashq

> สำหรับคนที่จะแก้โค้ด · วิธีใช้ → [README.md](../README.md) · [REFERENCE.md](REFERENCE.md) · กติกาการแก้ repo → [AGENTS.md](../AGENTS.md)

## ภาพรวม
```
Claude Code (/flash-plan · /flash-check · /flash-goal · /flash-investigate · /flash-qa · /flash-doc)
   │  python flashq.py run <แผน> <T-xx>        ← CLI (flashq.py) · ชนิดอื่น: verify · investigate · qa · doc
   ▼
~/.flashq/jobs/<id>.json  ──คิว──►  ช่องรัน running[-n].lock
   │                                     │ opencode run /flash  (หรือ --agent ผู้ตรวจ/ผู้สืบ)
   │                                     ▼
   │                           opencode serve :4096 ──► DeepSeek Flash แก้โค้ด + commit ในโปรเจกต์
   ▼
flashq ui :4097  (server ใน flashq.py + ui.html)  ── อ่าน jobs/ logs/ goals/ reviews/ ทุก 3 วิ
```
- ทุกคำสั่งเป็น process แยก · ประสานกันผ่านไฟล์ใน `~/.flashq` + file lock (`file_lock`) · ไม่มี daemon คิว — process ของ `run` แต่ละตัวรอช่องเอง (`acquire`)
- เป้าหมาย (`goal`) ไม่รันงานเอง — Claude เป็นคนวน · flashq แค่ตรวจธง (`check`) ตัดสิน (`verify`) และคัดลอกสถานะไป `~/.flashq/goals/` ให้หน้าเว็บ

## ส่วนต่าง ๆ ใน `flashq.py` (เรียงตามไฟล์)
| ส่วน | ฟังก์ชันหลัก |
|---|---|
| ค่าคงที่/ค่าตั้ง | `CONFIG_DEFAULTS` (config.json) · `DEFAULTS` (`.flash.json` ต่อโปรเจกต์ รวม timeout/stall/`variants` ต่อชนิดงาน) · `AGENT_KINDS` (verify/investigate = งานส่ง prompt ตรงให้ agent อ่านอย่างเดียว) · `variant_for` (ลำดับ `--variant` > `.flash.json` > `config.json` > `DEFAULTS`) |
| process/ไฟล์ | `pid_alive` (เทียบเวลาเริ่มกัน pid ซ้ำ) · `kill_tree` · `write_json`/`read_json` · `file_lock` |
| โปรเจกต์/git | `project_root` · `detect_remote` · `detect_main_branch` · `project_cfg` |
| คิว/ช่อง | `jobs` · `save_job` · `take_slot` · `acquire` · `release` · `request_run_now` |
| จัดคิวอัตโนมัติ | `plan_files` · `plan_meta` (`flashq-files`/`flashq-parallel`/`flashq-exclusive`) · `conflict_reason` · `schedule` · `overlap_report` |
| รันงาน | `ensure_live_server` · `wait_session` · `server_activity` (tool/subagent จาก server) · `ShellWatch` (ตัวเฝ้า shell) · `run_once` · `cmd_run` |
| นักทดสอบ | `qa_detect`/`qa_suggest_lines` (เดาชุดจากไฟล์ ไม่รัน) · `qa_spec`/`qa_specs` (ตรวจ+ปรับชุดจาก `.flash.json`/`--cmd`) · `qa_exec` (รันคำสั่งเอง + ฆ่าทั้งต้นเมื่อ timeout/cancel) · `qa_verdict` (fail-closed จาก exit code + `expect`) · `qa_summary` · `qa_analyze` (Flash `flash-tester` อ่าน log เฉพาะตอนล้ม — ไม่เปลี่ยนคำตัดสิน) · `cmd_qa` |
| ช่างเอกสาร | `doc_spec` (ตรวจชุดจาก `.flash.json` · paths กว้างเกิน/ครอบไฟล์ต้องห้าม = ปฏิเสธ) · `doc_guard`/`doc_before`/`doc_changed` (snapshot ก่อน-หลัง · ตรวจการลบไฟล์เองเพราะ `snapshot_changes` ไม่เห็น) · `doc_verdict` (fail-closed: ผ่านได้ทางเดียว `DRAFT` · `doc_secrets`/`doc_badrefs`) · `doc_backup`/`doc_restore` (สำรองไฟล์ที่สกปรกก่อนรัน → `~/.flashq/docbak/<job>` · ย้อนเฉพาะไฟล์ที่แตะ) · `doc_finalize` (`OUTSIDE`/`SECRET` ย้อนทันที) · `doc_since` · `cmd_doc` · `doc_review`/`cmd_doc_review` (รับ/ทิ้ง) · `doc_diff` (diff ใน Python เห็นไฟล์ใหม่) · `doc_row` (ส่วนที่หน้าเว็บใช้ ไม่ส่ง backup) |
| token/ค่าใช้จ่าย | ฝั่ง Claude: `scan_transcript` · `usage_summary` · `cmd_usage` (ผลเก็บ `~/.flashq/usage/<แผน>.json`) · ฝั่ง Flash: `scan_flash_log` (log ของงาน · แคชตาม mtime/size) · `oc_child_usage` (subagent ใน `opencode.db` อ่านอย่างเดียว) · `claude_overhead_usd` · `flash_usage_summary` · `cmd_usage_flash` |
| ขนาดแผน | `PLAN_SOFT`/`PLAN_HARD` · `plan_lint` |
| ยามส่งงาน | `hooks/run_guard.py` (PreToolUse `Bash\|PowerShell` · `scan`/`statements`/`judge` แยกคำสั่งแบบรู้เครื่องหมายคำพูด → บล็อกการส่งงานที่ไม่มีตัวเฝ้า) |
| ยามมอบงานสืบ | `hooks/delegate_guard.py` (2 โหมดในไฟล์เดียว · `prompt` = UserPromptSubmit จับ "ส่งสืบ/ให้ flash สืบ" → แทรกคำสั่ง + ตั้งงบอ่านโค้ด · `pretool` = PreToolUse `Read\|Grep\|Glob\|Bash\|PowerShell` นับการอ่านเอง เกินงบบล็อก · สถานะต่อ session ใน `~/.flashq/delegate/`) · `install --check` = `check_installed` เทียบไฟล์ที่ติดตั้งกับต้นฉบับ (ใช้ชุดเดียวกับ install ผ่าน `install_items`) |
| แจ้งผลกลับ Claude | `notify_job` (งานจบ → `~/.flashq/inbox/` + toast Windows) · `sweep_dead`/`cmd_sweep` (แจ้งงาน process ตาย ครั้งเดียวต่องาน) · hook `hooks/inbox_notify.py` (อ่าน inbox ตอนผู้ใช้พิมพ์ข้อความ แล้วแทรกผล+คำแนะนำเข้า session) |
| CLI อื่น | `cmd_wait` · `cmd_shrink` · `cmd_list` · `cmd_status` · `diagnose_job`/`cmd_why` · `cmd_log` · `cancel_job` · `cmd_config` · `cmd_runnow` · `switch_account` · `cmd_models`/`run_models` (+ `machine_models` · `pick_model` · `set_agent_model` · `ensure_models` ที่ install เรียก) · `cmd_install` · `cmd_init` · `cmd_review` · `cmd_prune` |
| ข้อมูลหน้าเว็บ | `ui_state` (ทุกอย่างที่ `/api/state` ส่ง) · `plan_trail` (งานที่เกี่ยวกับแผนเดียวกัน) · `job_stats` · `ui_reviews` · `log_tail` |
| server | `make_ui_server` · `cmd_ui` |
| เป้าหมาย | `goal_parse` · `goal_lint` · `goal_publish` · `goal_phase` (ขั้น/รอบที่กำลังทำ) · `ui_goals` · `goal_changed_files` · `goal_human` · `transcript_state`/`claude_activity` (อ่าน transcript ของ Claude Code) · `cmd_goal` |

## ไฟล์ข้อมูล (`~/.flashq` หรือ `FLASHQ_HOME`)
| ไฟล์ | เนื้อหา |
|---|---|
| `jobs/<id>.json` | งานหนึ่งงาน: `id` `kind` (work/verify/investigate/qa/test/doc) `status` (qa: + `qa` = ผลต่อชุด `[{name,cmd,verdict,secs,head,...}]` · `tasks` = ชื่อชุด · doc: + `doc` = `{name,verdict,state,why,changed,head0,after_sha,backup,...}` · `tasks` = ชื่อชุดเอกสาร) `project` `plan` `tasks` `message` `agent` `readonly` `title` `model` `slot` `pid`/`pid_start` `child_pid` `session` `logs` `created`/`started`/`finished` `shell_watch` `agent_act` `qv` |
| `logs/<id>_<n>.jsonl` · `.err` | output ของ opencode รอบที่ n (รอบลองใหม่/สลับบัญชีเพิ่มเลข) · stderr |
| `running.lock` · `running-<n>.lock` | ใครถือช่อง 1 / ช่อง n |
| `docbak/<job>/` | สำเนาไฟล์ที่ "สกปรกอยู่แล้ว" + ไฟล์ต้องห้ามก่อนช่างเอกสารแตะ (ไว้ย้อนตอนทิ้งร่าง/OUTSIDE/SECRET · ไฟล์เกิน 20MB ข้ามการสำรอง) |
| `run_now/<id>` | สัญญาณ "รันเลย" จากหน้าเว็บ/`runnow` |
| `config.json` | `max_parallel` `schedule` `starve_min` `image_max_px` `image_max_reads` · ทับค่าเริ่มต้นได้: `variants` `prices` `flash_compare` `notify` `notify_toast` ฯลฯ |
| `inbox/*.json` · `inbox/done/` | ผลงานจบรอส่งถึง Claude · ส่งแล้วย้ายไป `done/` |
| `usage/<แผน>.json` | ผลล่าสุดของ `flashq usage <แผน>` (token Claude ต่อแผน) ให้การ์ดงาน/ธงแสดง |
| `goals/<gid>.json` | สำเนาสถานะเป้าหมาย: `items` (G-xx) `rounds` (เพิ่มเฉพาะตอน verify) `rounds_max` `hours` `started` `owner` (session Claude Code) |
| `reviews/rv_*.json` | ป้าย Claude ตรวจ: `plan_name` `tasks` `status` (reviewing/pass/fail) `started` `finished` |
| `ui.log` · `live_server.pid/.log` | log ของหน้าเว็บ · server opencode ที่ flashq เปิดให้ |

ในโปรเจกต์: `.flash.json` · แผน `docs/plans/PLAN_*FLASH*.md` · เป้าหมาย `GOAL_*.md` · สถานะธง `.tmp/flashq-goal/` (base commit + ลายนิ้วมือเกณฑ์)

## API ของหน้าเว็บ (127.0.0.1 เท่านั้น)
- GET: `/` (ui.html + token) · `/api/state` · `/api/log` · `/api/why` · `/api/overlap` · `/api/plans` (คืน `qa_presets`/`doc_presets` ด้วย) · `/api/flash_usage?days=` (สรุป token/USD ของ Flash + ประมาณการประหยัด · `flash_usage_summary`) · `/api/doc_diff?id=` (diff ของร่างเอกสาร)
- POST (ต้องผ่าน Host/Origin + token): `/api/cancel` · `/api/stop` · `/api/runnow` · `/api/config` · `/api/dismiss` · `/api/submit` · `/api/retry` · `/api/prune` · `/api/open` · `/api/claude_check` (เปิด session Claude ตรวจงาน) · `/api/goal` · `/api/switch` · `/api/accounts` (เพิ่ม/แก้/ลบ/ย้าย/reset บัญชีที่ `~/.flashq/accounts.json`) · `/api/role_model` (ตั้งโมเดลบทบาท) · `/api/doc_review` (รับ/ทิ้งร่างเอกสาร · ทิ้งต้อง `confirm`=id · `force` ทับไฟล์ที่แก้ต่อ)
- คำสั่งที่หน้าเว็บสั่งรัน (`submit`/`retry`) สร้าง argv เป็น list (`build_run_argv`) แล้ว `spawn_run` แบบ detached ไม่ผ่าน shell

## `ui.html`
- หน้าเดียว ไม่มี build step · poll `/api/state` ทุก 3 วิ แล้ว render ใหม่เฉพาะส่วนที่ signature เปลี่ยน
- สองมุมมอง: แดชบอร์ด และ 🏢 ออฟฟิศ (`sceneSVG` วาดฉาก SVG · `deskSVG` ต่อช่อง · `loungeSVG` ห้องพัก/โซฟา (สถานะนั่ง-หลับ-ไปทำงานคำนวณใน `officeModel` → `m.lounge`) · การ์ดงาน `runCardHTML` · แถบขั้น `goalStepsHTML`/`runGoalHTML`/`planTrailHTML`)
- การ์ด "🪙 token ของ Flash · ประหยัด" (`flashUsageHTML` · ดึง `/api/flash_usage` แยกจากรอบ refresh 3 วิ) และช่องที่ 5 "ประหยัดเทียบ Claude" ในแถบสรุปบนสุดของหน้า office ใช้ข้อมูลชุดเดียวกัน
- โหมดสั่งงาน "เอกสาร": เลือกได้แค่ชื่อชุดจาก `doc_presets` · การ์ดงานเอกสารแสดงคำตัดสิน (`DOC_ICON`) + ปุ่มดู diff (`openDocDiff` · `#docDiffDlg`) / รับ / ทิ้ง
- ค่าที่จำในเบราว์เซอร์ผ่าน `store` (localStorage ห่อ try/catch): มุมมอง · ขนาดฟอนต์ · แผงพับ · ย่อการ์ด (`compactRuns`/`compactGoals`) · เสียง

## ตัวแปรแวดล้อม
| ตัวแปร | ใช้ทำอะไร |
|---|---|
| `FLASHQ_HOME` | ที่เก็บข้อมูล (ค่าเริ่มต้น `~/.flashq`) — เทสต์และ server ทดสอบใช้ตัวนี้ |
| `FLASHQ_OPENCODE` | คำสั่ง opencode (เทสต์ใช้ opencode ปลอม) |
| `FLASHQ_OPENCODE_CONFIG` | path `opencode.json` |
| `FLASHQ_OPENCODE_LOG` | path log กลางของ opencode ที่ใช้วินิจฉัย NOSTART (ค่าเริ่มต้น `~/.local/share/opencode/log/opencode.log`) |
| `FLASHQ_START_LIMIT_SEC` | รอ sessionID ใน log นานสุดกี่วิก่อนนับเป็น NOSTART (ค่าเริ่มต้น 180 · เทสต์ตั้งสั้น) |
| `FLASHQ_LIVE_URL` | URL ของ `opencode serve` (ค่าเริ่มต้น `http://127.0.0.1:4096`) |
| `FLASHQ_CLAUDE_HOME` | ที่ของ `~/.claude` ที่ `install` ติดตั้งคำสั่ง/agent/hook ลงไป (transcript ของ Claude Code อ่านจาก `~/.claude/projects` เสมอ) |
| `FLASHQ_SHELL_POLL_SEC` | ความถี่ของตัวเฝ้า shell (วินาที) |
| `FLASHQ_FAKE_PROCS` | ตารางโปรเซสปลอมสำหรับเทสต์ตัวเฝ้า shell |
