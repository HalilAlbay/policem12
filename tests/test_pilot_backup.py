import importlib.util
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("pilot_backup", Path(__file__).resolve().parents[1] / "packaging" / "pilot_backup.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

class PilotBackupTests(unittest.TestCase):
    def test_backup_verify_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            (data / "documents").mkdir(parents=True)
            (data / "documents" / "policy.pdf").write_bytes(b"%PDF-1.4 test")
            with closing(sqlite3.connect(data / "policem.sqlite3")) as db:
                db.execute("CREATE TABLE policies (id INTEGER PRIMARY KEY, number TEXT)")
                db.execute("INSERT INTO policies(number) VALUES ('TEST-001')")
            archive = root / "snapshot.zip"
            mod.backup(data, archive)
            self.assertEqual(mod.verify(archive), 2)
            restored = root / "restored"
            mod.restore(archive, restored)
            self.assertEqual((restored / "documents" / "policy.pdf").read_bytes(), b"%PDF-1.4 test")
            with closing(sqlite3.connect(restored / "policem.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT number FROM policies").fetchone()[0], "TEST-001")
            with self.assertRaises(FileExistsError):
                mod.restore(archive, restored)
    def test_reject_missing_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "documents").mkdir()
            with self.assertRaises(FileNotFoundError):
                mod.backup(root, root / "out.zip")

if __name__ == "__main__":
    unittest.main()
