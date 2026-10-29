import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import '../api/policem_api.dart';

class PdfReviewScreen extends StatefulWidget {
  final PolicemApi api;
  final String token;
  const PdfReviewScreen({super.key,required this.api,required this.token});
  @override State<PdfReviewScreen> createState()=>_PdfReviewScreenState();
}
class _PdfReviewScreenState extends State<PdfReviewScreen> {
  List<PlatformFile> files=[];
  List<Map<String,dynamic>> results=[];
  int index=0;
  bool busy=false;
  String? error;
  final fields=<String,TextEditingController>{};
  final names=['agency_id','branch_id','customer_name','policy_type','policy_number',
    'insurer','premium','start_date','end_date','issued_date'];
  @override void initState(){super.initState();for(final k in names)fields[k]=TextEditingController();}
  @override void dispose(){for(final c in fields.values)c.dispose();super.dispose();}
  void fill(Map<String,dynamic> extracted) {
    for(final k in names)fields[k]!.text='${extracted[k]??''}';
    if(fields['issued_date']!.text.isEmpty)fields['issued_date']!.text=DateTime.now().toIso8601String().substring(0,10);
  }
  Future<void> select() async {
    final chosen=await FilePicker.platform.pickFiles(type:FileType.custom,
      allowedExtensions:['pdf'],allowMultiple:true,withData:true);
    if(chosen==null)return;
    setState((){busy=true;error=null;files=chosen.files;results=[];index=0;});
    try {
      for(final file in files){
        if(file.bytes==null)throw StateError('${file.name}: dosya okunamadı');
        final raw=await widget.api.uploadPdf(widget.token,file.bytes!,file.name);
        if(raw is! List||raw.isEmpty||raw.first is! Map)throw const FormatException('PDF okuma sonucu geçersiz');
        results.add(Map<String,dynamic>.from(raw.first as Map));
      }
      if(results.isNotEmpty)fill(Map<String,dynamic>.from(results.first['fields']??{}));
      if(mounted)setState((){});
    }catch(e){if(mounted)setState(()=>error='$e');}
    finally{if(mounted)setState(()=>busy=false);}
  }
  Future<void> save() async {
    if(index>=results.length)return;
    final result=results[index];
    if(result['error']!=null){setState(()=>error='${result['error']}');return;}
    final payload=<String,dynamic>{};
    for(final k in names){final value=fields[k]!.text.trim();if(value.isNotEmpty)payload[k]=value;}
    for(final k in ['agency_id','branch_id']){
      if(payload[k]!=null){
        final parsed=int.tryParse(payload[k] as String);
        if(parsed==null){setState(()=>error='$k sayısal olmalı');return;}
        payload[k]=parsed;
      }
    }
    final premium=double.tryParse('${payload['premium']??''}'.replaceAll(',','.'));
    if(premium==null||premium<0){setState(()=>error='Geçerli prim girin');return;}
    payload['premium']=premium;
    for(final k in ['agency_id','customer_name','policy_type','policy_number','start_date','end_date','issued_date']){
      if(payload[k]==null){setState(()=>error='$k zorunlu');return;}
    }
    for(final k in ['start_date','end_date','issued_date']){
      if(DateTime.tryParse('${payload[k]}')==null){setState(()=>error='$k YYYY-AA-GG olmalı');return;}
    }
    payload['tracking']=true;
    setState((){busy=true;error=null;});
    try {
      await widget.api.savePdfPolicy(widget.token,files[index].bytes!,files[index].name,payload);
      index++;
      if(index<results.length)fill(Map<String,dynamic>.from(results[index]['fields']??{}));
      else {files=[];results=[];index=0;for(final c in fields.values)c.clear();}
      if(mounted){setState((){});ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content:Text('Poliçe kaydedildi. Yeni PDF yüklemeye hazır.')));}
    }catch(e){if(mounted)setState(()=>error='$e');}
    finally{if(mounted)setState(()=>busy=false);}
  }
  @override Widget build(BuildContext context)=>Scaffold(
    appBar:AppBar(title:const Text('PDF Poliçe Yükle')),
    body:ListView(padding:const EdgeInsets.all(16),children:[
      FilledButton(onPressed:busy?null:select,child:const Text('PDF Seç / Yeni Yükleme')),
      if(busy)const LinearProgressIndicator(),
      if(error!=null)Text(error!,style:const TextStyle(color:Colors.red)),
      if(results.isNotEmpty)...[
        Text('Dosya ${index+1}/${results.length}: ${files[index].name}'),
        if(results[index]['error']!=null)Text('${results[index]['error']}'),
        for(final k in names)TextField(controller:fields[k],
          decoration:InputDecoration(labelText:k)),
        FilledButton(onPressed:busy?null:save,child:const Text('Kontrol Ettim — Poliçeyi Kaydet')),
        TextButton(onPressed:busy?null:(){
          index++;
          if(index<results.length)fill(Map<String,dynamic>.from(results[index]['fields']??{}));
          else{results=[];files=[];index=0;}
          setState((){error=null;});
        },child:const Text('Bu Dosyayı Atla')),
      ],
    ]),
  );
}
