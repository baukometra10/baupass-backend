import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/session_store.dart';

/// Bottom sheet: company admins / contacts the worker can call.
class CompanyContactsSheet extends StatefulWidget {
  const CompanyContactsSheet({
    super.key,
    required this.session,
    required this.api,
    this.onCallEmployer,
  });

  final WorkerSession session;
  final ApiClient api;
  final Future<void> Function()? onCallEmployer;

  static Future<void> show(
    BuildContext context, {
    required WorkerSession session,
    required ApiClient api,
    Future<void> Function()? onCallEmployer,
  }) {
    return showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (ctx) => CompanyContactsSheet(
        session: session,
        api: api,
        onCallEmployer: onCallEmployer,
      ),
    );
  }

  @override
  State<CompanyContactsSheet> createState() => _CompanyContactsSheetState();
}

class _CompanyContactsSheetState extends State<CompanyContactsSheet> {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _admins = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = await widget.api.getJsonList(
        '/api/worker-app/company-admins',
        bearerToken: widget.session.bearer,
        deviceId: widget.session.deviceId,
      );
      if (!mounted) return;
      setState(() {
        _admins = rows;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message ?? e.toString();
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  String _nameOf(Map<String, dynamic> row) {
    final name = (row['name'] ?? row['displayName'] ?? row['fullName'] ?? '').toString().trim();
    if (name.isNotEmpty) return name;
    final email = (row['email'] ?? '').toString().trim();
    if (email.isNotEmpty) return email;
    return 'Administrator';
  }

  String _roleOf(Map<String, dynamic> row) {
    final role = (row['role'] ?? row['title'] ?? row['jobTitle'] ?? '').toString().trim();
    return role.isNotEmpty ? role : 'Firma / Admin';
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.paddingOf(context).bottom;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(16, 8, 16, 16 + bottom),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Kontakte', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(
              'Arbeitgeber anrufen oder Ansprechpartner wählen.',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
            const SizedBox(height: 16),
            if (widget.onCallEmployer != null)
              ListTile(
                leading: CircleAvatar(
                  backgroundColor: Theme.of(context).colorScheme.primaryContainer,
                  child: Icon(Icons.call_rounded, color: Theme.of(context).colorScheme.onPrimaryContainer),
                ),
                title: const Text('Firma anrufen'),
                subtitle: const Text('Sicherer Sprachkanal'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () async {
                  Navigator.of(context).pop();
                  await widget.onCallEmployer!();
                },
              ),
            if (_loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              )
            else if (_admins.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Text('Keine Admin-Kontakte hinterlegt.'),
              )
            else
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: _admins.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final row = _admins[index];
                    return ListTile(
                      leading: CircleAvatar(
                        child: Text(
                          () {
                            final n = _nameOf(row);
                            return n.isNotEmpty ? n.substring(0, 1).toUpperCase() : 'A';
                          }(),
                        ),
                      ),
                      title: Text(_nameOf(row)),
                      subtitle: Text(_roleOf(row)),
                      trailing: widget.onCallEmployer == null
                          ? null
                          : IconButton(
                              tooltip: 'Anrufen',
                              icon: const Icon(Icons.call_rounded),
                              onPressed: () async {
                                Navigator.of(context).pop();
                                await widget.onCallEmployer!();
                              },
                            ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}
