import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../services/tasks_repository.dart';

class LeaveRequestForm extends StatefulWidget {
  const LeaveRequestForm({
    super.key,
    required this.sessionToken,
    required this.tasks,
  });

  final String sessionToken;
  final TasksRepository tasks;

  @override
  State<LeaveRequestForm> createState() => _LeaveRequestFormState();
}

class _LeaveRequestFormState extends State<LeaveRequestForm> {
  String _type = 'urlaub';
  DateTime _start = DateTime.now();
  DateTime _end = DateTime.now();
  final _noteController = TextEditingController();
  final _emailController = TextEditingController();
  bool _submitting = false;
  String? _error;

  static String _formatDate(DateTime dt) {
    final m = dt.month.toString().padLeft(2, '0');
    final d = dt.day.toString().padLeft(2, '0');
    return '${dt.year}-$m-$d';
  }

  Future<void> _pickDate(bool isStart) async {
    final initial = isStart ? _start : _end;
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2020),
      lastDate: DateTime(2035),
    );
    if (picked == null) return;
    setState(() {
      if (isStart) {
        _start = picked;
        if (_end.isBefore(_start)) _end = _start;
      } else {
        _end = picked;
      }
    });
  }

  Future<void> _submit() async {
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.tasks.submitLeaveRequest(
        sessionToken: widget.sessionToken,
        type: _type,
        startDate: _formatDate(_start),
        endDate: _formatDate(_end),
        note: _noteController.text.trim(),
        recipientEmail: _emailController.text.trim().isEmpty
            ? null
            : _emailController.text.trim(),
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message ?? e.errorCode ?? e.toString());
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  void dispose() {
    _noteController.dispose();
    _emailController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('New leave request')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          DropdownButtonFormField<String>(
            value: _type,
            decoration: const InputDecoration(labelText: 'Type', border: OutlineInputBorder()),
            items: const [
              DropdownMenuItem(value: 'urlaub', child: Text('Vacation')),
              DropdownMenuItem(value: 'krank', child: Text('Sick')),
              DropdownMenuItem(value: 'sonstiges', child: Text('Other')),
            ],
            onChanged: _submitting ? null : (v) => setState(() => _type = v ?? 'urlaub'),
          ),
          const SizedBox(height: 12),
          ListTile(
            title: const Text('Start date'),
            subtitle: Text(_formatDate(_start)),
            trailing: const Icon(Icons.calendar_today),
            onTap: _submitting ? null : () => _pickDate(true),
            shape: RoundedRectangleBorder(
              side: BorderSide(color: Theme.of(context).dividerColor),
              borderRadius: BorderRadius.circular(8),
            ),
          ),
          const SizedBox(height: 8),
          ListTile(
            title: const Text('End date'),
            subtitle: Text(_formatDate(_end)),
            trailing: const Icon(Icons.calendar_today),
            onTap: _submitting ? null : () => _pickDate(false),
            shape: RoundedRectangleBorder(
              side: BorderSide(color: Theme.of(context).dividerColor),
              borderRadius: BorderRadius.circular(8),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _noteController,
            decoration: const InputDecoration(
              labelText: 'Note (optional)',
              border: OutlineInputBorder(),
            ),
            maxLines: 3,
            enabled: !_submitting,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _emailController,
            decoration: const InputDecoration(
              labelText: 'Manager email (optional)',
              border: OutlineInputBorder(),
            ),
            keyboardType: TextInputType.emailAddress,
            enabled: !_submitting,
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _submitting ? null : _submit,
            child: _submitting
                ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Submit'),
          ),
        ],
      ),
    );
  }
}
