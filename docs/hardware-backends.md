# Hardware, backend e runtime locali

JW PubliStudy separa quattro concetti che non sono intercambiabili:

- **architettura host**: l'architettura nativa di Windows;
- **architettura processo**: l'architettura dell'interprete Python/app;
- **dispositivo rilevato**: CPU, GPU o NPU visibile al sistema operativo;
- **backend utilizzabile**: runtime, driver, formato modello, device e probe compatibili insieme.

La presenza di una GPU o NPU non è mai usata come prova sufficiente di accelerazione.

## Rilevamento e validazione

Su Windows l'architettura viene determinata con `IsWow64Process2`, poi `GetNativeSystemInfo`, variabili ambiente e infine `platform.machine()`. Questo distingue, per esempio, un host ARM64 da un processo x64 in emulazione.

GPU e NPU sono inventariate best effort tramite una chiamata PowerShell controllata a CIM/PnP, eseguita nel worker di configurazione e non nel thread grafico. L'inventario non contiene serial number. Per diventare utilizzabile, un backend accelerato deve inoltre avere:

- un asset release compatibile con host e architettura EXE;
- un runtime estratto e validato con `--version`/`--help`;
- un device restituito dal runtime stesso;
- flag effettivamente presenti in `--help`;
- memoria dichiarata sufficiente per l'offload pianificato;
- avvio e health check riusciti.

## Matrice di supporto

| Piattaforma | Backend | Stato | Modello | Note |
|---|---|---|---|---|
| Windows x64 | llama.cpp CPU | supportato dal flusso automatico | GGUF | fallback stabile; AVX2 solo se rilevato e se esiste l'asset |
| Windows x64 + NVIDIA | llama.cpp CUDA | candidato se validato | GGUF | richiede asset, DLL, device runtime e memoria verificati; fallback Vulkan/CPU |
| Windows x64 + AMD/Intel | llama.cpp Vulkan | candidato se validato | GGUF | richiede device runtime e memoria verificati; fallback CPU |
| Windows ARM64 | llama.cpp CPU ARM64 | prioritario | GGUF | runtime nativo preferito sempre all'x64 emulato |
| Windows ARM64 | llama.cpp CPU x64 | fallback emulato | GGUF | usato solo quando le alternative native falliscono o l'asset manca |
| Windows ARM64 + Adreno | OpenCL Adreno | sperimentale e disattivato di default | GGUF | richiede opzione sperimentale e probe completo |
| Windows ARM64 Snapdragon | NPU | inventario; backend non disponibile | provider-specific | non usare GGUF direttamente con Windows ML/HTP; nessun flag NPU inventato |

“Candidato” non significa supporto garantito su ogni driver o scheda. L'app conserva il fallback CPU finché il runtime accelerato non supera validazione e avvio.

## Scelta automatica

Il catalogo legge i metadata JSON della release `latest` ufficiale di `ggml-org/llama.cpp`. Gli URL vengono copiati dagli asset della release, mai costruiti per supposizione. Asset sorgente/debug, architetture errate e pacchetti incompleti sono esclusi.

Il ranking premia architettura nativa, probe riuscito, device elencato, installazione valida e stabilità. Penalizza emulazione, backend sperimentali, driver/DLL mancanti e probe falliti. Un backend NPU richiederebbe insieme runtime, provider, modello compatibile, device, probe e generazione di test riuscita; l'implementazione attuale lo rifiuta con `provider_unavailable`.

Il resource planner usa RAM totale e disponibile, riserva per Windows/app, dimensione GGUF, KV cache, overhead runtime ed emulazione. Con poca memoria riduce context e modello. L'offload GPU viene aggiunto soltanto se il flag è esposto e la memoria del dispositivo è verificabile.

## Runtime side-by-side

```text
<AppData>/runtime/
  llama_cpp_cpu_x86_64_generic/<release>/llama-server.exe
  llama_cpp_cpu_arm64/<release>/llama-server.exe
  llama_cpp_cuda_x86_64/<release>/llama-server.exe
  llama_cpp_vulkan_x86_64/<release>/llama-server.exe
  active.json
```

EXE, DLL e supporti restano insieme. Download, estrazione sicura, staging e validazione precedono l'attivazione. `active.json` è aggiornato solo dopo readiness/health check; un runtime precedente non viene rimosso se il nuovo fallisce.

## Privacy e modalità manuale

`ai_hardware_profile.json` e `ai_backend_selection.json` restano locali e non contengono serial number. Le sole operazioni di rete automatiche sono metadata release e download esplicitamente avviati di runtime/modello. Pubblicazioni, prompt, fonti e cronologia non vengono inviati durante il rilevamento.

La modalità manuale resta disponibile e bypassa il selector soltanto quando abilitata esplicitamente. Un endpoint remoto manuale mantiene l'avviso privacy.

## Matrice di test manuale

| Ambiente | Verifiche specifiche |
|---|---|
| A. Windows x64 Intel senza GPU dedicata | x64 nativo, CPU, modello/context, localhost, health |
| B. Windows x64 AMD senza GPU dedicata | x64 nativo, CPU, fallback e memoria |
| C. Windows x64 + NVIDIA | CUDA device list, DLL, memoria/offload, crash → Vulkan/CPU |
| D. Windows x64 + AMD GPU | Vulkan device list, memoria/offload, crash → CPU |
| E. Windows ARM64 Snapdragon | host/processo, CPU ARM64 prioritaria, NPU mostrata ma non usata |
| F. Windows ARM64 con Python x64 | emulazione rilevata, ARM64 preferito se avviabile, x64 solo fallback |
| G. NPU rilevata senza provider | motivo comprensibile, nessun comando/flag NPU |
| H. RAM disponibile bassa | Small/context ridotto e suggerimento di chiudere app pesanti |

Per ogni ambiente registrare: architetture, emulazione, asset, backend, device, modello, context, stima memoria, comando, health, fallback e UI. Non dichiarare verificato un ambiente hardware non realmente disponibile.
