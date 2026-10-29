import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import '../api/policem_api.dart';

class OperationsScreen extends StatefulWidget {
  final PolicemApi api;
  final String token;
  final String role;
  const OperationsScreen({super.key,required this.api,required this.token,required this.role});
  @override State<OperationsScreen> createState()=>_OperationsScreenState();
}

class _OperationsScreenState extends State<OperationsScreen> {
  String section='policies';
  String search='';
  String? error;
  bool busy=false;
  dynamic data;
  final sections=<String,String>{
    'policies':'Poliçeler', 'renewals':'Yenilemeler', 'pdf':'PDF Okuma',
    'insurers':'Sigorta Şirketleri', 'reminders':'Hatırlatmalar',
    'transfer':'Poliçe Devri', 'users':'Personel', 'organization':'Acente ve Şubeler',
    'branding':'Uygulama Ayarları',
  };
  @override void initState(){super.initState();load();}
  bool get manager=>widget.role=='manager'||widget.role=='partner';
  bool get partner=>widget.role=='partner';
  Future<void> load() async {
    setState(() {busy=true;error=null;});
    try {
      final path={
        'policies':'/api/policies','renewals':'/api/policies',
        'insurers':'/api/insurers/summary','reminders':'/api/reminders',
        'transfer':'/api/transfer/staff','users':'/api/users/manage',
        'organization':'/api/organization','branding':'/api/branding'
      }[section];
      final result=path==null ? null : await widget.api.request('GET',path,widget.token,
        query: section=='renewals'?{'kind':'upcoming'}:null);
      if(mounted)setState(()=>data=result);
    }catch(e){if(mounted)setState(()=>error='$e');}
    finally{if(mounted)setState(()=>busy=false);}
  }
  Future<void> submit(String path, Map<String,dynamic> payload,{String method='POST'}) async {
    setState(()=>busy=true);
    try{
      await widget.api.request(method,path,widget.token,body:payload);
      await load();
      if(mounted)ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content:Text('Kaydedildi')));
    }catch(e){if(mounted)setState(()=>error='$e');}
    finally{if(mounted)setState(()=>busy=false);}
  }
  Future<void> form(String title,String path,List<String> fields,{String method='POST'}) async{
    final ctrls={for(final f in fields) f:TextEditingController()};
    final result=await showDialog<Map<String,dynamic>>(context:context,builder:(ctx)=>AlertDialog(
      title:Text(title),content:SingleChildScrollView(child:Column(mainAxisSize:MainAxisSize.min,
        children:[for(final f in fields)TextField(controller:ctrls[f],
          decoration:InputDecoration(labelText:f))])),
      actions:[TextButton(onPressed:()=>Navigator.pop(ctx),child:const Text('İptal')),
        FilledButton(onPressed:()=>Navigator.pop(ctx,{
          for(final e in ctrls.entries)e.key:e.value.text}),child:const Text('Kaydet'))]));
    for(final c in ctrls.values){c.dispose();}
    if(result!=null)await submit(path,result,method:method);
  }
  Future<void> pdf() async {
    final picked=await FilePicker.platform.pickFiles(type:FileType.custom,
      allowedExtensions:['pdf'],withData:true,allowMultiple:true);
    if(picked==null)return;
    setState(()=>busy=true);
    try{
      final results=[];
      for(final f in picked.files){
        if(f.bytes==null)continue;
        results.add(await widget.api.uploadPdf(widget.token,f.bytes!,f.name));
      }
      if(mounted)setState(()=>data=results);
    }catch(e){if(mounted)setState(()=>error='$e');}
    finally{if(mounted)setState(()=>busy=false);}
  }
  @override Widget build(BuildContext context){
    final allowed=sections.entries.where((e)=>manager||!['transfer','users','organization','branding'].contains(e.key)).toList();
    final items=data is List ? (data as List).where((x)=>jsonEncode(x).toLowerCase().contains(search.toLowerCase())).toList():<dynamic>[];
    return Scaffold(appBar:AppBar(title:const Text('Poliçem İşlemleri')),
      body:ListView(padding:const EdgeInsets.all(16),children:[
        DropdownButton<String>(value:section,isExpanded:true,
          items:[for(final e in allowed)DropdownMenuItem(value:e.key,child:Text(e.value))],
          onChanged:(v){if(v!=null){setState((){section=v;data=null;search='';});load();}}),
        if(busy)const LinearProgressIndicator(),
        if(error!=null)Text(error!,style:const TextStyle(color:Colors.red)),
        if(section=='pdf')FilledButton(onPressed:busy?null:pdf,child:const Text('PDF dosyalarını seç ve oku')),
        if(section=='policies')FilledButton(onPressed:()=>form('Yeni Poliçe','/api/policies',
          ['customer_name','policy_type','policy_number','insurer','premium','start_date','end_date','issued_date']),
          child:const Text('Poliçe Ekle')),
        if(section=='organization'&&manager)...[
          if(partner)FilledButton(onPressed:()=>form('Acente Ekle','/api/agencies',['name']),child:const Text('Acente Ekle')),
          FilledButton(onPressed:()=>form('Şube Ekle','/api/branches',['agency_id','name']),child:const Text('Şube Ekle')),
        ],
        if(section=='branding'&&manager)FilledButton(
          onPressed:()=>form('Marka Ayarları','/api/branding',['app_name','color'],method:'PUT'),
          child:const Text('Uygulama Adı ve Rengi')),
        if(section=='transfer'&&manager)FilledButton(
          onPressed:()=>form('Poliçe Devri','/api/transfer',['from_user_id','to_user_id']),
          child:const Text('Devir Oluştur')),
        if(section=='users'&&manager)FilledButton(
          onPressed:()=>form('Personel Ekle','/api/users',['username','display_name','password','role','branch_id','email','phone','job_title']),
          child:const Text('Personel Ekle')),
        if(section!='pdf')TextField(decoration:const InputDecoration(labelText:'Ara',prefixIcon:Icon(Icons.search)),
          onChanged:(v)=>setState(()=>search=v)),
        if(data is Map)SelectableText(const JsonEncoder.withIndent('  ').convert(data)),
        if(section=='pdf'&&data is List)SelectableText(const JsonEncoder.withIndent('  ').convert(data)),
        for(final item in items)
          Card(child:ListTile(title:Text(item is Map
              ? '${item['customer_name']??item['display_name']??item['insurer']??item['id']??'Kayıt'}'
              : '$item'),
            subtitle:Text(item is Map?'${item['policy_type']??''}  ${item['end_date']??''}':''),
            onTap:item is Map&&item['id']!=null&&section=='renewals'
              ?()=>form('Yenileme Durumu','/api/renewals/${item['id']}',['status'])
              :()=>showDialog<void>(context:context,builder:(ctx)=>AlertDialog(
                title:const Text('Kayıt Detayı'),content:SingleChildScrollView(
                  child:SelectableText(const JsonEncoder.withIndent('  ').convert(item))),
                actions:[TextButton(onPressed:()=>Navigator.pop(ctx),child:const Text('Kapat'))])))),
      ]));
  }
}
