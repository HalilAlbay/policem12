# Pilot V1 storage and backup — steps 4 and 5

Storage root: %ProgramData%\Policem
Application data: %ProgramData%\Policem\data (SQLite DB and documents).
Logs: %ProgramData%\Policem\logs.
Backups: %ProgramData%\Policem\backups, restricted to administrators/SYSTEM.
Existing app.py honors POLICEM_DATA; frozen server entrypoint defaults to this data directory.

Run initialize-storage.ps1 as administrator, review actual ACLs and Windows service identity before live use. The service must not run as an administrator. Never overwrite or delete existing database or documents during install/upgrade.

Backup prototype: python packaging/pilot_backup.py backup --data <data-folder> --archive <new-archive.zip>
Verify: python packaging/pilot_backup.py verify --archive <archive.zip>
Restore into NEW directory while application is stopped: python packaging/pilot_backup.py restore --archive <archive.zip> --target <new-empty-path>

Backup uses SQLite's online backup API, checks database integrity, includes documents and SHA-256 checksums. It deliberately does NOT delete older backups or replace live data during restore.

Critical limitations before pilot:
- Cross-resource consistency: SQLite snapshot and document copies are not one atomic transaction. Pause uploads or stop service during scheduled backup; implement application-wide upload quiescing for online backups.
- No Windows scheduled task has been installed or tested yet; configure a separate low-privilege backup operator and daily schedule.
- Copy backups off the office server (encrypted storage), define retention and restore drill.
- Test with real application data layout, multiple documents, Windows ACLs, service restarts, and WAL transactions.
- Do not claim disaster recovery is complete until a backup has been restored and validated on a separate environment.
