# JW PubliStudy runtime

Questa cartella e riservata al runtime AI locale, per esempio `llama-server.exe`.

Non committare file enormi o binari non necessari nel repository. In produzione il runtime potra essere incluso nell'installer Windows oppure scaricato automaticamente nella directory dati locale dell'app.

Il manifest runtime si trova in `app/ai/runtime_manager.py`. Sostituire gli URL placeholder con URL reali e checksum prima di distribuire il download automatico.

