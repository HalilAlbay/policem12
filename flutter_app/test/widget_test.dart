import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:policem_flutter/main.dart';

void main() {
  testWidgets('Poliçem uygulaması açılır', (WidgetTester tester) async {
    await tester.pumpWidget(const PolicemApp());
    expect(find.text('Poliçem'), findsWidgets);
  });
}
