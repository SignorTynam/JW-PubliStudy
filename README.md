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

## Fasi successive

La fase 4 si occupera della ricerca locale nelle fonti. Nelle fasi successive potranno essere aggiunte citazioni, funzionalita RAG e integrazioni AI locali.
