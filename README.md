# JW PubliStudy

JW PubliStudy e una desktop app locale per studiare pubblicazioni personali in formato PDF/TXT.

L'app permette di:

- importare pubblicazioni personali PDF/TXT;
- estrarre testo da TXT e PDF testuali;
- indicizzare localmente i contenuti in blocchi JSONL;
- cercare nelle fonti indicizzate;
- configurare e usare una chat AI locale gestita dall'app;
- mostrare fonti, riferimenti e citazioni usate nelle risposte.

Il progetto non usa cloud di default, non include OCR, non implementa embeddings, non usa ricerca vettoriale e non fa scraping da siti esterni. Il download automatico e previsto solo per runtime/modelli AI locali configurati nel catalogo dell'app.

## Requisiti

- Python 3.11 o superiore
- Windows come piattaforma principale
- Dipendenze Python indicate in `requirements.txt`

## Installazione

```bash
pip install -r requirements.txt
```

## Avvio

```bash
python main.py
```

Su Windows sono disponibili anche:

```bat
scripts\run_windows.bat
scripts\dev_setup_windows.bat
```

## Fase 1 - Base app

- Finestra principale PySide6
- Sidebar laterale con navigazione
- Pagine Home, Pubblicazioni, Studio / Chat e Impostazioni
- Sistema multilingue basato su file JSON
- Lingue iniziali: Italiano, Albanese e Inglese
- Salvataggio locale della lingua selezionata
- Tema grafico base moderno e pulito

## Fase 2 - Gestione pubblicazioni

- Importazione di file PDF e TXT locali
- Copia dei file importati nella directory dati locale dell'app
- Salvataggio dei metadati in `publications.json`
- Rilevamento duplicati tramite hash SHA-256
- Lista tabellare delle pubblicazioni importate
- Filtri per lingua, tipo file e stato
- Rinomina del titolo visualizzato
- Eliminazione di pubblicazioni e dei file copiati localmente

## Fase 3 - Estrazione testo e indicizzazione locale

- Estrazione testo da file TXT locali
- Estrazione testo da PDF testuali usando `pypdf`
- Nessun OCR: i PDF scannerizzati potrebbero non avere testo estraibile
- Pulizia e normalizzazione del testo estratto
- Creazione di blocchi di testo locali con riferimenti pagina approssimativi per i PDF
- Salvataggio dei blocchi in file JSONL nella directory dati locale dell'app
- Aggiornamento dello stato della pubblicazione: importata, in indicizzazione, indicizzata o errore

## Fase 4 - Ricerca locale nelle fonti

- Ricerca testuale nei chunk indicizzati
- Filtri per lingua e pubblicazione
- Limite configurabile dei risultati
- Risultati ordinati per rilevanza
- Dettaglio del risultato con fonte, file, lingua, pagina o blocco
- Copia del testo completo del chunk
- Copia del riferimento della fonte

La fase 4 non implementa AI, embeddings, ricerca vettoriale, RAG o generazione di risposte.

## Fase 5 - Chat AI locale con fonti

- Usa le pubblicazioni gia indicizzate come fonti
- Recupera i chunk piu rilevanti tramite `SearchService`
- Invia domanda e fonti a un endpoint compatibile OpenAI Chat Completions
- Mostra risposta e fonti usate sotto la risposta
- Salva la cronologia chat localmente
- Permette di copiare ultima risposta e riferimenti/fonti

La fase 5 non scarica modelli, non usa cloud di default, non implementa embeddings e non implementa ricerca vettoriale.

## Fase 6 - Rifinitura MVP e manutenzione

- Versione app centralizzata in `app/version.py`
- Impostazioni riorganizzate in sezioni: lingua, modello AI locale, dati locali, statistiche, manutenzione e informazioni app
- Percorsi dati visibili e apribili dall'interfaccia
- Statistiche libreria: pubblicazioni, stati, chunk e dimensione dati
- Controllo integrita di metadati, file importati, indice, manifest e cronologia chat
- Ricostruzione indice per tutte le pubblicazioni disponibili
- Reset indice senza eliminare PDF/TXT importati
- Cancellazione cronologia chat locale
- Warning privacy se viene configurato un endpoint non locale
- Migliorie UX in Pubblicazioni, Ricerca e Chat
- Script Windows semplici per avvio e setup sviluppo

## AI locale automatica

JW PubliStudy prepara una configurazione AI locale gestita dall'app:

- controlla le caratteristiche del PC;
- consiglia un modello small, medium o large;
- salva i modelli nella directory dati locale, non nella repository;
- avvia un runtime locale su `127.0.0.1` con porta libera;
- usa la chat RAG solo sulle fonti indicizzate;
- mantiene pubblicazioni, domande, indici e cronologia sul computer dell'utente.

La prima configurazione puo richiedere tempo e spazio su disco. In questa fase gli URL dei modelli e del runtime sono placeholder centralizzati: se l'utente preme "Configura automaticamente" senza URL reali, l'app mostra un errore chiaro e non va in crash.

### Per sviluppatori

La nuova architettura si trova in `app/ai/`:

- `hardware_check.py`: rileva sistema, architettura, RAM e spazio libero;
- `model_catalog.py`: catalogo modelli e URL placeholder;
- `model_manager.py`: percorsi, verifica e stato locale dei modelli;
- `download_worker.py`: download asincrono PySide6 con file `.part`;
- `runtime_manager.py`: ricerca/avvio runtime locale su `127.0.0.1`;
- `ai_client.py`: client unico per modalita automatica e manuale;
- `setup_service.py`: coordinamento della configurazione automatica.

Gli URL reali dei modelli vanno inseriti in `app/ai/model_catalog.py`.
L'URL reale del runtime va inserito in `app/ai/runtime_manager.py`.
Il binario runtime bundled puo essere messo in `runtime/`, seguendo `runtime/README.md`.

La modalita manuale resta disponibile nelle Impostazioni avanzate per sviluppo o test con server esterni compatibili OpenAI, per esempio LM Studio o Ollama. Non e la modalita richiesta all'utente finale.

## Dati locali

JW PubliStudy salva i dati nella directory applicativa dell'utente ottenuta tramite `QStandardPaths.AppDataLocation`, fuori dalla repository Git.

Dati principali:

- `publications.json`: metadati delle pubblicazioni importate
- `publications/`: copie locali dei file PDF/TXT importati
- `index/chunks/`: chunk indicizzati in formato JSONL
- `index/index_manifest.json`: manifest opzionale dell'indice
- `chat_history.json`: cronologia chat locale
- `models/`: modelli AI locali scaricati dall'app
- `runtime/`: runtime AI locale scaricato o incluso in futuro
- QSettings: preferenze come lingua e configurazione modello locale

## Privacy

- I file importati, l'indice e la cronologia restano sul computer dell'utente.
- L'app non invia dati online automaticamente.
- La modalita automatica usa solo `127.0.0.1` e non espone il runtime sulla rete locale.
- Domanda e fonti vengono inviate solo al runtime locale automatico o all'endpoint manuale configurato.
- Se l'utente abilita la modalita manuale con endpoint remoto, il trattamento dei dati diventa responsabilita dell'utente.
- L'app non richiede API key e non salva API key.
- Nessun contenuto delle pubblicazioni viene inviato a servizi cloud dall'app.

## Test manuale consigliato

1. Avvia l'app.
2. Cambia lingua.
3. Importa un TXT.
4. Importa un PDF testuale.
5. Indicizza le pubblicazioni.
6. Cerca nella tab Ricerca.
7. Copia un riferimento.
8. Apri Impostazioni e verifica la sezione AI locale.
9. Premi Configura automaticamente senza URL reali e verifica l'errore gestito.
10. Fai una domanda nella chat.
11. Copia la risposta con fonti.
12. Controlla l'integrita.
13. Resetta l'indice.
14. Reindicizza.
15. Cancella la cronologia chat.
16. Attiva la modalita manuale avanzata e testa un endpoint locale compatibile OpenAI, se disponibile.

## Test automatici

```bash
python -m unittest discover -s tests
```

I test coprono catalogo modelli, classificazione hardware, gestione percorsi/verifica modelli e costruzione comando runtime senza usare `0.0.0.0`.

## Limiti attuali

- Le risposte dipendono dalla qualita delle fonti indicizzate.
- Se il modello locale non e avviato, la chat mostra un errore e non genera risposte.
- La ricerca delle fonti e testuale, non semantica.
- Nessun OCR: i PDF scannerizzati senza testo potrebbero non essere indicizzabili.
- Nessun cloud usato di default.
- Gli URL di modelli e runtime sono ancora placeholder finche non vengono sostituiti con risorse reali e checksum.

## Packaging futuro

Per ora l'app si avvia da sorgente con Python.

In futuro potra essere creato un installer Windows. I modelli AI non devono essere inclusi nella repository e non devono essere scaricati automaticamente dall'app.
