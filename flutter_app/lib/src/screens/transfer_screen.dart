import 'package:flutter/material.dart';
import '../api/policem_api.dart';

class TransferScreen extends StatefulWidget {
  final PolicemApi api;
  final String token;
  const TransferScreen({super.key,required this.api,required this.token});
  @override State<TransferScreen> createState()=>_TransferScreenState();
}
class _TransferScreenState extends State<TransferScreen> {
  List<Map<String,dynamic>> staff=[];
  List<Map<String,dynamic>> policies=[];
  int? from,to;
  final selected=<int>{};
  bool all=true,busy=false;
  String? error,result;
  @override void initState(){super.initState();load();}
  Future<void> load() async {
    setState((){busy=true;error=null;});
    try{
      final people=await widget.api.request('GET','/api/transfer/staff',widget.token);
      final records=await widget.api.request('GET','/api/policies',widget.token,query:{'kind':'all'});
      if(!mounted)return;
      setState((){staff=(people as List).map((e)=>Map<String,dynamic>.from(e as Map)).toList();
        policies=(records as List).map((e)=>Map<String,dynamic>.from(e as Map)).toList();});
    }catch(e){if(mounted)setState(()=>error='$e');}
    finally{if(mounted)setState(()=>busy=false);}
  }
  Future<void> transfer() async {
    if(from==null||to==null||from==to){setState(()=>error='Farklı kaynak ve hedef personel seçin');return;}
    final ids=policies.where((p)=>p['owner_user_id']==from).map((p)=>p['id'] as int).toList();
    final chosen=all?ids:ids.where(selected.contains).toList();
    if(chosen.isEmpty){setState(()=>error='Devredilecek poliçe seçilmedi');return;}
    final approved=await showDialog<bool>(context:context,builder:(ctx)=>AlertDialog(
      title:const Text('İş Devrini Onayla'),
      content:Text('${chosen.length} poliçe başka personele aktarılacak. Bu işlem kayıtları silmez. Devam edilsin mi?'),
      actions:[TextButton(onPressed:()=>Navigator.pop(ctx,false),child:const Text('Vazgeç')),
        FilledButton(onPressed:()=>Navigator.pop(ctx,true),child:const Text('Devret'))]));
    if(approved!=true)return;
    setState((){busy=true;error=null;});
    try {
      final response=await widget.api.request('POST','/api/transfer',widget.token,
        body:{'from_user_id':from,'to_user_id':to,'policy_ids':chosen});
      if(mounted)setState(()=>result='${response['count']} poliçe devredildi.');
      selected.clear();await load();
    }catch(e){if(mounted)setState(()=>error='$e');}
    finally{if(mounted)setState(()=>busy=false);}
  }
  @override Widget build(BuildContext context) {
    final source=policies.where((p)=>p['owner_user_id']==from).toList();
    return Scaffold(appBar:AppBar(title:const Text('Personel İş Devri')),
      body:ListView(padding:const EdgeInsets.all(16),children:[
        if(busy)const LinearProgressIndicator(),
        if(error!=null)Text(error!,style:const TextStyle(color:Colors.red)),
        if(result!=null)Text(result!,style:const TextStyle(color:Colors.green)),
        DropdownButtonFormField<int>(value:from,decoration:const InputDecoration(labelText:'Kaynak personel'),
          items:[for(final p in staff)DropdownMenuItem(value:p['id'] as int,child:Text('${p['display_name']}'))],
          onChanged:(v)=>setState((){from=v;selected.clear();})),
        DropdownButtonFormField<int>(value:to,decoration:const InputDecoration(labelText:'Hedef personel'),
          items:[for(final p in staff.where((p)=>p['active']==true&&p['id']!=from))
            DropdownMenuItem(value:p['id'] as int,child:Text('${p['display_name']}'))],
          onChanged:(v)=>setState(()=>to=v)),
        SwitchListTile(title:const Text('Tüm poliçeleri devret'),value:all,
          onChanged:(v)=>setState(()=>all=v)),
        if(!all)for(final p in source)CheckboxListTile(
          title:Text('${p['customer_name']}'),subtitle:Text('${p['policy_number']}'),
          value:selected.contains(p['id']),onChanged:(v)=>setState((){
            if(v==true)selected.add(p['id'] as int);else selected.remove(p['id']);})),
        Text('Kaynak personelde ${source.length} poliçe var.'),
        FilledButton(onPressed:busy?null:transfer,child:const Text('İş Devrini Tamamla')),
      ]));
  }
}
