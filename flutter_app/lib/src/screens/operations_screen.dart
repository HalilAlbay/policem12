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
  Map<String,dynamic> normalize(String path, Map<String,dynamic> input) {
    final data=Map<String,dynamic>.from(input);
    const ints={'agency_id','branch_id','owner_user_id','seller_user_id','from_user_id','to_user_id'};
    for(final k in ints) {
      if(data[k] is String) {
        final v=(data[k] as String).trim();
        data[k]=v.isEmpty?null:int.tryParse(v);
        if(v.isNotEmpty&&data[k]==null)throw FormatException('$k sayı olmalı');
      }
    }
    if(data.containsKey('premium')) {
      data['premium']=double.tryParse('${data['premium']}'.replaceAll(',','.'));
      if(data['premium']==null)throw const FormatException('Prim geçersiz');
    }
    for(final k in ['tracking','external','active']) {
      if(data[k] is String) {
        final v=(data[k] as String).toLowerCase().trim();
        if(v!='true'&&v!='false'&&v!='1'&&v!='0')throw FormatException('$k true/false olmalı');
        data[k]=v=='true'||v=='1';
      }
    }
    if(path.startsWith('/api/renewals/')) {
      if(!['bekliyor','arandi','teklif','policelestirildi','kaybedildi'].contains(data['status'])) {
        throw const FormatException('Geçersiz yenileme durumu');
      }
    }
    if(path=='/api/policies'||path=='/api/users') {
      for(final k in data.keys.toList()) {
        if(data[k]==null||data[k]=='')data.remove(k);
      }
    }
    return data;
  }
  Future<void> submit(String path, Map<String,dynamic> payload,{String method='POST'}) async {
    setState(()=>busy=true);
    try{
      await widget.api.request(method,path,widget.token,body:normalize(path,payload));
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
    // Dialog text controllers are disposed after the route is fully removed.
    if(result!=null)await submit(path,result,method:method);
  }
  Future<void> editStaff(Map item) async {
    await form('Personel Düzenle','/api/users/${item['id']}',
      ['display_name','phone','start_date','job_title','active'],method:'PUT');
  }
  Future<void> renew(int policyId) async {
    final options=['bekliyor','arandi','teklif','kaybedildi'];
    final status=await showDialog<String>(context:context,builder:(ctx)=>SimpleDialog(
      title:const Text('Yenileme Durumu'),children:[
        for(final option in options)SimpleDialogOption(
          onPressed:()=>Navigator.pop(ctx,option),child:Text(option)),
        const Padding(padding:EdgeInsets.all(12),
          child:Text('Poliçeleştirildi işlemi yeni poliçe bilgilerini gerektirir.')),
      ]));
    if(status!=null)await submit('/api/renewals/$policyId',{'status':status});
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
          ['agency_id','branch_id','customer_name','policy_type','policy_number','insurer','premium','start_date','end_date','issued_date']),
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
              ?()=>renew(item['id'] as int)
              :item is Map&&item['id']!=null&&section=='users'
              ?()=>editStaff(item)
              :()=>showDialog<void>(context:context,builder:(ctx)=>AlertDialog(
                title:const Text('Kayıt Detayı'),content:SingleChildScrollView(
                  child:SelectableText(const JsonEncoder.withIndent('  ').convert(item))),
                actions:[TextButton(onPressed:()=>Navigator.pop(ctx),child:const Text('Kapat'))])))),
      ]));
  }
}
