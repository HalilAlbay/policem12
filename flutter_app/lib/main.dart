import 'package:flutter/material.dart';
import 'src/api/policem_api.dart';
import 'src/auth/session_manager.dart';

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
      if (mounted) setState(() => user = loggedIn);
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
      if (mounted) setState(() { user = null; error = null; });
    } catch (_) {
      if (mounted) setState(() => error = 'Çıkış işlemi tamamlanamadı.');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }
  @override void dispose() {
    username.dispose(); password.dispose(); session.api.close(); super.dispose();
  }
  @override Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Poliçem')),
    body: Center(child: ConstrainedBox(
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
