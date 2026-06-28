# JW PubliStudy

JW PubliStudy e una desktop app locale per studiare pubblicazioni personali in formato PDF/TXT.

L'app permette di:

- importare pubblicazioni personali PDF/TXT;
- estrarre testo da TXT e PDF testuali;
- indicizzare localmente i contenuti in blocchi JSONL;
- cercare nelle fonti indicizzate;
- usare una chat AI locale collegata a un endpoint compatibile OpenAI Chat Completions;
- mostrare fonti, riferimenti e citazioni usate nelle risposte.

Il progetto non usa cloud di default, non scarica modelli, non include OCR, non implementa embeddings, non usa ricerca vettoriale e non fa scraping da siti esterni.

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

## Configurazione modello locale

Per usare la chat bisogna avviare un server compatibile OpenAI Chat Completions, per esempio LM Studio o un server locale equivalente.

Valori predefiniti:

- Endpoint: `http://localhost:1234/v1/chat/completions`
- Modello: `local-model`

Endpoint, modello, temperature, max tokens, timeout e numero di fonti si possono modificare nella pagina Impostazioni.

## Dati locali

JW PubliStudy salva i dati nella directory applicativa dell'utente ottenuta tramite `QStandardPaths.AppDataLocation`, fuori dalla repository Git.

Dati principali:

- `publications.json`: metadati delle pubblicazioni importate
- `publications/`: copie locali dei file PDF/TXT importati
- `index/chunks/`: chunk indicizzati in formato JSONL
- `index/index_manifest.json`: manifest opzionale dell'indice
- `chat_history.json`: cronologia chat locale
- QSettings: preferenze come lingua e configurazione modello locale

## Privacy

- I file importati, l'indice e la cronologia restano sul computer dell'utente.
- L'app non invia dati online automaticamente.
- L'endpoint predefinito e `localhost`.
- Domanda e fonti vengono inviate solo all'endpoint configurato.
- Se l'utente configura un endpoint remoto, il trattamento dei dati diventa responsabilita dell'utente.
- L'app non richiede API key e non salva API key.
- Nessun modello AI viene scaricato automaticamente.

## Test manuale consigliato

1. Avvia l'app.
2. Cambia lingua.
3. Importa un TXT.
4. Importa un PDF testuale.
5. Indicizza le pubblicazioni.
6. Cerca nella tab Ricerca.
7. Copia un riferimento.
8. Configura un modello locale.
9. Testa la connessione.
10. Fai una domanda nella chat.
11. Copia la risposta con fonti.
12. Controlla l'integrita.
13. Resetta l'indice.
14. Reindicizza.
15. Cancella la cronologia chat.

## Limiti attuali

- Le risposte dipendono dalla qualita delle fonti indicizzate.
- Se il modello locale non e avviato, la chat mostra un errore e non genera risposte.
- La ricerca delle fonti e testuale, non semantica.
- Nessun OCR: i PDF scannerizzati senza testo potrebbero non essere indicizzabili.
- Nessun cloud usato di default.
- Nessun download automatico di modelli.

## Packaging futuro

Per ora l'app si avvia da sorgente con Python.

In futuro potra essere creato un installer Windows. I modelli AI non devono essere inclusi nella repository e non devono essere scaricati automaticamente dall'app.
