# CC_attendance — GOJ Staff Time Tracking
## Operational Runbook

### Infrastructure
| Component | Path | Port |
|-----------|------|------|
| **DB** | `~/Desktop/REX/attendance.db` (SQLite, WAL mode) | — |
| **API server** | `~/Desktop/REX/CC_attendance.py` | `:8101` |
| **DB logic** | `~/Desktop/REX/CC_attendance_db.py` | — |
| **launchd** | `~/Library/LaunchAgents/com.ghs.cc-attendance.plist` | — |
| **Hub widget** | `hermes-hub/server.py` → `GOJ_ATTEND` | `:9000` |
| **Backup script** | `~/Desktop/REX/backup_attendance.sh` | — |

### Registered Staff
| ID | Name | Department | MAC | RFID |
|----|------|-----------|-----|------|
| 1 | Vladimir | admin | `vlads_mac` | `RFID001` |
| 2 | Mykhailo | kitchen | `mykhailo_mac` | `RFID002` |
| 3 | Front Desk | frontdesk | `frontdesk_mac` | `RFID003` |
| 4 | Alejandro Kato | chairman | `kato_mac` | `RFID000` |

> **MAC addresses are placeholders.** Once real device MACs are collected (WiFi SSID or `CC_ghs_staff_daemon.py` scanning), update via `POST /api/staff/update`.

### API Reference
| Method | Route | Purpose |
|--------|-------|---------|
| `GET` | `/health` | Health + stats (staff_count, audit_entries) |
| `POST` | `/api/event` | Clock in/out toggle. Body: `{"mac":"vlads_mac"}` |
| `GET` | `/api/attendance/today` | Today's attendance (Hub widget source) |
| `GET` | `/api/staff` | List all registered staff |
| `POST` | `/api/staff/register` | Register new staff |

### Clock-In/Out Flow
Each `POST /api/event` **toggles**: if clocked in → clock out; if clocked out → clock in.
- Uses MAC address as primary identifier
- Audit chain logs every action (SHA-256 linked list, genesis block)
- Session UUIDs tie clock-in to clock-out pairs

### Audit Chain
- Cryptographically linked list in `audit_log` table
- Verify: `python3 -c "from CC_attendance_db import AttendanceDB; print(AttendanceDB().verify_audit_chain())"`
- Current: **20 entries, valid** (as of 2026-07-15)

### Backup
- **Nightly** (2AM ET): `cronjob 57684d57e324` → cartoons drive + local copy
- **Manual**: `bash ~/Desktop/REX/backup_attendance.sh`
- **Local**: `~/Desktop/REX/backups/` (hourly manual is recommended)
- **Remote**: `/Volumes/cartoons/hermes-backups/attendance/` (30-day retention)

### Service Management
```bash
# Status
launchctl list | grep cc-attendance
curl -s http://127.0.0.1:8101/health

# Restart
launchctl bootout gui/$(id -u)/com.ghs.cc-attendance && sleep 1
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ghs.cc-attendance.plist

# Logs
tail -f ~/Desktop/REX/cc_attendance.log
```

### Hub Dashboard
- URL: `http://127.0.0.1:9000`
- Widget: GOJ Attendance panel → polls `:8101/api/attendance/today`
- Shows: staff status (in/out), session durations, live clock

### Adding New Staff
```bash
curl -X POST http://127.0.0.1:8101/api/staff/register \
  -H "Content-Type: application/json" \
  -d '{"name":"New Person","department":"kitchen","mac":"new_mac","rfid":"RFID005"}'
```

### Troubleshooting
| Symptom | Check |
|---------|-------|
| Hub shows `alive: false` | `curl http://127.0.0.1:8101/health` — restart if needed |
| Clock-in returns error | Check MAC is registered: `curl http://127.0.0.1:8101/api/staff` |
| Audit chain corrupt | Restore from backup, re-register staff |
| cartoons not mounted | Backup skips silently; manually mount and run script |

### Real MAC Addresses (to be filled)
When devices are on the GOJ WiFi network, collect real MACs from the router or via `CC_ghs_staff_daemon.py` device detection, then update the staff table.
