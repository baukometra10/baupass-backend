/// Shared API → local device time formatting for the worker app.
DateTime? parseApiInstant(String? raw) {
  final value = (raw ?? '').trim();
  if (value.isEmpty) return null;
  final parsed = DateTime.tryParse(value);
  if (parsed == null) return null;
  return parsed.isUtc ? parsed.toLocal() : parsed.toLocal();
}

String _two(int n) => n.toString().padLeft(2, '0');

/// Local wall-clock time `HH:mm`.
String formatTimeLocal(String? raw, {String fallback = ''}) {
  final local = parseApiInstant(raw);
  if (local == null) return fallback.isNotEmpty ? fallback : (raw ?? '');
  return '${_two(local.hour)}:${_two(local.minute)}';
}

/// Local date+time `dd.MM.yyyy HH:mm`.
String formatDateTimeLocal(String? raw, {String fallback = ''}) {
  final local = parseApiInstant(raw);
  if (local == null) return fallback.isNotEmpty ? fallback : (raw ?? '');
  return '${_two(local.day)}.${_two(local.month)}.${local.year} ${_two(local.hour)}:${_two(local.minute)}';
}

/// Compact local stamp for lists: `dd.MM. HH:mm`.
String formatShortDateTimeLocal(String? raw, {String fallback = ''}) {
  final local = parseApiInstant(raw);
  if (local == null) return fallback.isNotEmpty ? fallback : (raw ?? '');
  return '${_two(local.day)}.${_two(local.month)}. ${_two(local.hour)}:${_two(local.minute)}';
}
