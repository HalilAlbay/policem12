"""Static contract checks for the isolated Windows 10 updater/release pipeline."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github/workflows/windows-server-package.yml').read_text(encoding='utf-8')
ISS = (ROOT / 'packaging/Policem-Test.iss').read_text(encoding='utf-8')
UPDATER = (ROOT / 'packaging/update-win10-test.ps1').read_text(encoding='utf-8')

class Win10UpdaterContract(unittest.TestCase):
    def test_release_is_published_with_checksum(self):
        self.assertIn('gh release create $tag', WORKFLOW)
        self.assertIn('--latest', WORKFLOW)
        self.assertIn('Policem_Setup_Win10_TEST.exe.sha256', WORKFLOW)
        self.assertIn('Stamp Windows 10 TEST release version', WORKFLOW)
    def test_installed_version_marker(self):
        self.assertIn('Source: "installed-release.txt"', ISS)
        self.assertIn('Set-Content -Path packaging/installed-release.txt', WORKFLOW)
    def test_update_checks_integrity_and_install_result(self):
        self.assertIn('Get-FileHash $exe -Algorithm SHA256', UPDATER)
        self.assertIn('$process.ExitCode -ne 0', UPDATER)
        self.assertIn('$installed -ne $release.tag_name', UPDATER)
        self.assertIn('if ($current -eq $release.tag_name)', UPDATER)
    def test_test_data_location_not_modified(self):
        self.assertNotIn('Remove-Item', UPDATER)
        self.assertNotIn('PolicemTest\\data', UPDATER)

if __name__ == '__main__':
    unittest.main()
