# Windows 10 test installer

The separate **Policem_Setup_Win10_TEST.exe** is a user-scoped installer.
It installs under LocalAppData/Programs/PolicemTest, uses LocalAppData/PolicemTest/data for SQLite and PDFs, binds to 127.0.0.1:8000 and does not install a Windows service, open firewall ports, change proxy configuration, or touch the company server.

After installation, open the Policem TEST desktop shortcut; leave its console open while using the browser. Close the console to stop the local test server. Do not use real customer records. This is a test candidate, not a production build.

The installer does not automatically create an admin password. Initial admin provisioning must be completed through a separately approved secure bootstrap; without it, first login may not work. The port 8000 must be free. The local application is HTTP only, so iPhone Face ID/passkeys cannot be acceptance-tested with this local installer.

To obtain the file, GitHub Actions must finish successfully and publish the artifact named Policem-Win10-TEST-UNSIGNED. A committed workflow is not proof of a successful build.
