"""Offline initial admin bootstrap; run only before first real user exists."""
import argparse
import getpass
import os
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    args.data.mkdir(parents=True, exist_ok=True)
    os.environ["POLICEM_DATA"] = str(args.data.resolve())
    from app import init, conn, password_hash
    init()
    with conn() as db:
        count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count:
            raise SystemExit("Users already exist: refusing to reset credentials")
    password = getpass.getpass("New admin password (min 12 chars): ")
    repeat = getpass.getpass("Confirm admin password: ")
    if len(password) < 12 or password != repeat:
        raise SystemExit("Password too short or confirmation mismatch")
    with conn() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            raise SystemExit("Concurrent bootstrap detected")
        branch = db.execute("SELECT id FROM branches ORDER BY id LIMIT 1").fetchone()
        if not branch:
            raise SystemExit("Missing default branch")
        db.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id) VALUES(?,?,?,?,?)", ("admin","İlk Yönetici","partner",password_hash(password),branch[0]))
        db.commit()
    print("Initial admin created. Remove any POLICEM_ADMIN_PASSWORD environment variable before service startup.")

if __name__ == "__main__":
    main()
