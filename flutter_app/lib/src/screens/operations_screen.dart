import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import '../api/policem_api.dart';
import 'pdf_review_screen.dart';
import 'transfer_screen.dart';

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
  String kind='all';
  String period='month';
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
        query: section=='renewals'?{'kind':'upcoming'}:section=='policies'?{'kind':kind,'period':period}:section=='insurers'?{'period':period}:null);
      if(mounted)setState(()=>data=result);
    }catch(e){if(mounted)setState(()=>error='$e');}
    finally{if(mounted)setState(()=>busy=false);}
  }
  Map<String,dynamic> normalize(String path, Map<String,dynamic> input) {
    final data=Map<String,dynamic>.from(input);
    if(data['new_policy'] is Map) {
      data['new_policy']=normalize('/api/policies',Map<String,dynamic>.from(data['new_policy'] as Map));
    }
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
    if(path=='/api/policies'||path=='/api/users'||path.startsWith('/api/policies/')) {
      for(final k in data.keys.toList()) {
        if(data[k]==null||data[k]=='')data.remove(k);
      }
    }
    if(path=='/api/policies'||path.startsWith('/api/policies/')) {
      const required=['agency_id','customer_name','policy_type','policy_number',
        'premium','start_date','end_date','issued_date'];
      for(final k in required){if(data[k]==null||data[k]=='')throw FormatException('$k zorunlu');}
      for(final k in ['start_date','end_date','issued_date']){
        if(DateTime.tryParse('${data[k]}')==null)throw FormatException('$k geçerli tarih olmalı');
      }
      if(DateTime.parse('${data['end_date']}').isBefore(DateTime.parse('${data['start_date']}'))) {
        throw const FormatException('Bitiş tarihi başlangıçtan önce olamaz');
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
  Future<void> form(String title,String path,List<String> fields,{String method='POST',Map? initial}) async{
    final ctrls={for(final f in fields) f:TextEditingController(text:initial?[f]?.toString()??'')};
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
  Future<void> editPolicy(Map item) async {
    await form('Poliçe Düzenle','/api/policies/${item['id']}',
      ['agency_id','branch_id','owner_user_id','seller_user_id','customer_name','policy_type',
       'policy_number','insurer','premium','start_date','end_date','issued_date','tracking','external'],
      method:'PUT',initial:item);
  }
  Future<void> editStaff(Map item) async {
    await form('Personel Düzenle','/api/users/${item['id']}',
      ['display_name','phone','start_date','job_title','active'],method:'PUT',initial:item);
  }
  Future<void> renew(int policyId) async {
    final options=['bekliyor','arandi','teklif','kaybedildi','policelestirildi'];
    final status=await showDialog<String>(context:context,builder:(ctx)=>SimpleDialog(
      title:const Text('Yenileme Durumu'),children:[
        for(final option in options)SimpleDialogOption(
          onPressed:()=>Navigator.pop(ctx,option),child:Text(option)),
        const Padding(padding:EdgeInsets.all(12),
          child:Text('Poliçeleştirildi işlemi yeni poliçe bilgilerini gerektirir.')),
      ]));
    if(status=='policelestirildi') {
      final old=await widget.api.request('GET','/api/policies',widget.token);
      final item=(old as List).cast<Map>().firstWhere((p)=>p['id']==policyId);
      final keys=['agency_id','branch_id','owner_user_id','customer_name','policy_type',
        'policy_number','insurer','premium','start_date','end_date','issued_date'];
      final ctrls={for(final k in keys)k:TextEditingController(text:'${item[k]??''}')};
      final values=await showDialog<Map<String,dynamic>>(context:context,builder:(ctx)=>AlertDialog(
        title:const Text('Yeni Poliçe Bilgileri'),content:SingleChildScrollView(
          child:Column(mainAxisSize:MainAxisSize.min,children:[
            for(final k in keys)TextField(controller:ctrls[k],decoration:InputDecoration(labelText:k))])),
        actions:[TextButton(onPressed:()=>Navigator.pop(ctx),child:const Text('İptal')),
          FilledButton(onPressed:()=>Navigator.pop(ctx,{for(final e in ctrls.entries)e.key:e.value.text}),
            child:const Text('Poliçeleştir'))]));
      if(values==null)return;
      try {
        final policy=normalize('/api/policies',values);
        await submit('/api/renewals/$policyId',{'status':status,'new_policy':policy});
      }catch(e){if(mounted)setState(()=>error='$e');}
    }else if(status!=null){await submit('/api/renewals/$policyId',{'status':status});}
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
        if(section=='policies')...[
          DropdownButton<String>(value:kind,isExpanded:true,items:const [
            DropdownMenuItem(value:'all',child:Text('Tüm poliçeler')),
            DropdownMenuItem(value:'active',child:Text('Aktif')),
            DropdownMenuItem(value:'upcoming',child:Text('Yaklaşan')),
            DropdownMenuItem(value:'offer',child:Text('Teklif')),
            DropdownMenuItem(value:'issued',child:Text('Kesilen'))],
            onChanged:(v){if(v!=null){setState(()=>kind=v);load();}}),
        ],
        if(section=='policies'||section=='insurers')DropdownButton<String>(
          value:period,isExpanded:true,items:const [
            DropdownMenuItem(value:'day',child:Text('Gün')),
            DropdownMenuItem(value:'week',child:Text('Hafta')),
            DropdownMenuItem(value:'month',child:Text('Ay')),
            DropdownMenuItem(value:'year',child:Text('Yıl'))],
          onChanged:(v){if(v!=null){setState(()=>period=v);load();}}),
        if(section=='pdf')FilledButton(onPressed:busy?null:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>PdfReviewScreen(api:widget.api,token:widget.token))),child:const Text('PDF Yükle, Kontrol Et ve Kaydet')),
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
        if(section=='branding'&&manager)FilledButton(
          onPressed:()async{
            final picked=await FilePicker.platform.pickFiles(type:FileType.image,withData:true);
            if(picked==null||picked.files.single.bytes==null)return;
            try{await widget.api.uploadBrandIcon(widget.token,picked.files.single.bytes!,picked.files.single.name);await load();}
            catch(e){if(mounted)setState(()=>error='$e');}
          },child:const Text('Logo Yükle')),
        if(section=='branding'&&manager)OutlinedButton(
          onPressed:()async{try{await widget.api.request('DELETE','/api/branding/icon',widget.token);await load();}
          catch(e){if(mounted)setState(()=>error='$e');}},
          child:const Text('Logoyu Kaldır')),
        if(section=='transfer'&&manager)FilledButton(
          onPressed:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>TransferScreen(api:widget.api,token:widget.token))),
          child:const Text('Devir Oluştur')),
        if(section=='users'&&manager)FilledButton(
          onPressed:()=>form('Personel Ekle','/api/users',['username','display_name','password','role','branch_id','email','phone','job_title']),
          child:const Text('Personel Ekle')),
        if(section!='pdf')TextField(decoration:const InputDecoration(labelText:'Ara',prefixIcon:Icon(Icons.search)),
          onChanged:(v)=>setState(()=>search=v)),
        if(section=='organization'&&data is Map)
          for(final e in (data as Map).entries)Card(child:ExpansionTile(
            title:Text('${e.key}'),children:[
              if(e.value is List)for(final x in e.value as List)
                ListTile(title:Text('${x is Map ? x['name']??x['display_name']??x['id'] : x}')),
              if(e.value is! List)ListTile(title:Text('${e.value}'))])),
        if(section=='insurers'&&data is Map)
          for(final x in ((data as Map)['items'] as List? ?? []))
            if(x is Map)Card(child:ListTile(title:Text('${x['insurer']}'),
              subtitle:Text('${x['count']} poliçe'),
              trailing:x['premium']!=null?Text('${x['premium']} TL'):null)),
        if(section=='branding'&&data is Map)Card(child:ListTile(
          title:Text('${(data as Map)['app_name']}'),
          subtitle:Text('Renk: ${(data as Map)['color']} • Logo: ${(data as Map)['has_icon']==true?'Var':'Yok'}'))),
        if(section=='pdf'&&data is List)SelectableText(const JsonEncoder.withIndent('  ').convert(data)),
        for(final item in items)
          Card(child:ListTile(title:Text(item is Map
              ? '${item['customer_name']??item['display_name']??item['insurer']??item['id']??'Kayıt'}'
              : '$item'),
            subtitle:Text(item is Map?'${item['policy_type']??''}  ${item['end_date']??''}':''),
            onTap:item is Map&&item['id']!=null&&section=='policies'
              ?()=>editPolicy(item)
              :item is Map&&item['id']!=null&&section=='renewals'
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
