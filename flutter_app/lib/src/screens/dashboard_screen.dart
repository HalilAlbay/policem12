import 'package:flutter/material.dart';
import '../api/policem_api.dart';
import 'operations_screen.dart';

class DashboardScreen extends StatefulWidget {
  final PolicemApi api;
  final String token;
  final Map<String, dynamic> user;
  final Future<void> Function() onLogout;
  const DashboardScreen({super.key, required this.api, required this.token,
    required this.user, required this.onLogout});
  @override State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  String period = 'month';
  Map<String, dynamic>? summary;
  List<dynamic> policies = [];
  Map<String, dynamic>? finance;
  String? error;
  bool loading = false;
  String selectedKind = 'active';
  bool get isPartner => widget.user['role'] == 'partner';
  bool get isManager => widget.user['role'] == 'manager';
  @override void initState() { super.initState(); load(); }
  Future<void> load() async {
    setState(() { loading = true; error = null; });
    try {
      final s = await widget.api.getSummary(widget.token, period: period);
      final p = await widget.api.getPolicies(widget.token, kind: selectedKind, period: period);
      Map<String, dynamic>? f;
      if (isPartner) f = await widget.api.getFinance(widget.token, period: period);
      if (mounted) setState(() { summary = s; policies = p; finance = f; });
    } catch (e) {
      if (mounted) setState(() => error = e is ApiException ? e.message : 'Bağlantı hatası');
    } finally { if (mounted) setState(() => loading = false); }
  }
  @override Widget build(BuildContext context) {
    const kinds = {'active':'Aktif', 'upcoming':'Yaklaşan', 'offer':'Teklif',
      'issued':'Kesilen'};
    return Scaffold(
      appBar: AppBar(title: Text('Poliçem • ${widget.user['display_name'] ?? ''}'),
        actions: [
          IconButton(onPressed: loading ? null : load, icon: const Icon(Icons.refresh)),
          IconButton(icon: const Icon(Icons.apps), tooltip:'İşlemler', onPressed:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>OperationsScreen(api:widget.api,token:widget.token,role:'${widget.user['role']}')))),
          IconButton(onPressed: widget.onLogout, icon: const Icon(Icons.logout)),
        ]),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Text(isPartner ? 'Yönetici Özeti' : isManager ? 'Yönetim Paneli' : 'Uzman Paneli',
          style: Theme.of(context).textTheme.headlineSmall),
        DropdownButton<String>(value: period,
          items: const [DropdownMenuItem(value:'day',child:Text('Gün')),
            DropdownMenuItem(value:'week',child:Text('Hafta')),
            DropdownMenuItem(value:'month',child:Text('Ay')),
            DropdownMenuItem(value:'year',child:Text('Yıl'))],
          onChanged: (v) { if (v != null) { setState(() => period=v); load(); } }),
        if (loading) const LinearProgressIndicator(),
        if (error != null) Text(error!, style: const TextStyle(color: Colors.red)),
        if (summary != null)
          Wrap(spacing: 10, runSpacing: 10, children: [
            for (final e in kinds.entries)
              ActionChip(label: Text('${e.value}: ${summary![e.key] ?? 0}'),
                onPressed: () { setState(() => selectedKind=e.key); load(); }),
          ]),
        if (finance != null) Card(child: ListTile(title: const Text('Toplam Prim'),
          subtitle: Text('${finance!['total_premium'] ?? 0} TL'),
          trailing: Text('${finance!['total_count'] ?? 0} poliçe'))),
        const Divider(),
        Text('${kinds[selectedKind]} Poliçeler', style: Theme.of(context).textTheme.titleLarge),
        for (final item in policies)
          if (item is Map)
            Card(child: ListTile(
              title: Text('${item['customer_name'] ?? 'Müşteri'}'),
              subtitle: Text('${item['policy_type'] ?? ''} • ${item['insurer'] ?? ''}'),
              trailing: Text('${item['end_date'] ?? ''}'))),
        if (!loading && policies.isEmpty) const Text('Bu dönemde poliçe bulunamadı.'),
      ]),
    );
  }
}
