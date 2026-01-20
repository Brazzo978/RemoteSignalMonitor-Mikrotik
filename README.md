# RemoteSignalMonitor-Mikrotik

Interfaccia grafica semplice per configurare e monitorare i dati del modem collegato a un router remoto Mikrotik.

## Funzioni attuali (breve descrizione)
- **Connessione SSH guidata**: crea una sessione verso RouterOS indicando host, credenziali, porta e interfaccia LTE.
- **Terminale AT**: invio di comandi AT personalizzati con output in tempo reale.
- **Monitor segnali**: lettura di RSRP/RSRQ/SNR/RSSI e valutazione qualitativa del segnale.
- **Info modem e rete**: parsing di `ATI`, `AT^DEBUG?` e `AT^TEMP?` per operatore, band, canale, PCI, Cell ID, TAC e temperatura.
- **Dettagli avanzati**: elenco bande e canali (LTE/NR) con informazioni approfondite per tecnologia.
- **Sessione controllata**: gestione sessione con token e possibilità di disconnessione pulita.

## Requisiti
- Python 3.9+ consigliato
- Dipendenze Python elencate in `requirements.txt`

## Installazione (configurazione minima)
1. Clona il repository:
   ```bash
   git clone <URL_DEL_REPOSITORY>
   cd RemoteSignalMonitor-Mikrotik
   ```
2. Installa le dipendenze:
   ```bash
   pip install -r requirements.txt
   ```

## Utilizzo
Avvia l'applicazione:
```bash
python app.py
```

Una volta avviata, usa l'interfaccia grafica per configurare la connessione al router Mikrotik e visualizzare i dati del modem.

---

# RemoteSignalMonitor-Mikrotik (English)

Simple GUI to configure and monitor modem data from a remote Mikrotik router.

## Current features (short overview)
- **Guided SSH connection**: opens a RouterOS session by providing host, credentials, port, and LTE interface.
- **AT terminal**: send custom AT commands and view the output in real time.
- **Signal monitoring**: reads RSRP/RSRQ/SNR/RSSI and computes a qualitative signal rating.
- **Modem & network info**: parses `ATI`, `AT^DEBUG?`, and `AT^TEMP?` for operator, bands, channel, PCI, Cell ID, TAC, and temperature.
- **Advanced details**: lists LTE/NR bands and channels with per-technology breakdowns.
- **Session control**: token-based session handling with clean disconnect.

## Requirements
- Python 3.9+ recommended
- Python dependencies listed in `requirements.txt`

## Installation (minimal setup)
1. Clone the repository:
   ```bash
   git clone <URL_DEL_REPOSITORY>
   cd RemoteSignalMonitor-Mikrotik
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage
Start the application:
```bash
python app.py
```

Once running, use the GUI to configure the connection to the Mikrotik router and inspect modem data.
