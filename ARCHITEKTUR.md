# CoopManager — Architektur-Konzept

Stand: 2026-08-10 · Status: Entwurf / Diskussionsgrundlage
Ziel: Mitgliederverwaltung für Genossenschaften. Umfang: Mitglieder-Stammdaten, Anteile & Zahlungen, Auth & Rollen, Dokumente & Reports.

Dieses Dokument ist ein Vorschlag zur Diskussion. Es wird nichts implementiert, solange nicht abgestimmt.

**Grundsatzentscheidungen (abgestimmt):**

- **Kein ORM.** Persistenz über raw SQL. Start mit `sqlite3`, Umstieg auf PostgreSQL später.
- **Event Sourcing durchgehend.** Alle Fachdaten werden als Events gespeichert; Zustand ist eine abgeleitete Projektion.
- **Vertical Slices.** Struktur nach Fachkomponente, nicht nach technischer Schicht.
- **DSGVO via Crypto-Shredding.** Personenbezogene Daten (PII) in Events verschlüsselt pro Mitglied; „Vergessen" = Schlüssel löschen.

---

## 1. Stack

| Bereich | Empfehlung | Begründung |
|---|---|---|
| Web-Framework | Flask (App-Factory + Blueprints je Slice) | Bereits gesetzt, passt für überschaubare Fachanwendung |
| DB-Zugriff | raw SQL über `sqlite3` (Std-Lib) → später `psycopg` (PostgreSQL) | Bewusst kein ORM; volle Kontrolle über Event Store & Projektionen |
| Datenbank | SQLite (Start) → PostgreSQL (Prod) | Schneller Start; Postgres für Mehrbenutzer, `jsonb`, Backups |
| Persistenz-Modell | Event Store (append-only) + abgeleitete Read-Models | Historie, Prüfungssicherheit, Audit-Trail intrinsisch |
| Auth | Flask-Login + Werkzeug-Passworthashes | Session-basiert, ausreichend für internes Tool |
| Krypto (Shredding) | `cryptography` (AES-GCM), Schlüssel pro Mitglied | DSGVO-Löschung bei unveränderlichen Events |
| Formulare/Validierung | Flask-WTF (WTForms) + CSRF | Serverseitige Validierung, CSRF-Schutz |
| Templates | Jinja2 + Bootstrap o. ä. | Server-rendered, keine SPA nötig |
| Config | eigene Config-Klasse (Dev/Test/Prod) aus Env | 12-Factor, `.env` + Env-Vars sauber trennen |
| PDF/Reports | WeasyPrint (HTML→PDF) oder ReportLab | Bescheinigungen, Beitrittserklärungen |
| Tests | pytest | Event-Handling & Projektionen von Anfang an testen |

Kein SQLAlchemy, kein Alembic, kein Flask-Migrate. Schema-Migrationen betreffen nur die Event-Store-Tabelle (klein, stabil) und die Read-Model-Tabellen (jederzeit aus Events neu berechenbar). Der Umstieg SQLite → PostgreSQL wird dadurch entschärft.

Hinweis zu Python 3.14: Der Stack ist jetzt deutlich schlanker (Std-Lib `sqlite3`, wenige Wheels). `cryptography`, `psycopg` und WeasyPrint vor Festlegung kurz auf 3.14-Wheels prüfen; sonst ist 3.12/3.13 der risikoärmere Boden.

---

## 2. Event Sourcing — Grundprinzip

Der Ablauf jeder fachlichen Änderung:

1. **Command** — eine Absicht (`RegisterMember`, `SubscribeShares`, `RecordPayment`). Wird validiert, führt aber selbst nichts aus.
2. **Aggregate** — der Konsistenz-Wächter (`Member`, `ShareAccount`). Wird durch Abspielen seiner bisherigen Events aus dem Stream rekonstruiert, prüft das Command gegen den aktuellen Zustand und erzeugt neue Events.
3. **Event** — eine Tatsache in der Vergangenheit (`MemberRegistered`, `SharesSubscribed`, `PaymentRecorded`). Unveränderlich, append-only.
4. **Projektion / Read-Model** — abgeleitete, abfragbare Sicht (Mitgliederliste, Anteilsregister, Saldo). Wird durch Abspielen der Events aufgebaut und ist jederzeit **komplett neu berechenbar**.

Schreibseite (Command → Event → Store) und Leseseite (Projektion → Read-Model) sind getrennt (CQRS). Da alles in einem Flask-Prozess läuft, werden Projektionen zunächst **synchron** nach dem Append aktualisiert — keine echte eventual consistency, kein Message-Broker nötig. Bei späterer Skalierung lässt sich das entkoppeln.

---

## 3. Event Store (Schema)

Eine einzige append-only Tabelle. Identisch nutzbar in SQLite und Postgres:

```sql
-- Event store: append-only, single source of truth.
CREATE TABLE events (
    global_seq  INTEGER PRIMARY KEY AUTOINCREMENT,  -- global order for projection replay
    stream_id   TEXT    NOT NULL,                    -- aggregate id, e.g. "member-<uuid>"
    version     INTEGER NOT NULL,                    -- per-stream version, starts at 1
    event_type  TEXT    NOT NULL,                    -- e.g. "MemberRegistered"
    schema_ver  INTEGER NOT NULL DEFAULT 1,          -- payload schema version (for upcasting)
    payload     TEXT    NOT NULL,                    -- JSON; TEXT in sqlite, jsonb in postgres
    metadata    TEXT    NOT NULL,                    -- JSON: correlation id, acting user, ip
    created_at  TEXT    NOT NULL,                    -- ISO-8601 UTC timestamp
    UNIQUE (stream_id, version)                      -- optimistic concurrency guard
);

CREATE INDEX idx_events_stream ON events (stream_id, version);
```

Zwei Punkte, die von Anfang an tragen müssen:

**Optimistische Nebenläufigkeit.** Ein Command lädt den Stream, kennt dessen aktuelle `version` N und schreibt das neue Event mit `version = N+1`. Die `UNIQUE (stream_id, version)`-Bedingung lässt einen zweiten, gleichzeitigen Schreiber scheitern → Retry. Funktioniert in SQLite und Postgres gleich.

**Event-Versionierung (Upcasting).** `schema_ver` erlaubt spätere Payload-Änderungen. Beim Laden werden alte Events durch *Upcaster*-Funktionen in die aktuelle Form gebracht, bevor das Aggregate sie sieht. So bleiben Jahre alte Events lesbar, ohne den Store zu migrieren.

Beim Umstieg auf Postgres: `payload`/`metadata` → `jsonb`, `global_seq` → `BIGINT GENERATED ALWAYS AS IDENTITY`. Sonst bleibt das Modell gleich.

---

## 4. Projektionen / Read-Models

Read-Models sind normale SQL-Tabellen, ausschließlich von Projektionen beschrieben, nie direkt fachlich verändert.

- Jede Projektion führt einen **Checkpoint** (`last_global_seq`), damit sie inkrementell nur neue Events verarbeitet.
- Jede Projektion hat eine **Rebuild-Funktion**: Read-Model leeren, alle Events ab `global_seq = 0` erneut abspielen. Pflicht — das ist die Absicherung gegen Projektionsfehler und der Grund, warum Schema-Änderungen an Read-Models harmlos sind.
- Beispiele: `member_list` (Nr., Name, Status), `member_detail`, `share_register`, `payment_ledger`, `share_balance` (Saldo = Summe der Bewegungen).

```sql
-- Projection checkpoint: how far each read-model has consumed the event stream.
CREATE TABLE projection_checkpoints (
    projection      TEXT    NOT NULL PRIMARY KEY,
    last_global_seq INTEGER NOT NULL DEFAULT 0
);
```

---

## 5. Crypto-Shredding (DSGVO)

Events sind unveränderlich — löschen kann man sie nicht. Personenbezogene Daten (PII: Name, Adresse, E-Mail, Telefon, Geburtsdatum) werden deshalb **verschlüsselt** in den Event-Payload gelegt, mit einem Schlüssel **pro Mitglied**.

```sql
-- Per-member encryption keys. This table IS mutable/deletable — that is the point.
-- "Right to be forgotten" = delete the row; ciphertext in events becomes permanently unreadable.
CREATE TABLE member_keys (
    member_id   TEXT PRIMARY KEY,
    key         BLOB NOT NULL,        -- AES-GCM key, per member
    created_at  TEXT NOT NULL,
    erased_at   TEXT                  -- set when key is destroyed
);
```

Regeln:

- Nur PII-Felder werden verschlüsselt; fachlich-nicht-personenbezogene Felder (Status, Datum, Anteilsanzahl, Beträge) bleiben klar, damit Projektionen und Auswertungen weiter funktionieren.
- „Mitglied vergessen" = `member_keys`-Zeile löschen (`erased_at` setzen, `key` nullen). Danach sind die PII-Felder aller Events dieses Mitglieds dauerhaft unlesbar, der Event-Stream bleibt strukturell intakt.
- Auskunftspflicht (Datenexport pro Mitglied) wird über eine dedizierte Projektion bedient, solange der Schlüssel existiert.
- Der Master-/Wrapping-Key (zum Schutz der `member_keys` selbst) gehört in Env/Secrets-Store, nicht in die DB.

Offene Detailfrage: Aufbewahrungspflichten (Genossenschaft/Steuer) vs. Löschpflicht — welche Felder müssen ggf. auch nach „Vergessen" in aggregierter, anonymer Form erhalten bleiben.

---

## 6. Projektstruktur (Vertical Slices)

Struktur nach Fachkomponente. Jeder Slice besitzt seine Commands, Events, Aggregates, Projektionen, Routes und Templates. Querschnitts-Infrastruktur liegt bewusst dünn in `shared/`.

```
src/coopman/
├── __init__.py            # create_app() factory, blueprint registration
├── config.py              # Config classes (Dev/Prod/Test) from env
├── main.py                # entry point -> create_app(); wsgi target
├── shared/                # cross-cutting infrastructure (keep thin)
│   ├── db.py              # sqlite connection now; swappable for psycopg later
│   ├── eventstore.py      # append(), load_stream(), read_all(from_seq)
│   ├── projection.py      # base: checkpoint handling, rebuild()
│   ├── crypto.py          # per-member key mgmt, encrypt/decrypt PII
│   ├── messagebus.py      # dispatch commands -> handlers, events -> projections
│   └── auth.py            # login, @require_role(...) decorator
├── members/               # slice: Mitglieder-Stammdaten
│   ├── domain.py          # Member aggregate, commands, events
│   ├── handlers.py        # command handlers
│   ├── projections.py     # member_list, member_detail read-models
│   ├── routes.py          # Flask blueprint (thin: request in, response out)
│   └── templates/
├── shares/                # slice: Anteile (event-sourced)
├── payments/              # slice: Zahlungen (Ledger)
├── auth_users/            # slice: Login-Konten & Rollen
├── documents/             # slice: Upload/Generierung
└── reports/               # slice: Listen, Exporte (liest Read-Models)
tests/
```

Prinzip: Routes bleiben dünn. Fachlogik lebt in den Aggregates/Handlern des jeweiligen Slice. Slices kennen einander nicht direkt — Kommunikation nur über den Event-Store bzw. den Message-Bus.

---

## 7. Fachdomänen als Slices

Zentrale Unterscheidung, unverändert wichtig: **`User` (Login-Konto) ≠ `Member` (Genossenschaftsmitglied)**. Ein Vorstands-User ist kein Mitglied im fachlichen Sinn; ein Mitglied hat u. U. keinen Login. Getrennte Slices (`auth_users` vs. `members`).

**members** — Stammdaten. Events: `MemberRegistered`, `MemberDataCorrected`, `MemberStatusChanged` (`interessent` → `aktiv` → `gekündigt` → `ausgeschieden`), `MemberErased` (Marker, wenn Schlüssel gelöscht wird). PII im Payload verschlüsselt. Mitgliedsnummer ist fachlicher Schlüssel, getrennt von der `stream_id`.

**shares** — Anteile je Mitglied. Events: `SharesSubscribed`, `SharesTerminated`. Anteilsart/Nennwert (`ShareType`) als eigene, kleine Referenzdaten — kann als einfache Projektion oder eigener Stream geführt werden.

**payments** — Ein-/Auszahlungen als **Ledger** (Bewegungen, nie überschreibbarer Saldo). Events: `PaymentRecorded`, `PaymentReversed`. Der Saldo ist die Projektion `share_balance`. Das ist die natürlichste ES-Domäne im ganzen System.

**Beträge:** JSON kennt keinen Decimal-Typ. Geldbeträge deshalb als **ganzzahlige Minor-Units (Cent)** im Payload speichern, **niemals Float**. Erst bei der Anzeige/Berechnung in Decimal wandeln.

**auth_users** — Login & Rollen. Events: `UserCreated`, `PasswordChanged`, `RoleAssigned`, `UserDeactivated`. Rollen (`vorstand`, `verwaltung`, `mitglied`) im Code prüfen (`@require_role(...)`), nicht in Templates. Optional `member_id`-Verknüpfung für Self-Service.

**documents** — Metadaten event-sourced (`DocumentGenerated`, `DocumentUploaded`), die Dateien selbst im Dateisystem/Objektspeicher, nur Referenz im Event.

**reports** — rein lesend: Mitgliederliste, Anteilsregister, Zeichnungsjournal als Ausgabe (CSV/XLSX/PDF) aus den Read-Models. Nicht persistent, außer Archivierungspflicht.

---

## 8. Querschnitts-Themen

**Konfiguration / Secrets.** Getrennte Config-Klassen Dev/Test/Prod. `SECRET_KEY` und Crypto-Master-Key in Prod aus Env-Vars, nie aus Datei. `.env` nur lokal (siehe Findings).

**Validierung & Sicherheit.** CSRF (Flask-WTF) für alle Formulare. Passwort-Hashing mit Werkzeug (scrypt/pbkdf2). Serverseitige Validierung immer. Command-Validierung zusätzlich im Aggregate.

**Audit-Trail.** Kommt bei ES „gratis": jedes Event trägt in `metadata` den handelnden User, Zeitpunkt und Korrelations-ID. „Wer hat wann was geändert" ist der Event-Stream selbst.

**Tests.** Der ES-typische Stil: *Given* (bisherige Events) → *When* (Command) → *Then* (erwartete neue Events). Dazu Projektions-Tests (Events rein, Read-Model-Zustand raus) und Rollen-Zugriffsschutz. In-Memory-SQLite für schnelle Läufe.

**Schema-Migrationen.** Nur zwei Dinge migrieren: die `events`-Tabelle (selten, additiv) und Read-Model-Tabellen (per Rebuild aus Events). Kein Alembic nötig — schlichte, versionierte SQL-Skripte reichen.

---

## 9. Sofort-Findings zum aktuellen Scaffolding

Konkrete Verbesserungsvorschläge zum Ist-Zustand (keine Änderung durchgeführt):

1. **`pyproject.toml` — kaputter Entry-Point.** `coopmanager = "main"` ist ungültig. Format muss `modul:funktion` sein, z. B. `coopmanager = "coopman.main:main"`. Aktuell existiert weder Modul noch Funktion — der Console-Script würde fehlschlagen.

2. **`.env.example` enthält echten Secret.** Datei trägt denselben `SECRET_KEY` wie `.env`, und `.gitignore` (`**/.env`) greift **nicht** für `.env.example` → der Key würde eingecheckt. Platzhalter setzen (`SECRET_KEY=change-me-generate-a-random-key`), aktuellen Key als kompromittiert behandeln und neu erzeugen.

3. **`src/coopman/__init__.py` ist leer.** Hier gehört die `create_app()`-Factory hin.

4. **Kein Persistenz-Layer.** Nur Flask als Dependency. Für das ES-Fundament fehlen `shared/eventstore.py`, `shared/db.py`, `shared/crypto.py` sowie `cryptography` als Dependency.

5. **README unvollständig.** Installation/Usage leer, Tippfehler „there members" → „their members".

6. **Python 3.14** — Wheel-Verfügbarkeit von `cryptography`/`psycopg`/WeasyPrint prüfen (§1).

---

## 10. Vorgeschlagene Reihenfolge (falls Umsetzung startet)

1. **Fundament:** `create_app()`, Config-Klassen, `shared/db.py` (SQLite), `shared/eventstore.py` (append/load/read_all mit optimistischer Nebenläufigkeit), `shared/crypto.py` (Key-Store + encrypt/decrypt), `shared/projection.py` (Checkpoint + Rebuild), `shared/messagebus.py`. Entry-Point reparieren.
2. **auth_users-Slice:** User/Rollen als Events, Login/Logout, `@require_role`. Zugriffsschutz-Gerüst steht früh.
3. **members-Slice:** Registrierung/Korrektur/Status als Events, PII-Verschlüsselung, Projektionen (Liste/Detail), Formulare. Crypto-Shredding-Pfad durchtesten.
4. **shares-Slice:** Zeichnung/Kündigung als Events.
5. **payments-Slice:** Ledger, Saldo-Projektion, Given/When/Then-Tests.
6. **documents & reports:** Generierung/Upload, Exporte (CSV/XLSX/PDF) aus Read-Models.
7. **Durchgängig:** Tests, README pflegen, Postgres-Umstieg vorbereiten.

Offene Punkte vor Schritt 1: Geldbeträge als Cent bestätigen · ab wann PostgreSQL · Deployment-Ziel (eigener Server, Container, Hosting?) · Aufbewahrungspflicht vs. Löschpflicht bei Crypto-Shredding (welche Felder überleben anonymisiert) · brauchen Mitglieder Self-Service-Login.
