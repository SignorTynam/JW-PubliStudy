# JW PubliStudy

JW PubliStudy e una applicazione desktop locale pensata per aiutare lo studio di pubblicazioni caricate personalmente.

Questa prima fase crea solo la base navigabile dell'app: non include AI, RAG, caricamento file, database, indicizzazione o ricerca nei documenti.

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

## Fasi successive

Nelle fasi successive potranno essere aggiunti caricamento e gestione pubblicazioni, lettura documenti, indicizzazione locale, ricerca nelle fonti, citazioni, funzionalita RAG e integrazioni AI locali.
