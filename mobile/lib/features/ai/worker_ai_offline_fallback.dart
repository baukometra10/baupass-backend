/// Local deterministic answers when cloud AI is not configured.
class WorkerAiOfflineFallback {
  static String? answer(String question) {
    final q = question.toLowerCase().trim();
    if (q.isEmpty) return null;

    if (_any(q, ['check-in', 'checkin', 'einchecken', 'einstempeln', 'anwesend'])) {
      return 'Zum Check-in öffnen Sie den Tab „Anwesenheit“. '
          'NFC am Drehkreuz oder manueller Check-in im Geofence. '
          'Standort nur am Einsatzort während der Arbeitszeit.';
    }
    if (_any(q, ['urlaub', 'abwesenheit', 'krank', 'frei'])) {
      return 'Urlaub/Abwesenheit: Aufgaben → Urlaub. Antrag stellen; '
          'Status erscheint dort und per Push, sobald der Arbeitgeber entscheidet.';
    }
    if (_any(q, ['schicht', 'tausch', 'tauschen', 'dienstplan'])) {
      return 'Schichten: Aufgaben → Schichten. Mit „Tausch“ können Sie '
          'eine Schicht anbieten oder Anfragen annehmen/ablehnen/zurückziehen.';
    }
    if (_any(q, ['einsatz', 'plan', 'einsatzplan'])) {
      return 'Einsatzplan: Aufgaben → Einsatzplan. Dort sehen Sie zugewiesene Tage '
          'und können ggf. zusagen oder ablehnen.';
    }
    if (_any(q, ['dokument', 'ausweis', 'pass', 'ablauf'])) {
      return 'Dokumente: Aufgaben → Dokumente. Abgelaufene oder fehlende Unterlagen '
          'werden dort und per Push angezeigt.';
    }
    if (_any(q, ['chat', 'nachricht', 'anruf', 'konferenz', 'telefon'])) {
      return 'Chat und Anrufe: Tab „Chat“. 1:1-Anrufe sind Audio; '
          'Konferenzen können Video nutzen — Kamera ggf. einschalten.';
    }
    if (_any(q, ['datenschutz', 'impressum', 'rechtlich', 'dsgvo'])) {
      return 'Rechtliches: Profil → Rechtliches (Impressum & Datenschutz). '
          'Vor dem Login auch auf dem Anmeldebildschirm.';
    }
    if (_any(q, ['hilfe', 'assist', 'was kannst', 'hallo', 'hi'])) {
      return 'Ich helfe offline bei Check-in, Urlaub, Schichten, Einsatzplan, '
          'Dokumenten, Chat und Rechtlichem. Für KI-Antworten muss der Arbeitgeber '
          'den Assistenten freischalten.';
    }
    return 'Offline-Hinweis: Der KI-Assistent ist nicht konfiguriert. '
        'Fragen Sie nach Check-in, Urlaub, Schichttausch, Einsatzplan, Dokumenten '
        'oder Datenschutz — oder wenden Sie sich an Ihren Arbeitgeber.';
  }

  static bool _any(String q, List<String> keys) => keys.any(q.contains);
}
