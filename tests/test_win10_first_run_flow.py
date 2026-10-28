"""Guard the Windows 10 pilot setup -> explicit login flow."""
import unittest
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")

class Win10FirstRunFlowTests(unittest.TestCase):
    def test_first_account_requires_explicit_login(self):
        start = HTML.index("async function createFirstAccount(){")
        end = HTML.index("\nasync function login()", start)
        flow = HTML[start:end]
        self.assertIn("await api('setup','POST'", flow)
        self.assertIn("Kurulum tamamlandı.", flow)
        self.assertNotIn("await login()", flow)
        self.assertIn("$('password').value=''", flow)

    def test_local_test_restart_shows_setup_or_login(self):
        self.assertIn("checkFirstSetup().then(", HTML)
        self.assertIn("if(localWin10Test){token=null;sessionStorage.removeItem('policem_token')}", HTML)
        self.assertIn("if(token&&!localWin10Test", HTML)

    def test_login_errors_are_visible(self):
        self.assertIn('id="loginFeedback"', HTML)
        self.assertIn("feedback.textContent=e.message||'Giriş başarısız.'", HTML)

if __name__ == "__main__":
    unittest.main()
