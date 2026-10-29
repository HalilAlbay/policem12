import 'package:flutter/material.dart';
import 'src/api/policem_api.dart';
import 'src/auth/session_manager.dart';
import 'src/auth/biometric_gate.dart';
import 'src/screens/dashboard_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const PolicemApp());
}

class PolicemApp extends StatelessWidget {
  const PolicemApp({super.key});
  @override Widget build(BuildContext context) => MaterialApp(
    title: 'Poliçem',
    theme: ThemeData(colorSchemeSeed: const Color(0xFF1755A2)),
    home: const LoginScreen(),
  );
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final username = TextEditingController();
  final password = TextEditingController();
  final session = SessionManager(PolicemApi());
  final biometric = BiometricGate();
  bool biometricsAvailable = false;
  bool biometricsEnabled = false;
  bool locked = false;
  bool busy = false;
  String? error;
  Map<String, dynamic>? user;

  @override void initState() {
    super.initState();
    _restore();
  }
  Future<void> _restore() async {
    setState(() => busy = true);
    try {
      biometricsAvailable = await biometric.available();
      biometricsEnabled = await biometric.enabled();
      if (biometricsEnabled) {
        final unlocked = await biometric.verify();
        if (!unlocked) {
          if (mounted) setState(() { locked = true; error = 'Biyometrik doğrulama gerekli.'; });
          return;
        }
      }
      final restored = await session.restore();
      if (mounted) setState(() => user = restored);
    } catch (_) {
      if (mounted) setState(() => error = 'Oturum kontrol edilemedi. İnternet bağlantısını kontrol edin.');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }
  Future<void> _login() async {
    setState(() { busy = true; error = null; });
    try {
      final loggedIn = await session.login(username.text.trim(), password.text);
      password.clear();
      if (mounted) setState(() { user = loggedIn; locked = false; });
    } on ApiException catch (e) {
      if (mounted) setState(() => error = e.message);
    } catch (_) {
      if (mounted) setState(() => error = 'Bağlantı kurulamadı.');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }
  Future<void> _logout() async {
    setState(() => busy = true);
    try {
      await session.logout();
      await biometric.disable();
      if (mounted) setState(() { user = null; locked = false; error = null; });
    } catch (_) {
      if (mounted) setState(() => error = 'Çıkış işlemi tamamlanamadı.');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }
  Future<void> _unlock() async {
    if (!await biometric.verify()) return;
    setState(() { locked = false; error = null; });
    await _restore();
  }
  Future<void> _enableBiometrics() async {
    final ok = await biometric.enroll();
    if (mounted) setState(() {
      biometricsEnabled = ok;
      error = ok ? null : 'Biyometrik doğrulama etkinleştirilemedi.';
    });
  }
  @override void dispose() {
    username.dispose(); password.dispose(); session.api.close(); super.dispose();
  }
  @override Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Poliçem')),
    body: locked ? Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
      const Text('Poliçem kilitli'),
      FilledButton(onPressed: _unlock, child: const Text('Face ID / Parmak izi ile aç')),
      TextButton(onPressed: () async { await session.logout(); await biometric.disable(); if (mounted) setState(() { locked=false; user=null; error=null; }); }, child: const Text('Şifreyle yeniden giriş')),
    ])) : user != null ? Column(children: [
      if (biometricsAvailable && !biometricsEnabled)
        ListTile(title: const Text('Face ID / Parmak izi ile aç'),
          trailing: FilledButton(onPressed: _enableBiometrics, child: const Text('Etkinleştir'))),
      Expanded(child: FutureBuilder<String?>(
        future: session.accessToken(),
        builder: (context, snapshot) {
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
          return DashboardScreen(key: ValueKey(snapshot.data), api: session.api,
            token: snapshot.data!, user: user!, onLogout: _logout);
        },
      )),
    ]) : Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 420),
      child: Padding(padding: const EdgeInsets.all(24),
        child: user == null
          ? Column(mainAxisSize: MainAxisSize.min, children: [
              TextField(controller: username, enabled: !busy,
                decoration: const InputDecoration(labelText: 'Kullanıcı adı')),
              TextField(controller: password, obscureText: true, enabled: !busy,
                decoration: const InputDecoration(labelText: 'Şifre'),
                onSubmitted: (_) { if (!busy) _login(); }),
              if (error != null) Text(error!, style: const TextStyle(color: Colors.red)),
              const SizedBox(height: 20),
              FilledButton(onPressed: busy ? null : _login, child: const Text('Giriş yap')),
            ])
          : Column(mainAxisSize: MainAxisSize.min, children: [
              Text('Hoş geldiniz, ${user!['display_name'] ?? user!['username']}'),
              const Text('Giriş doğrulandı. Yönetim ekranları sonraki aşamada.'),
              if (error != null) Text(error!),
              FilledButton(onPressed: busy ? null : _logout, child: const Text('Çıkış yap')),
            ]),
      ),
    )),
  );
}
