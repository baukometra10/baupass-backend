# Railway: Warum "Token ungueltig" – und was wirklich hilft

## Das Problem

Sie kopieren oft eine **UUID** (z.B. `b8168fd4-ff51-4ec7-8099-f548599d5f4d`).

Das kann sein:

| Was Sie kopiert haben | Woher | Funktioniert mit `railway whoami`? |
|----------------------|-------|-----------------------------------|
| **Project ID** | Cmd+K im Projekt | NEIN – ist keine Anmeldung |
| **Service ID** | Cmd+K beim Service | NEIN |
| **Environment ID** | Cmd+K | NEIN |
| **OAuth Client ID** (`rlwy_oaci_...`) | Applications | NEIN |
| **Account Token** | Account Settings → Tokens | JA |
| **Project Token** | Projekt → Settings → Tokens | NEIN bei whoami – nur fuer `railway up` |

`railway whoami` testet nur einen **Account Token**.  
Wenn Sie eine Project-ID als Token einfügen, kommt immer **Unauthorized** – obwohl die ID im Dashboard "gueltig" ist.

---

## Loesung 1: Ohne Token (empfohlen)

Im Terminal **nur diese 4 Zeilen**, nacheinander:

```
cd C:\Users\u4363\Desktop\baustelle
railway login
railway link
railway up --detach
```

- `railway login` → Browser, einloggen  
- `railway link` → **baupass-production** → Service **web**  
- **Nicht** `railway whoami` mit einer UUID testen

---

## Loesung 2: Echter Account Token

1. Browser: **https://railway.com/account/tokens**  
2. **Create Token** (Name: deploy)  
3. Token kopieren (lang, wird nur einmal gezeigt)  
4. Terminal:

```
cd C:\Users\u4363\Desktop\baustelle
Remove-Item Env:RAILWAY_TOKEN -ErrorAction SilentlyContinue
$env:RAILWAY_API_TOKEN = "HIER_DEN_ECHTEN_ACCOUNT_TOKEN"
railway whoami
```

Wenn Ihr **Name** erscheint → Token ist richtig.  
Dann: `railway link` → `railway up --detach`

---

## Loesung 3: Nur Project Token (ohne whoami)

Nur wenn Sie unter **Projekt → Settings → Tokens** einen Token erstellt haben:

```
cd C:\Users\u4363\Desktop\baustelle
Remove-Item Env:RAILWAY_API_TOKEN -ErrorAction SilentlyContinue
$env:RAILWAY_TOKEN = "PROJECT_TOKEN_VON_TOKENS_SEITE"
railway up -p IHRE_PROJECT_ID -s IHRE_SERVICE_ID --detach
```

- **PROJECT_ID** = Cmd+K → Project ID (das ist OK, aber nur fuer `-p`)  
- **PROJECT_TOKEN** = nur von der Seite **Tokens** im Projekt  

`railway whoami` weglassen – schlaegt mit Project Token immer fehl.
