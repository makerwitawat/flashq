# โครงสร้าง flashq

> สำหรับคนที่จะแก้โค้ด · วิธีใช้ → [README.md](../README.md) · กติกาการแก้ repo → [AGENTS.md](../AGENTS.md)

## ภาพรวม
```
Claude Code (/flash-plan · /flash-check · /flash-goal)
   │  python flashq.py run <แผน> <T-xx>        ← CLI (flashq.py)
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
| ค่าคงที่/ค่าตั้ง | `CONFIG_DEFAULTS` (config.json) · `DEFAULTS` (`.flash.json` ต่อโปรเจกต์) · `AGENT_KINDS` |
| process/ไฟล์ | `pid_alive` (เทียบเวลาเริ่มกัน pid ซ้ำ) · `kill_tree` · `write_json`/`read_json` · `file_lock` |
| โปรเจกต์/git | `project_root` · `detect_remote` · `detect_main_branch` · `project_cfg` |
| คิว/ช่อง | `jobs` · `save_job` · `take_slot` · `acquire` · `release` · `request_run_now` |
| จัดคิวอัตโนมัติ | `plan_files` · `plan_meta` (`flashq-files`/`flashq-parallel`) · `conflict_reason` · `schedule` · `overlap_report` |
| รันงาน | `ensure_live_server` · `wait_session` · `server_activity` (tool/subagent จาก server) · `ShellWatch` (ตัวเฝ้า shell) · `run_once` · `cmd_run` |
| ขนาดแผน | `PLAN_SOFT`/`PLAN_HARD` · `plan_lint` |
| CLI อื่น | `cmd_wait` · `cmd_shrink` · `cmd_list` · `cmd_status` · `diagnose_job`/`cmd_why` · `cmd_log` · `cancel_job` · `cmd_config` · `cmd_runnow` · `switch_account` · `cmd_install` · `cmd_init` · `cmd_review` · `cmd_prune` |
| ข้อมูลหน้าเว็บ | `ui_state` (ทุกอย่างที่ `/api/state` ส่ง) · `plan_trail` (งานที่เกี่ยวกับแผนเดียวกัน) · `job_stats` · `ui_reviews` · `log_tail` |
| server | `make_ui_server` · `cmd_ui` |
| เป้าหมาย | `goal_parse` · `goal_lint` · `goal_publish` · `goal_phase` (ขั้น/รอบที่กำลังทำ) · `ui_goals` · `goal_changed_files` · `goal_human` · `transcript_state`/`claude_activity` (อ่าน transcript ของ Claude Code) · `cmd_goal` |

## ไฟล์ข้อมูล (`~/.flashq` หรือ `FLASHQ_HOME`)
| ไฟล์ | เนื้อหา |
|---|---|
| `jobs/<id>.json` | งานหนึ่งงาน: `id` `kind` (work/verify/investigate/test) `status` `project` `plan` `tasks` `message` `agent` `readonly` `title` `model` `slot` `pid`/`pid_start` `child_pid` `session` `logs` `created`/`started`/`finished` `shell_watch` `agent_act` `qv` |
| `logs/<id>_<n>.jsonl` · `.err` | output ของ opencode รอบที่ n (รอบลองใหม่/สลับบัญชีเพิ่มเลข) · stderr |
| `running.lock` · `running-<n>.lock` | ใครถือช่อง 1 / ช่อง n |
| `run_now/<id>` | สัญญาณ "รันเลย" จากหน้าเว็บ/`runnow` |
| `config.json` | `max_parallel` `schedule` `starve_min` `image_max_px` `image_max_reads` |
| `goals/<gid>.json` | สำเนาสถานะเป้าหมาย: `items` (G-xx) `rounds` (เพิ่มเฉพาะตอน verify) `rounds_max` `hours` `started` `owner` (session Claude Code) |
| `reviews/rv_*.json` | ป้าย Claude ตรวจ: `plan_name` `tasks` `status` (reviewing/pass/fail) `started` `finished` |
| `ui.log` · `live_server.pid/.log` | log ของหน้าเว็บ · server opencode ที่ flashq เปิดให้ |

ในโปรเจกต์: `.flash.json` · แผน `docs/plans/PLAN_*FLASH*.md` · เป้าหมาย `GOAL_*.md` · สถานะธง `.tmp/flashq-goal/` (base commit + ลายนิ้วมือเกณฑ์)

## API ของหน้าเว็บ (127.0.0.1 เท่านั้น)
- GET: `/` (ui.html + token) · `/api/state` · `/api/log` · `/api/why` · `/api/overlap` · `/api/plans`
- POST (ต้องผ่าน Host/Origin + token): `/api/cancel` · `/api/stop` · `/api/runnow` · `/api/config` · `/api/dismiss` · `/api/submit` · `/api/retry` · `/api/prune` · `/api/open` · `/api/goal` · `/api/switch`
- คำสั่งที่หน้าเว็บสั่งรัน (`submit`/`retry`) สร้าง argv เป็น list (`build_run_argv`) แล้ว `spawn_run` แบบ detached ไม่ผ่าน shell

## `ui.html`
- หน้าเดียว ไม่มี build step · poll `/api/state` ทุก 3 วิ แล้ว render ใหม่เฉพาะส่วนที่ signature เปลี่ยน
- สองมุมมอง: แดชบอร์ด และ 🏢 ออฟฟิศ (`sceneSVG` วาดฉาก SVG · `deskSVG` ต่อช่อง · การ์ดงาน `runCardHTML` · แถบขั้น `goalStepsHTML`/`runGoalHTML`/`planTrailHTML`)
- ค่าที่จำในเบราว์เซอร์ผ่าน `store` (localStorage ห่อ try/catch): มุมมอง · ขนาดฟอนต์ · แผงพับ · ย่อการ์ด (`compactRuns`/`compactGoals`) · เสียง

## ตัวแปรแวดล้อม
| ตัวแปร | ใช้ทำอะไร |
|---|---|
| `FLASHQ_HOME` | ที่เก็บข้อมูล (ค่าเริ่มต้น `~/.flashq`) — เทสต์และ server ทดสอบใช้ตัวนี้ |
| `FLASHQ_OPENCODE` | คำสั่ง opencode (เทสต์ใช้ opencode ปลอม) |
| `FLASHQ_OPENCODE_CONFIG` | path `opencode.json` |
| `FLASHQ_LIVE_URL` | URL ของ `opencode serve` (ค่าเริ่มต้น `http://127.0.0.1:4096`) |
| `FLASHQ_CLAUDE_HOME` | ที่ของ `~/.claude` ที่ `install` ติดตั้งคำสั่ง/agent/hook ลงไป (transcript ของ Claude Code อ่านจาก `~/.claude/projects` เสมอ) |
| `FLASHQ_SHELL_POLL_SEC` | ความถี่ของตัวเฝ้า shell (วินาที) |
| `FLASHQ_FAKE_PROCS` | ตารางโปรเซสปลอมสำหรับเทสต์ตัวเฝ้า shell |
