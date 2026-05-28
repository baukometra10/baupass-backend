import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../services/digital_card_repository.dart';

class DigitalPassCard extends StatelessWidget {
  const DigitalPassCard({
    super.key,
    required this.firstName,
    required this.lastName,
    required this.role,
    required this.badgeId,
    required this.companyName,
    required this.validUntil,
    required this.status,
    this.photoData,
    this.dynamicQr,
    this.subcompany,
  });

  final String firstName;
  final String lastName;
  final String role;
  final String badgeId;
  final String companyName;
  final String validUntil;
  final String status;
  final String? photoData;
  final DynamicQrPayload? dynamicQr;
  final String? subcompany;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final name = '$firstName $lastName'.trim();
    final qrValue = dynamicQr?.qrToken ?? badgeId;
    final remaining = dynamicQr?.remainingSec ?? 0;

    return Card(
      elevation: 4,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              theme.colorScheme.primary,
              theme.colorScheme.primaryContainer.withValues(alpha: 0.95),
            ],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.construction, color: Colors.white),
                const SizedBox(width: 8),
                Text(
                  'BAUPASS',
                  style: theme.textTheme.labelLarge?.copyWith(
                    color: Colors.white,
                    letterSpacing: 1.2,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const Spacer(),
                if (remaining > 0)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.white24,
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Text(
                      '${remaining}s',
                      style: const TextStyle(color: Colors.white, fontSize: 12),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: QrImageView(
                    data: qrValue,
                    size: 112,
                    backgroundColor: Colors.white,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _photoAvatar(),
                      const SizedBox(height: 8),
                      Text(
                        name.isEmpty ? 'Mitarbeiter' : name,
                        style: theme.textTheme.titleLarge?.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(role, style: const TextStyle(color: Colors.white70)),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text(companyName, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
            if (subcompany != null && subcompany!.isNotEmpty)
              Text(subcompany!, style: const TextStyle(color: Colors.white70, fontSize: 12)),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(child: _field('Badge-ID', badgeId)),
                Expanded(child: _field('Gültig bis', validUntil)),
                Chip(
                  label: Text(status, style: const TextStyle(fontSize: 11)),
                  backgroundColor: Colors.white,
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _photoAvatar() {
    if (photoData == null || photoData!.isEmpty) {
      return CircleAvatar(
        radius: 28,
        backgroundColor: Colors.white24,
        child: const Icon(Icons.person, color: Colors.white, size: 32),
      );
    }
    try {
      final bytes = base64Decode(photoData!.split(',').last);
      return CircleAvatar(radius: 28, backgroundImage: MemoryImage(bytes));
    } catch (_) {
      return CircleAvatar(
        radius: 28,
        backgroundColor: Colors.white24,
        child: const Icon(Icons.person, color: Colors.white, size: 32),
      );
    }
  }

  Widget _field(String label, String value) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white54, fontSize: 11)),
        Text(value, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
      ],
    );
  }
}
