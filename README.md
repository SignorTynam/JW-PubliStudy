# JW PubliStudy

JW PubliStudy e una applicazione desktop locale pensata per aiutare lo studio di pubblicazioni caricate personalmente.

Le prime fasi costruiscono una base locale e navigabile per la libreria di pubblicazioni. L'app non include ancora AI, RAG, lettura del contenuto dei documenti, indicizzazione o ricerca semantica.

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

## Contenuto della fase 1

- Finestra principale PySide6
- Sidebar laterale con navigazione
- Pagine Home, Pubblicazioni, Studio / Chat e Impostazioni
- Sistema multilingue basato su file JSON
- Lingue iniziali: Italiano, Albanese e Inglese
- Salvataggio locale della lingua selezionata
- Tema grafico base moderno e pulito
- Struttura modulare pronta per estensioni future

## Fase 2 - Gestione pubblicazioni

- Importazione di file PDF e TXT locali
- Copia dei file importati nella directory dati locale dell'app
- Salvataggio dei metadati in `publications.json`
- Rilevamento duplicati tramite hash SHA-256
- Lista tabellare delle pubblicazioni importate
- Filtri per lingua, tipo file e stato
- Rinomina del titolo visualizzato
- Eliminazione di pubblicazioni e dei file copiati localmente

La fase 2 non legge ancora il contenuto dei documenti, non estrae testo dai PDF, non esegue OCR, non crea chunk, non calcola embeddings e non indicizza i file.

## Fase 3 - Estrazione testo e indicizzazione locale

- Estrazione testo da file TXT locali
- Estrazione testo da PDF testuali usando `pypdf`
- Nessun OCR: i PDF scannerizzati potrebbero non avere testo estraibile
- Pulizia e normalizzazione del testo estratto
- Creazione di blocchi di testo locali con riferimenti pagina approssimativi per i PDF
- Salvataggio dei blocchi in file JSONL nella directory dati locale dell'app
- Aggiornamento dello stato della pubblicazione: importata, in indicizzazione, indicizzata o errore
- Preparazione per la fase 4, dedicata alla ricerca locale nelle fonti

La fase 3 non implementa AI, embeddings, chat, RAG, ricerca semantica o citazioni generate automaticamente.

## Fase 4 - Ricerca locale nelle fonti

- Ricerca testuale nei chunk indicizzati
- Filtri per lingua e pubblicazione
- Limite configurabile dei risultati
- Risultati ordinati per rilevanza
- Dettaglio del risultato con fonte, file, lingua, pagina o blocco
- Copia del testo completo del chunk
- Copia del riferimento della fonte

La fase 4 non implementa AI, embeddings, ricerca vettoriale, RAG, chat con modello locale o generazione di risposte.

## Fase 5 - Chat AI locale con fonti

- Usa le pubblicazioni gia indicizzate come fonti
- Recupera i chunk piu rilevanti tramite `SearchService`
- Invia domanda e fonti a un endpoint locale compatibile OpenAI Chat Completions
- Mostra risposta e fonti usate sotto la risposta
- Salva la cronologia chat localmente
- Permette di copiare ultima risposta e riferimenti/fonti

La fase 5 non scarica modelli, non usa cloud di default, non fa scraping, non implementa embeddings e non implementa ricerca vettoriale.

## Configurazione modello locale

Per usare la chat bisogna avviare un server locale compatibile con OpenAI Chat Completions, per esempio LM Studio o un server locale equivalente.

Valori predefiniti:

- Endpoint: `http://localhost:1234/v1/chat/completions`
- Modello: `local-model`

Endpoint, modello, temperature, max tokens, timeout e numero di fonti si possono modificare nella pagina Impostazioni.

L'app invia domanda e fonti solo all'endpoint configurato. L'endpoint predefinito e locale (`localhost`). Se l'utente inserisce un endpoint remoto, la responsabilita del trattamento dei dati e dell'utente.

## Limiti attuali

- Le risposte dipendono dalla qualita delle fonti indicizzate
- Se il modello locale non e avviato, la chat non genera risposte
- La ricerca delle fonti e ancora testuale, non semantica
- Nessun OCR
- Nessun cloud usato di default
- Nessun download automatico di modelli

## Fasi successive

Nelle fasi successive potranno essere aggiunti miglioramenti alla qualita del retrieval, ricerca semantica opzionale, embeddings locali e funzioni avanzate di studio.
