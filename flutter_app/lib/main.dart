import 'package:flutter/material.dart';
import 'src/api/policem_api.dart';

void main() => runApp(const PolicemApp());

class PolicemApp extends StatelessWidget {
  const PolicemApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Poliçem',
      theme: ThemeData(colorSchemeSeed: const Color(0xFF1755A2)),
      home: const LoginScreen(),
    );
  }
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final username = TextEditingController();
  final password = TextEditingController();
  bool busy = false;
  String? error;

  Future<void> login() async {
    setState(() { busy = true; error = null; });
    try {
      // The backend's authentication contract must be checked before enabling
      // real login. No credentials are sent until that integration is written.
      throw UnimplementedError('API login contract integration pending');
    } catch (_) {
      setState(() => error = 'Giriş bağlantısı henüz uygulanmadı.');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  void dispose() {
    username.dispose();
    password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Poliçem')),
    body: Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 420),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: username, decoration: const InputDecoration(labelText: 'Kullanıcı adı')),
          TextField(controller: password, obscureText: true, decoration: const InputDecoration(labelText: 'Şifre')),
          if (error != null) Text(error!, style: const TextStyle(color: Colors.red)),
          const SizedBox(height: 20),
          FilledButton(onPressed: busy ? null : login, child: const Text('Giriş yap')),
        ]),
      ),
    )),
  );
}
