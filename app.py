import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import re

from flask import Flask, jsonify, request
import paramiko


@dataclass
class SSHSession:
    token: str
    client: paramiko.SSHClient
    interface: str
    host: str
    username: str
    port: int
    created_at: float
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, SSHSession] = {}
        self._lock = threading.Lock()

    def add(self, client: paramiko.SSHClient, interface: str, host: str, username: str, port: int) -> SSHSession:
        token = secrets.token_urlsafe(32)
        session = SSHSession(
            token=token,
            client=client,
            interface=interface,
            host=host,
            username=username,
            port=port,
            created_at=time.time(),
        )
        with self._lock:
            self._sessions[token] = session
        return session

    def get(self, token: str) -> Optional[SSHSession]:
        with self._lock:
            return self._sessions.get(token)

    def remove(self, token: str) -> None:
        with self._lock:
            session = self._sessions.pop(token, None)
        if session:
            try:
                session.client.close()
            except Exception:
                pass

    def cleanup(self, max_age_seconds: int = 1800) -> None:
        cutoff = time.time() - max_age_seconds
        to_remove = []
        with self._lock:
            for token, session in list(self._sessions.items()):
                if session.created_at < cutoff:
                    to_remove.append(token)
        for token in to_remove:
            self.remove(token)


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
sessions = SessionStore()


HTML_PAGE = """<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Remote Signal Monitor</title>
    <link
      href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
      rel="stylesheet"
      integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH"
      crossorigin="anonymous"
    />
    <style>
      body { background: #f5f7fb; }
      .card-icon { width: 58px; height: 58px; }
      .terminal { background: #0b0d0e; color: #3dff8f; font-family: "Fira Code", monospace; min-height: 260px; max-height: 380px; overflow-y: auto; border-radius: 6px; padding: 1rem; }
      .panel-title { letter-spacing: 0.5px; }
      .status-pill { padding: 0.35rem 0.75rem; border-radius: 999px; font-weight: 600; }
      .bg-dim { background: #eef2f7; }
      .signal-table th { width: 38%; }
      .tab-pane { display: none; }
      .tab-pane.active { display: block; }
      .nav-tabs .nav-link { border: none; }
      .nav-tabs .nav-link.active { border-bottom: 2px solid #0d6efd; font-weight: 600; }
      .progress { background-color: #ecf1f8; height: 14px; overflow: visible; }
      .progress-bar { transition: width 0.4s ease; font-size: 11px; }
      .signal-meter { background: #fff; border: 1px solid #e9edf3; border-radius: 10px; padding: 0.75rem; box-shadow: inset 0 1px 0 rgba(255,255,255,0.6); }
      .signal-meter + .signal-meter { margin-top: 0.6rem; }
      .badge-soft { background: #f3f6fb; color: #3b4863; border-radius: 12px; padding: 0.15rem 0.5rem; }
      .band-group { background: #fff; border: 1px solid #e9edf3; border-radius: 10px; padding: 0.85rem 1rem; }
      .band-chip { padding: 0.2rem 0.55rem; border-radius: 999px; }
      .band-chip input { display: none; }
      .band-chip-label { min-width: 46px; }
    </style>
  </head>
  <body class="pb-5">
    <main class="container py-4">
      <nav class="navbar navbar-expand-lg mb-4 bg-white rounded shadow-sm px-3">
        <a class="navbar-brand fw-bold" href="#">Simple T99 (SSH)</a>
        <div class="ms-auto d-flex align-items-center gap-2">
          <span class="badge text-bg-secondary" id="connection-badge">Disconnesso</span>
        </div>
      </nav>

      <div class="card shadow-sm">
        <div class="card-header bg-white border-0 pb-0">
          <ul class="nav nav-tabs card-header-tabs" id="main-tabs" role="tablist">
            <li class="nav-item"><button class="nav-link active" data-target="connessione" type="button">Connessione</button></li>
            <li class="nav-item"><button class="nav-link" data-target="terminale" type="button">Terminale</button></li>
            <li class="nav-item"><button class="nav-link" data-target="segnali" type="button">Segnali</button></li>
            <li class="nav-item"><button class="nav-link" data-target="bande" type="button">Bande</button></li>
            <li class="nav-item"><button class="nav-link" data-target="info" type="button">Info</button></li>
          </ul>
        </div>
        <div class="card-body">
          <div class="tab-pane active" data-tab="connessione">
            <h5 class="card-title panel-title mb-3">Connessione SSH guidata</h5>
            <form id="connection-form" class="row g-3">
              <div class="col-12">
                <label class="form-label fw-semibold">Indirizzo IP / Host</label>
                <input class="form-control" name="host" required placeholder="192.168.88.1" value="192.168.88.1" />
              </div>
              <div class="col-md-6">
                <label class="form-label fw-semibold">Username</label>
                <input class="form-control" name="username" required placeholder="admin" value="admin" />
              </div>
              <div class="col-md-6">
                <label class="form-label fw-semibold">Password</label>
                <input class="form-control" type="password" name="password" required />
              </div>
              <div class="col-md-6">
                <label class="form-label fw-semibold">Porta SSH</label>
                <input class="form-control" name="port" type="number" min="1" max="65535" value="22" />
              </div>
              <div class="col-md-6">
                <label class="form-label fw-semibold">Interfaccia LTE</label>
                <input class="form-control" name="interface" required placeholder="lte1" value="lte1" />
                <small class="text-muted">Nome dell'interfaccia LTE sul router</small>
              </div>
              <div class="col-12 d-flex gap-2">
                <button type="button" class="btn btn-primary flex-grow-1" id="connect-button">Connetti</button>
                <button type="button" class="btn btn-outline-danger" id="disconnect-button">Disconnetti</button>
              </div>
              <div class="col-12">
                <div id="status" class="alert p-2 mb-0 d-none"></div>
                <pre id="debug-log" class="bg-dim p-2 small rounded d-none"></pre>
              </div>
            </form>
          </div>

          <div class="tab-pane" data-tab="terminale">
            <div class="d-flex align-items-center justify-content-between">
              <h6 class="card-subtitle text-muted mb-0">Terminale AT</h6>
              <small class="text-muted">Usa la sessione attiva per inviare comandi</small>
            </div>
            <div class="terminal mt-3" id="terminal" aria-live="polite"></div>
            <div class="input-group mt-2">
              <input id="command-input" class="form-control" placeholder="ATI" />
              <button id="send-button" class="btn btn-secondary">Invia</button>
            </div>
            <small class="text-muted">Esempi: ATI, AT^DEBUG?, AT^TEMP?</small>
          </div>

          <div class="tab-pane" data-tab="segnali">
            <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
              <div>
                <h5 class="card-title panel-title mb-0">Segnali &amp; Stato modem</h5>
                <small class="text-muted">Dati raccolti via AT (ATI, AT^DEBUG?, AT^TEMP?) over SSH</small>
              </div>
              <div class="d-flex gap-2">
                <button id="refresh-button" class="btn btn-outline-primary btn-sm">Aggiorna</button>
                <div class="input-group input-group-sm" style="min-width: 180px;">
                  <span class="input-group-text">
                    <div class="form-check form-switch m-0">
                      <input class="form-check-input" type="checkbox" id="auto-refresh" checked />
                    </div>
                    <label class="form-check-label ms-2" for="auto-refresh">Auto</label>
                  </span>
                  <input
                    class="form-control"
                    type="number"
                    id="auto-refresh-interval"
                    min="3"
                    max="60"
                    value="3"
                    aria-label="Intervallo auto refresh in secondi"
                  />
                  <span class="input-group-text">s</span>
                </div>
              </div>
            </div>

            <div class="row row-cols-1 row-cols-md-2 g-3 mt-2">
              <div class="col">
                <div class="card bg-light border-0 h-100">
                  <div class="card-body">
                    <div class="d-flex align-items-center gap-3">
                      <svg class="card-icon" viewBox="0 0 640 512" fill="#2fa7fb" xmlns="http://www.w3.org/2000/svg"><path d="M576 0c17.7 0 32 14.3 32 32V480c0 17.7-14.3 32-32 32s-32-14.3-32-32V32c0-17.7 14.3-32 32-32zM448 96c17.7 0 32 14.3 32 32V480c0 17.7-14.3 32-32 32s-32-14.3-32-32V128c0-17.7 14.3-32 32-32zM352 224V480c0 17.7-14.3 32-32 32s-32-14.3-32-32V224c0-17.7 14.3-32 32-32s32 14.3 32 32zM192 288c17.7 0 32 14.3 32 32V480c0 17.7-14.3 32-32 32s-32-14.3-32-32V320c0-17.7 14.3-32 32-32zM96 416v64c0 17.7-14.3 32-32 32s-32-14.3-32-32V416c0-17.7 14.3-32 32-32s32 14.3 32 32z"/></svg>
                      <div>
                        <div class="text-muted small">Segnale</div>
                        <h4 class="mb-0" id="signal-assessment">-</h4>
                        <small class="text-muted">RSRP/RSRQ/SNR</small>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div class="col">
                <div class="card bg-light border-0 h-100">
                  <div class="card-body">
                    <div class="d-flex align-items-center gap-3">
                      <svg class="card-icon" viewBox="0 0 320 512" fill="#fdb53c" xmlns="http://www.w3.org/2000/svg"><path d="M160 64c-26.5 0-48 21.5-48 48V276.5c0 17.3-7.1 31.9-15.3 42.5C86.2 332.6 80 349.5 80 368c0 44.2 35.8 80 80 80s80-35.8 80-80c0-18.5-6.2-35.4-16.7-48.9c-8.2-10.6-15.3-25.2-15.3-42.5V112c0-26.5-21.5-48-48-48zM48 112C48 50.2 98.1 0 160 0s112 50.1 112 112V276.5c0 .1 .1 .3 .2 .6c.2 .6 .8 1.6 1.7 2.8c18.9 24.4 30.1 55 30.1 88.1c0 79.5-64.5 144-144 144S16 447.5 16 368c0-33.2 11.2-63.8 30.1-88.1c.9-1.2 1.5-2.2 1.7-2.8c.1-.3 .2-.5 .2-.6V112zM208 368c0 26.5-21.5 48-48 48s-48-21.5-48-48c0-20.9 13.4-38.7 32-45.3V272c0-8.8 7.2-16 16-16s16 7.2 16 16v50.7c18.6 6.6 32 24.4 32 45.3z"/></svg>
                      <div>
                        <div class="text-muted small">Temperatura</div>
                        <h4 class="mb-0" id="temperature">-</h4>
                        <small class="text-muted">Media sensori</small>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="row g-3 mt-3">
              <div class="col-md-6">
                <div class="signal-meter h-100">
                  <div class="d-flex justify-content-between small mb-1"><span class="fw-semibold">RSRP</span><span id="rsrp-value">-</span></div>
                  <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100">
                    <div class="progress-bar" id="rsrp-bar" style="width: 0%"></div>
                  </div>
                </div>
              </div>
              <div class="col-md-6">
                <div class="signal-meter h-100">
                  <div class="d-flex justify-content-between small mb-1"><span class="fw-semibold">RSSI</span><span id="rssi-value">-</span></div>
                  <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100">
                    <div class="progress-bar" id="rssi-bar" style="width: 0%"></div>
                  </div>
                </div>
              </div>
              <div class="col-md-6">
                <div class="signal-meter h-100">
                  <div class="d-flex justify-content-between small mb-1"><span class="fw-semibold">RSRQ</span><span id="rsrq-value">-</span></div>
                  <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100">
                    <div class="progress-bar" id="rsrq-bar" style="width: 0%"></div>
                  </div>
                </div>
              </div>
              <div class="col-md-6">
                <div class="signal-meter h-100">
                  <div class="d-flex justify-content-between small mb-1"><span class="fw-semibold">SNR</span><span id="snr-value">-</span></div>
                  <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100">
                    <div class="progress-bar" id="snr-bar" style="width: 0%"></div>
                  </div>
                </div>
              </div>
              <div class="col-12">
                <div class="card border-0 bg-white shadow-sm">
                  <div class="card-header bg-white border-0 pb-0 d-flex justify-content-between align-items-center">
                    <div>
                      <div class="fw-semibold">Segnali avanzati</div>
                      <small class="text-muted">Dettagli per banda e tecnologia</small>
                    </div>
                    <button class="btn btn-sm btn-outline-primary" type="button" data-bs-toggle="collapse" data-bs-target="#advanced-collapse" aria-expanded="false">Mostra</button>
                  </div>
                  <div class="card-body collapse" id="advanced-collapse">
                    <div id="advanced-placeholder" class="text-muted small">Nessun dettaglio disponibile.</div>
                    <div id="advanced-container" class="d-flex flex-column gap-3"></div>
                  </div>
                </div>
              </div>
            </div>

            <div class="row g-3 mt-1">
              <div class="col-12">
                <div class="card border-0 bg-dim">
                  <div class="card-body">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                      <h6 class="mb-0">Informazioni rete</h6>
                      <span class="status-pill text-bg-light" id="rat-pill">-</span>
                    </div>
                    <div class="table-responsive">
                      <table class="table table-sm align-middle mb-0 signal-table">
                        <tbody>
                          <tr><th>Operatore</th><td id="network-provider">-</td></tr>
                          <tr><th>MCC/MNC</th><td id="mccmnc">-</td></tr>
                          <tr><th>Band</th><td id="bands">-</td></tr>
                          <tr><th>EARFCN/NRARFCN</th><td id="earfcn">-</td></tr>
                          <tr><th>PCI</th><td id="pci">-</td></tr>
                          <tr><th>Cell ID</th><td id="cell-id">-</td></tr>
                          <tr><th>TAC</th><td id="tac">-</td></tr>
                          <tr><th>RSRP</th><td id="rsrp">-</td></tr>
                          <tr><th>RSRQ</th><td id="rsrq">-</td></tr>
                          <tr><th>SNR</th><td id="snr">-</td></tr>
                          <tr><th>RSSI</th><td id="rssi">-</td></tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="mt-3">
              <h6 class="text-muted">Ultimi output AT</h6>
              <pre class="bg-white rounded border p-2 small" id="raw-debug" style="max-height: 200px; overflow:auto;"></pre>
            </div>
          </div>

          <div class="tab-pane" data-tab="bande">
            <div class="d-flex justify-content-between align-items-start flex-wrap gap-2">
              <div>
                <h5 class="panel-title mb-1">Gestione bande</h5>
                <p class="text-muted mb-0">Leggi e configura le bande disponibili con AT^BAND_PREF_EXT.</p>
              </div>
              <div class="d-flex gap-2">
                <button class="btn btn-outline-secondary btn-sm" id="bands-refresh-button" type="button">Leggi bande</button>
                <button class="btn btn-primary btn-sm" id="bands-save-button" type="button">Salva modifiche</button>
                <button class="btn btn-outline-danger btn-sm" id="bands-reset-button" type="button">Reset bande</button>
              </div>
            </div>

            <div id="bands-status" class="alert alert-info d-none mt-3"></div>
            <div id="bands-container" class="row g-3 mt-3">
              <div class="col-12">
                <div class="bg-white rounded border p-3 text-muted small">
                  Connetti il modem e premi "Leggi bande" per visualizzare le bande disponibili per WCDMA, LTE e 5G (NSA/SA).
                </div>
              </div>
            </div>
            <pre id="bands-raw" class="bg-dim p-2 small rounded d-none mt-3" style="max-height: 220px; overflow:auto;"></pre>
          </div>

          <div class="tab-pane" data-tab="info">
            <div class="d-flex justify-content-between align-items-start flex-wrap gap-2 mb-3">
              <div>
                <h5 class="panel-title mb-1">Info modem</h5>
                <p class="text-muted mb-0">Dati parsati dal comando ATI.</p>
              </div>
              <div class="d-flex gap-2">
                <button class="btn btn-outline-primary btn-sm" id="info-refresh" type="button">Aggiorna</button>
              </div>
            </div>

            <div id="info-status" class="alert alert-info d-none" role="alert"></div>

            <div class="row g-3">
              <div class="col-md-6">
                <div class="card border-0 shadow-sm h-100">
                  <div class="card-body">
                    <h6 class="fw-semibold mb-3">Identità modem (ATI)</h6>
                    <div class="table-responsive">
                      <table class="table table-sm mb-0">
                        <tbody>
                          <tr><th>Produttore</th><td id="info-manufacturer">-</td></tr>
                          <tr><th>Modello</th><td id="info-model">-</td></tr>
                          <tr><th>Revisione</th><td id="info-revision">-</td></tr>
                          <tr><th>SVN</th><td id="info-svn">-</td></tr>
                          <tr><th>IMEI</th><td id="info-imei">-</td></tr>
                          <tr><th>GCAP</th><td id="info-gcap">-</td></tr>
                          <tr><th>MPN</th><td id="info-mpn">-</td></tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
              <div class="col-md-6">
                <div class="bg-white border rounded h-100 p-3">
                  <div class="d-flex justify-content-between align-items-center mb-2">
                    <div class="fw-semibold">Output grezzo</div>
                    <span class="badge bg-light text-dark" id="info-last-update">-</span>
                  </div>
                  <pre id="info-raw" class="bg-dim p-2 small rounded" style="min-height: 120px; max-height: 260px; overflow:auto;"></pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" crossorigin="anonymous"></script>
    <script>
      const form = document.getElementById('connection-form');
      const statusEl = document.getElementById('status');
      const debugLog = document.getElementById('debug-log');
      const terminal = document.getElementById('terminal');
      const commandInput = document.getElementById('command-input');
      const sendButton = document.getElementById('send-button');
      const disconnectButton = document.getElementById('disconnect-button');
      const connectButton = document.getElementById('connect-button');
      const connectionBadge = document.getElementById('connection-badge');
      const refreshButton = document.getElementById('refresh-button');
      const autoRefresh = document.getElementById('auto-refresh');
      const autoRefreshInterval = document.getElementById('auto-refresh-interval');
      const rawDebug = document.getElementById('raw-debug');
      const mainTabs = document.getElementById('main-tabs');
      const advancedContainer = document.getElementById('advanced-container');
      const advancedPlaceholder = document.getElementById('advanced-placeholder');
      const bandsContainer = document.getElementById('bands-container');
      const bandsStatus = document.getElementById('bands-status');
      const bandsRaw = document.getElementById('bands-raw');
      const bandsRefreshButton = document.getElementById('bands-refresh-button');
      const bandsSaveButton = document.getElementById('bands-save-button');
      const bandsResetButton = document.getElementById('bands-reset-button');
      const infoRefreshButton = document.getElementById('info-refresh');
      const infoStatus = document.getElementById('info-status');
      const infoRaw = document.getElementById('info-raw');
      const infoLastUpdate = document.getElementById('info-last-update');
      const infoFields = {
        manufacturer: document.getElementById('info-manufacturer'),
        model: document.getElementById('info-model'),
        revision: document.getElementById('info-revision'),
        svn: document.getElementById('info-svn'),
        imei: document.getElementById('info-imei'),
        gcap: document.getElementById('info-gcap'),
        mpn: document.getElementById('info-mpn'),
      };
      const STORAGE_KEY = 'rsm-ssh-settings';
      let sessionToken = null;
      let autoTimer = null;
      let currentBands = {};
      let modemInfoLoaded = false;
      const bandTechnologies = [
        { key: 'WCDMA', label: 'WCDMA', hint: 'Bande 3G' },
        { key: 'LTE', label: 'LTE', hint: 'Bande 4G' },
        { key: 'NR5G_NSA', label: 'NR5G NSA', hint: '5G Non-Standalone' },
        { key: 'NR5G_SA', label: 'NR5G SA', hint: '5G Standalone' },
      ];
      const defaultBandsCatalog = {
        WCDMA: ['1', '2', '4', '5', '6', '8', '9', '19'],
        LTE: ['1', '2', '3', '4', '5', '7', '8', '12', '13', '14', '17', '18', '19', '20', '25', '26', '28', '29', '30', '32', '34', '38', '39', '40', '41', '42', '43', '46', '48', '66', '71'],
        NR5G_NSA: ['1', '2', '3', '5', '7', '8', '12', '14', '20', '25', '28', '38', '40', '41', '48', '66', '71', '77', '78', '79', '257', '258', '260', '261'],
        NR5G_SA: ['1', '2', '3', '5', '7', '8', '12', '20', '25', '28', '38', '40', '41', '48', '66', '71', '77', '78', '79'],
      };

      function loadSavedSettings() {
        try {
          const raw = localStorage.getItem(STORAGE_KEY);
          if (!raw) return;
          const saved = JSON.parse(raw);
          if (saved.host) form.host.value = saved.host;
          if (saved.username) form.username.value = saved.username;
          if (saved.password) form.password.value = saved.password;
          if (saved.port) form.port.value = saved.port;
          if (saved.interface) form.interface.value = saved.interface;
        } catch (error) {
          console.warn('Impossibile caricare le impostazioni salvate', error);
        }
      }

      function persistSettingsFromForm(data) {
        try {
          const payload = data || {
            host: form.host.value.trim(),
            username: form.username.value.trim(),
            password: form.password.value,
            port: form.port.value,
            interface: form.interface.value.trim(),
          };
          localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
        } catch (error) {
          console.warn('Impossibile salvare le impostazioni', error);
        }
      }

      mainTabs.addEventListener('click', (event) => {
        if (event.target.tagName !== 'BUTTON') return;
        const target = event.target.getAttribute('data-target');
        document.querySelectorAll('#main-tabs .nav-link').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
        event.target.classList.add('active');
        const pane = document.querySelector(`.tab-pane[data-tab="${target}"]`);
        if (pane) pane.classList.add('active');
        if (target === 'bande' && sessionToken && !Object.keys(currentBands).length) {
          loadBandPreferences(false);
        }
        if (target === 'info') {
          fetchModemInfo(!modemInfoLoaded);
        }
      });

      loadSavedSettings();

      ['host', 'username', 'password', 'port', 'interface'].forEach(name => {
        const input = form.elements[name];
        if (!input) return;
        input.addEventListener('change', () => persistSettingsFromForm());
        input.addEventListener('blur', () => persistSettingsFromForm());
      });

      const percentageCalculators = {
        rsrp(value) {
          if (isNaN(value) || value < -140) return 0;
          let pct = ((value - -135) / (-65 + 135)) * 100;
          if (pct > 100) pct = 100;
          if (pct < 15) pct = 15;
          return Math.round(pct);
        },
        rsrq(value) {
          if (isNaN(value) || value < -20) return 0;
          let pct = ((value - -20) / (-8 + 20)) * 100;
          if (pct > 100) pct = 100;
          if (pct < 15) pct = 15;
          return Math.round(pct);
        },
        snr(value) {
          if (isNaN(value) || value < -10) return 0;
          let pct = ((value - -10) / (35 + 10)) * 100;
          if (pct > 100) pct = 100;
          if (pct < 15) pct = 15;
          return Math.round(pct);
        },
        rssi(value) {
          if (isNaN(value)) return 0;
          const min = -110;
          const max = -30;
          if (value <= min) return 0;
          let pct = ((value - min) / (max - min)) * 100;
          if (pct > 100) pct = 100;
          if (pct < 15) pct = 15;
          return Math.round(pct);
        },
      };

      function getProgressClass(percentage) {
        if (percentage >= 60) return 'bg-success';
        if (percentage >= 40) return 'bg-warning';
        return 'bg-danger';
      }

      function updateMeter(idBase, value, percentage) {
        const valueEl = document.getElementById(`${idBase}-value`);
        const barEl = document.getElementById(`${idBase}-bar`);
        if (!valueEl || !barEl) return;
        valueEl.textContent = value || '-';
        barEl.style.width = `${percentage}%`;
        barEl.setAttribute('aria-valuenow', percentage.toString());
        barEl.className = `progress-bar ${getProgressClass(percentage)}`;
      }

      function log(message) {
        console.log(message);
        debugLog.classList.remove('d-none');
        const time = new Date().toLocaleTimeString();
        debugLog.textContent += time + ': ' + message + '\\n';
        debugLog.scrollTop = debugLog.scrollHeight;
      }
      function showStatus(message, type = 'info') {
        statusEl.classList.remove('d-none', 'alert-success', 'alert-danger', 'alert-info');
        const map = { success: 'alert-success', error: 'alert-danger', info: 'alert-info' };
        statusEl.classList.add(map[type] || 'alert-info');
        statusEl.textContent = message;
        log('Status: ' + message);
      }

      function appendTerminal(text, isError) {
        const color = isError ? '#ff8585' : '#3dff8f';
        const line = document.createElement('div');
        line.style.color = color;
        line.textContent = text;
        terminal.appendChild(line);
        terminal.scrollTop = terminal.scrollHeight;
      }

      function setConnectedUI(connected) {
        connectionBadge.textContent = connected ? 'Connesso' : 'Disconnesso';
        connectionBadge.className = connected ? 'badge text-bg-success' : 'badge text-bg-secondary';
        connectButton.disabled = connected;
      }

      function setInfoStatus(message, type = 'info') {
        infoStatus.classList.remove('d-none', 'alert-success', 'alert-danger', 'alert-info', 'alert-warning');
        const map = { success: 'alert-success', error: 'alert-danger', info: 'alert-info', warning: 'alert-warning' };
        infoStatus.classList.add(map[type] || 'alert-info');
        infoStatus.textContent = message;
      }

      function renderModemInfo(parsed) {
        Object.entries(infoFields).forEach(([key, el]) => {
          if (!el) return;
          el.textContent = parsed[key] || '-';
        });
        infoLastUpdate.textContent = new Date().toLocaleTimeString();
      }

      async function fetchModemInfo(showMessage = true) {
        if (!sessionToken) {
          setInfoStatus('Connetti al modem per leggere le informazioni.', 'warning');
          return;
        }

        infoRefreshButton.disabled = true;
        if (showMessage) {
          setInfoStatus('Lettura dati ATI in corso...', 'info');
        }

        try {
          const response = await fetch('/info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: sessionToken })
          });
          const data = await response.json();

          if (!response.ok) {
            setInfoStatus('Errore lettura info: ' + (data.error || 'richiesta fallita'), 'error');
            return;
          }

          renderModemInfo(data.parsed || {});
          infoRaw.textContent = (data.raw || '').trim();
          setInfoStatus('Info modem aggiornate.', 'success');
          modemInfoLoaded = true;
        } catch (error) {
          setInfoStatus('Errore lettura info: ' + error.message, 'error');
        } finally {
          infoRefreshButton.disabled = false;
        }
      }

      async function handleConnect(event) {
        if (event) event.preventDefault();

        log('Bottone Connetti cliccato');
        connectButton.disabled = true;
        showStatus('Connessione in corso...', 'info');

        const formData = new FormData(form);
        const payload = Object.fromEntries(formData.entries());
        payload.port = Number(payload.port || 22);

        persistSettingsFromForm(payload);

        const safePayload = Object.assign({}, payload, {password: '***'});
        log('Payload preparato: ' + JSON.stringify(safePayload));

        try {
          const response = await fetch('/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });

          const data = await response.json();

          if (!response.ok) {
            showStatus('Errore: ' + (data.error || 'Connessione fallita'), 'error');
            connectButton.disabled = false;
            return;
          }

          sessionToken = data.token;
          setConnectedUI(true);
          showStatus('Connessione stabilita!', 'success');
          appendTerminal('=== Sessione pronta (comandi via /interface lte at-chat) ===');
          appendTerminal((data.preview || '').trim() || '(nessun output)');
          commandInput.focus();
          autoRefresh.checked = true;
          enforceIntervalBounds();
          await fetchSignals();
          syncAutoRefreshState();
        } catch (error) {
          log('ERRORE durante fetch: ' + error.message);
          console.error('Errore completo:', error);
          showStatus('Errore: ' + error.message, 'error');
          connectButton.disabled = false;
        }
      }

      connectButton.addEventListener('click', handleConnect);
      form.addEventListener('submit', handleConnect);

      commandInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          sendButton.click();
        }
      });

      sendButton.addEventListener('click', async function() {
        if (!sessionToken) return;

        const command = commandInput.value.trim();
        if (!command) return;

        log('Invio comando: ' + command);
        sendButton.disabled = true;
        appendTerminal('> ' + command);
        commandInput.value = '';

        try {
          const response = await fetch('/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: sessionToken, command })
          });
          const data = await response.json();
          if (!response.ok) {
            appendTerminal('ERRORE: ' + (data.error || 'Comando fallito'), true);
            showStatus('Errore comando: ' + (data.error || ''), 'error');
          } else {
            appendTerminal(data.output || '(nessun output)');
          }
        } catch (error) {
          appendTerminal('Errore: ' + error.message, true);
        } finally {
          sendButton.disabled = false;
          commandInput.focus();
        }
      });

      disconnectButton.addEventListener('click', async function() {
        if (!sessionToken) return;

        log('Richiesta disconnessione');
        try {
          await fetch('/disconnect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: sessionToken })
          });
        } catch (error) {
          log('Errore durante disconnessione: ' + error.message);
          console.error(error);
        }

        terminal.innerHTML = '';
        showStatus('Sessione terminata', 'info');
        sessionToken = null;
        setConnectedUI(false);
        if (autoTimer) {
          clearInterval(autoTimer);
          autoRefresh.checked = false;
          autoTimer = null;
        }
        resetBandsUI();
        resetInfoUI();
      });

      refreshButton.addEventListener('click', fetchSignals);
      infoRefreshButton.addEventListener('click', () => fetchModemInfo(true));
      autoRefresh.addEventListener('change', syncAutoRefreshState);
      autoRefreshInterval.addEventListener('change', () => {
        enforceIntervalBounds();
        syncAutoRefreshState();
      });
      bandsRefreshButton.addEventListener('click', () => loadBandPreferences());
      bandsSaveButton.addEventListener('click', saveBandPreferences);
      bandsResetButton.addEventListener('click', resetBandPreferences);

      resetBandsUI();
      resetInfoUI();

      function enforceIntervalBounds() {
        const value = Number(autoRefreshInterval.value);
        if (Number.isNaN(value) || value < 3) {
          autoRefreshInterval.value = 3;
        } else if (value > 60) {
          autoRefreshInterval.value = 60;
        } else {
          autoRefreshInterval.value = Math.round(value);
        }
      }

      function syncAutoRefreshState() {
        if (!sessionToken) {
          autoRefresh.checked = false;
          if (autoTimer) {
            clearInterval(autoTimer);
            autoTimer = null;
          }
          return;
        }

        if (autoTimer) {
          clearInterval(autoTimer);
          autoTimer = null;
        }

        if (autoRefresh.checked) {
          enforceIntervalBounds();
          const intervalMs = Number(autoRefreshInterval.value) * 1000;
          autoTimer = setInterval(fetchSignals, intervalMs);
        }
      }

      function setBandsStatus(message, type = 'info') {
        if (!message) {
          bandsStatus.classList.add('d-none');
          bandsStatus.textContent = '';
          return;
        }
        bandsStatus.classList.remove('d-none', 'alert-success', 'alert-danger', 'alert-info', 'alert-warning');
        const map = { success: 'alert-success', error: 'alert-danger', warning: 'alert-warning', info: 'alert-info' };
        bandsStatus.classList.add(map[type] || 'alert-info');
        bandsStatus.textContent = message;
      }

      function resetBandsUI() {
        currentBands = {};
        bandsContainer.innerHTML = `<div class="col-12"><div class="bg-white rounded border p-3 text-muted small">Connetti il modem e premi "Leggi bande" per ottenere l'elenco delle bande disponibili.</div></div>`;
        setBandsStatus('In attesa di una connessione per leggere le bande.', 'info');
        bandsRaw.textContent = '';
        bandsRaw.classList.add('d-none');
      }

      function resetInfoUI() {
        modemInfoLoaded = false;
        Object.values(infoFields).forEach(el => {
          if (el) el.textContent = '-';
        });
        infoRaw.textContent = '';
        infoLastUpdate.textContent = '-';
        setInfoStatus('In attesa di una connessione per leggere le info modem.', 'info');
      }

      function parseBandResponse(text) {
        const state = {};
        // Usa backslash doppi per evitare che le sequenze di escape diventino CR/LF reali nella pagina HTML
        const lines = (text || '').split(/\\r?\\n/);
        lines.forEach(rawLine => {
          const line = rawLine.trim();
          if (!line) return;
          const match = line.match(/^(WCDMA|LTE|NR5G_NSA|NR5G_SA),(Enable Bands|Disable Bands)\\s*:?(.*)$/i);
          if (!match) return;
          const tech = match[1].toUpperCase();
          const kind = match[2].toLowerCase().includes('enable') ? 'enabled' : 'disabled';
          const parts = (match[3] || '')
            .split(',')
            .map(v => v.trim())
            .filter(Boolean);
          if (!state[tech]) {
            state[tech] = { enabled: [], disabled: [], available: [] };
          }
          state[tech][kind] = parts;
        });

        bandTechnologies.forEach(({ key }) => {
          const entry = state[key] || { enabled: [], disabled: [], available: [] };
          const available = Array.from(new Set([...(entry.enabled || []), ...(entry.disabled || [])]));
          entry.available = available.length ? available : (defaultBandsCatalog[key] || []);
          if (!entry.enabled.length && !entry.disabled.length && entry.available.length) {
            entry.enabled = [...entry.available];
          }
          state[key] = entry;
        });

        return state;
      }

      function renderBandTables(state) {
        bandsContainer.innerHTML = '';
        bandTechnologies.forEach(({ key, label, hint }) => {
          const info = state[key] || { enabled: [], disabled: [], available: [] };
          const available = [...(info.available || [])].sort((a, b) => Number(a) - Number(b));
          const enabledSet = new Set(info.enabled || []);
          const disabledSet = new Set(info.disabled || []);

          const pills = available
            .map(band => {
              const checked = enabledSet.size ? enabledSet.has(band) : !disabledSet.has(band);
              const inputId = `${key}-${band}`;
              return `
                <input class="btn-check band-checkbox" type="checkbox" data-tech="${key}" value="${band}" id="${inputId}" ${checked ? 'checked' : ''}>
                <label class="btn btn-outline-primary btn-sm band-chip band-chip-label" for="${inputId}">${band}</label>`;
            })
            .join('');

          const col = document.createElement('div');
          col.className = 'col-12';
          col.innerHTML = `
            <div class="band-group mb-2">
              <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2">
                <div>
                  <div class="fw-semibold">${label}</div>
                  <div class="text-muted small">${hint || ''}</div>
                </div>
                <div class="d-flex flex-wrap align-items-center gap-2">
                  <div class="btn-group btn-group-sm" role="group">
                    <button class="btn btn-outline-secondary" type="button" data-tech-action="select-all" data-tech="${key}">Seleziona tutte</button>
                    <button class="btn btn-outline-secondary" type="button" data-tech-action="deselect-all" data-tech="${key}">Deseleziona tutte</button>
                  </div>
                  <span class="badge bg-light text-dark">${available.length} bande</span>
                </div>
              </div>
              <div class="d-flex flex-wrap gap-1 align-items-center">
                ${pills || '<span class="text-muted small">Nessuna banda riportata dal modem.</span>'}
              </div>
            </div>`;
          bandsContainer.appendChild(col);
        });
      }

      bandsContainer.addEventListener('click', (event) => {
        const actionButton = event.target.closest('[data-tech-action]');
        if (!actionButton) return;
        const techKey = actionButton.getAttribute('data-tech');
        const action = actionButton.getAttribute('data-tech-action');
        if (!techKey || !action) return;
        const checkboxes = bandsContainer.querySelectorAll(`.band-checkbox[data-tech="${techKey}"]`);
        const shouldSelect = action === 'select-all';
        checkboxes.forEach(box => {
          box.checked = shouldSelect;
        });
      });

      function collectTechSelection(techKey) {
        const checkboxes = bandsContainer.querySelectorAll(`.band-checkbox[data-tech="${techKey}"]`);
        const selected = [];
        const available = [];
        checkboxes.forEach(box => {
          available.push(box.value);
          if (box.checked) selected.push(box.value);
        });
        return { selected, available };
      }

      async function loadBandPreferences(showMessage = true) {
        if (!sessionToken) {
          setBandsStatus('Connetti al modem per leggere le bande disponibili.', 'warning');
          return;
        }
        bandsRefreshButton.disabled = true;
        bandsSaveButton.disabled = true;
        bandsResetButton.disabled = true;
        if (showMessage) {
          setBandsStatus('Lettura bande dal modem in corso...', 'info');
        }
        try {
          const response = await fetch('/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: sessionToken, command: 'AT^BAND_PREF_EXT?' })
          });
          const data = await response.json();
          if (!response.ok) {
            setBandsStatus('Errore lettura bande: ' + (data.error || 'Richiesta fallita'), 'error');
            return;
          }
          const output = (data.output || '').trim();
          currentBands = parseBandResponse(output);
          renderBandTables(currentBands);
          bandsRaw.textContent = output;
          bandsRaw.classList.toggle('d-none', !output);
          setBandsStatus('Bande aggiornate dalla lettura del modem.', 'success');
        } catch (error) {
          setBandsStatus('Errore lettura bande: ' + error.message, 'error');
        } finally {
          bandsRefreshButton.disabled = false;
          bandsSaveButton.disabled = false;
          bandsResetButton.disabled = false;
        }
      }

      async function resetBandPreferences() {
        if (!sessionToken) {
          setBandsStatus('Connetti al modem per resettare le bande.', 'warning');
          return;
        }

        bandsResetButton.disabled = true;
        bandsRefreshButton.disabled = true;
        bandsSaveButton.disabled = true;
        setBandsStatus('Reset delle bande in corso...', 'info');

        try {
          const response = await fetch('/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: sessionToken, command: 'AT^BAND_PREF_EXT' })
          });
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.error || 'Comando AT rifiutato');
          }

          setBandsStatus('Bande ripristinate. Rilettura in corso...', 'success');
          await new Promise(resolve => setTimeout(resolve, 2000));
          await loadBandPreferences(false);
        } catch (error) {
          setBandsStatus('Errore reset bande: ' + error.message, 'error');
        } finally {
          bandsResetButton.disabled = false;
          bandsRefreshButton.disabled = false;
          bandsSaveButton.disabled = false;
        }
      }

      async function saveBandPreferences() {
        if (!sessionToken) {
          setBandsStatus('Connetti al modem per salvare le bande.', 'warning');
          return;
        }

        const commands = [];
        bandTechnologies.forEach(({ key }) => {
          const { selected, available } = collectTechSelection(key);
          if (!available.length) return;
          const disabled = available.filter(b => !selected.includes(b));
          if (disabled.length) {
            commands.push({ tech: key, status: 1, bands: disabled });
          }
          if (selected.length) {
            commands.push({ tech: key, status: 2, bands: selected });
          }
        });

        if (!commands.length) {
          setBandsStatus('Nessuna banda da inviare. Esegui prima la lettura.', 'warning');
          return;
        }

        bandsSaveButton.disabled = true;
        bandsRefreshButton.disabled = true;
        setBandsStatus('Invio configurazione bande al modem...', 'info');

        try {
          for (const cmd of commands) {
            const commandString = `AT^BAND_PREF_EXT=${cmd.tech},${cmd.status},${cmd.bands.join(':')}`;
            const response = await fetch('/send', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ token: sessionToken, command: commandString })
            });
            const data = await response.json();
            if (!response.ok) {
              throw new Error(data.error || 'Comando AT rifiutato');
            }
          }

          setBandsStatus('Configurazione inviata. Rilettura in corso...', 'success');
          await new Promise(resolve => setTimeout(resolve, 2000));
          await loadBandPreferences(false);
        } catch (error) {
          setBandsStatus('Errore durante il salvataggio: ' + error.message, 'error');
        } finally {
          bandsSaveButton.disabled = false;
          bandsRefreshButton.disabled = false;
        }
      }

      async function fetchSignals() {
        if (!sessionToken) return;
        refreshButton.disabled = true;
        try {
          const response = await fetch('/signals', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: sessionToken })
          });
          const data = await response.json();
          if (!response.ok) {
            showStatus('Errore segnali: ' + (data.error || 'richiesta fallita'), 'error');
            return;
          }
          renderSignals(data.parsed || {});
          rawDebug.textContent = (data.raw || '').trim();
        } catch (error) {
          showStatus('Errore segnali: ' + error.message, 'error');
        } finally {
          refreshButton.disabled = false;
        }
      }

      function renderSignals(parsed) {
        document.getElementById('signal-assessment').textContent = parsed.signal_assessment || '-';
        document.getElementById('temperature').textContent = parsed.temperature || '-';
        document.getElementById('network-provider').textContent = parsed.operator || '-';
        document.getElementById('mccmnc').textContent = parsed.mccmnc || '-';
        document.getElementById('bands').textContent = parsed.bands || '-';
        document.getElementById('earfcn').textContent = parsed.channels || parsed.channel || '-';
        document.getElementById('pci').textContent = parsed.pci || '-';
        document.getElementById('cell-id').textContent = parsed.cell_id || '-';
        document.getElementById('tac').textContent = parsed.tac || '-';
        document.getElementById('rsrp').textContent = parsed.rsrp || '-';
        document.getElementById('rsrq').textContent = parsed.rsrq || '-';
        document.getElementById('snr').textContent = parsed.snr || '-';
        document.getElementById('rssi').textContent = parsed.rssi || '-';
        const ratPill = document.getElementById('rat-pill');
        ratPill.textContent = parsed.rat || '-';
        ratPill.className = 'status-pill text-bg-' + (parsed.rat === 'NR5G_SA' || parsed.rat === 'LTE+NR' ? 'success' : 'light');

        const rsrpVal = parseFloat(parsed.rsrp_value);
        const rsrqVal = parseFloat(parsed.rsrq_value);
        const snrVal = parseFloat(parsed.snr_value);
        const rssiVal = parseFloat(parsed.rssi_value);
        updateMeter('rsrp', parsed.rsrp || '-', percentageCalculators.rsrp(rsrpVal));
        updateMeter('rsrq', parsed.rsrq || '-', percentageCalculators.rsrq(rsrqVal));
        updateMeter('snr', parsed.snr || '-', percentageCalculators.snr(snrVal));
        updateMeter('rssi', parsed.rssi || '-', percentageCalculators.rssi(rssiVal));

        renderAdvanced(parsed.advanced || []);
      }

      function renderAdvanced(details) {
        advancedContainer.innerHTML = '';
        if (!details || !details.length) {
          advancedPlaceholder.classList.remove('d-none');
          return;
        }
        advancedPlaceholder.classList.add('d-none');

        details.forEach(detail => {
          const wrapper = document.createElement('div');
          wrapper.className = 'border rounded p-2';

          const header = document.createElement('div');
          header.className = 'd-flex justify-content-between flex-wrap gap-2';
          header.innerHTML = `<div><div class="fw-semibold">${detail.title || 'Banda'}</div><div class="text-muted small">${detail.technology || ''}${detail.band_display ? ' · ' + detail.band_display : ''}</div></div><div class="text-muted small text-end">PCI: ${detail.pci || '-'}<br/>Canale: ${detail.channel || '-'}</div>`;
          wrapper.appendChild(header);

          if (detail.bandwidth || detail.rx_diversity) {
            const meta = document.createElement('div');
            meta.className = 'd-flex justify-content-between text-muted small mt-1';
            meta.innerHTML = `<span>Larghezza banda: ${detail.bandwidth || '-'}</span><span>${detail.rx_diversity ? 'RX Diversity: ' + detail.rx_diversity : ''}</span>`;
            wrapper.appendChild(meta);
          }

          if (detail.tx_power) {
            const tx = document.createElement('div');
            tx.className = 'text-muted small';
            tx.textContent = `Potenza TX: ${detail.tx_power}`;
            wrapper.appendChild(tx);
          }

          (detail.metrics || []).forEach(metric => {
            const pct = percentageCalculators[metric.key] ? percentageCalculators[metric.key](parseFloat(metric.value)) : 0;
            const block = document.createElement('div');
            block.className = 'mt-2';
            block.innerHTML = `<div class="d-flex justify-content-between small"><span class="fw-semibold">${metric.label}</span><span>${metric.display || 'N/A'}</span></div>`;
            const progress = document.createElement('div');
            progress.className = 'progress';
            progress.setAttribute('role', 'progressbar');
            progress.setAttribute('aria-valuemin', '0');
            progress.setAttribute('aria-valuemax', '100');

            if (pct > 0) {
              const bar = document.createElement('div');
              bar.className = `progress-bar ${getProgressClass(pct)}`;
              bar.style.width = `${pct}%`;
              bar.textContent = `${metric.display} / ${pct}%`;
              progress.appendChild(bar);
              block.appendChild(progress);
            } else {
              const muted = document.createElement('div');
              muted.className = 'text-muted fst-italic small';
              muted.textContent = 'Valore non disponibile';
              block.appendChild(muted);
            }
            wrapper.appendChild(block);
          });

          (detail.antennas || []).forEach(ant => {
            const pct = percentageCalculators.rsrp(parseFloat(ant.value));
            const block = document.createElement('div');
            block.className = 'mt-2';
            block.innerHTML = `<div class="d-flex justify-content-between small"><span>${ant.label || 'Antenna'}</span><span>${ant.display || 'N/A'}</span></div>`;
            if (pct > 0) {
              const progress = document.createElement('div');
              progress.className = 'progress';
              const bar = document.createElement('div');
              bar.className = `progress-bar ${getProgressClass(pct)}`;
              bar.style.width = `${pct}%`;
              progress.appendChild(bar);
              block.appendChild(progress);
            }
            wrapper.appendChild(block);
          });

          advancedContainer.appendChild(wrapper);
        });
      }
    </script>
  </body>
</html>
"""


def _mask_password(password: str) -> str:
    if not password:
        return "<vuoto>"
    if len(password) <= 4:
        return "*" * len(password)
    return f"{password[0]}***{password[-1]} (len={len(password)})"


def _run_at_command(session: SSHSession, at_cmd: str, timeout: int = 20) -> str:
    ros_cmd = _build_ros_at_chat_cmd(session.interface, at_cmd)
    logger.debug("Esecuzione AT via SSH (%s): %s", at_cmd, ros_cmd)
    with session.lock:
        out, err = _run_ros_cmd(session.client, ros_cmd, timeout=timeout)
    text = (out or "") + ("\n" + err if err else "")
    return text.strip()


def _build_ros_at_chat_cmd(interface: str, at_cmd: str) -> str:
    """
    Wrappa un comando AT dentro RouterOS:
      /interface lte at-chat <iface> input="<cmd>"
    """
    clean = (at_cmd or "").strip()
    clean = clean.replace("\r", "").replace("\n", " ")

    # RouterOS: usiamo stringa tra doppi apici; escapamo backslash e doppi apici
    clean = clean.replace("\\", "\\\\").replace('"', '\\"')

    return f'/interface lte at-chat {interface} input="{clean}"'


def _parse_ati_output(text: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {
        "manufacturer": "-",
        "model": "-",
        "revision": "-",
        "svn": "-",
        "imei": "-",
        "gcap": "-",
        "mpn": "-",
    }

    for raw_line in text.splitlines():
        sanitized = "".join(ch for ch in raw_line if ch.isprintable() or ch in "\t")
        line = sanitized.strip()
        if not line or line.upper() == "OK":
            continue

        match = re.match(
            r"^(?P<key>\+?(manufacturer|model|revision|svn|imei|gcap|mpn))\s*[:=]?\s*(?P<value>.*)$",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            key = match.group("key").lstrip("+").strip().lower()
            value = match.group("value").strip() or "-"
            parsed[key] = value
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        normalized_key = key.strip().lstrip("+").lower()
        if normalized_key in parsed:
            parsed[normalized_key] = value.strip() or "-"

    return parsed


def _parse_temp_output(text: str) -> str:
    temps = []
    for label in ["TSENS", "PA", "Skin Sensor"]:
        match = re.search(rf"{re.escape(label)}:\s*([+-]?\d+)C", text, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            temps.append(value)

    if not temps:
        return "-"

    average = sum(temps) / len(temps)
    return f"Media {average:.1f}°C"


def _parse_debug_output(text: str) -> Dict[str, Any]:
    info: Dict[str, str] = {
        "rat": "-",
        "mccmnc": "-",
        "bands": "-",
        "channel": "-",
        "channels": "-",
        "pci": "-",
        "cell_id": "-",
        "tac": "-",
        "rsrp": "-",
        "rsrq": "-",
        "snr": "-",
        "rssi": "-",
        "rsrp_value": None,
        "rsrq_value": None,
        "snr_value": None,
        "rssi_value": None,
        "advanced": [],
    }

    def _to_float(value: str) -> Optional[float]:
        try:
            return float(value)
        except Exception:
            return None

    def _extract_first_float(value: str) -> Optional[float]:
        match = re.search(r"([-+]?\d+(?:\.\d+)?)", value)
        if not match:
            return None
        return _to_float(match.group(1))

    def _round_value(value: Optional[float]) -> Optional[float]:
        if value is None or value != value:
            return None
        return round(value, 1)

    def _parse_antennas(line: str, prefix: str = "Antenna"):
        match = re.search(r"\(([^)]+)\)", line)
        if not match:
            return []
        antennas = []
        for idx, item in enumerate(match.group(1).split(",")):
            value = _extract_first_float(item.strip())
            antennas.append(
                {
                    "label": f"{prefix} {idx + 1}",
                    "value": value,
                    "display": f"{value} dBm" if value is not None else "N/A",
                }
            )
        return antennas

    def _finalize_entry(entry: Optional[Dict], advanced: list) -> None:
        if not entry:
            return

        band_display = (
            f"Band {entry['band']}" if entry.get("technology") == "LTE" and entry.get("band") else entry.get("band") or "N/A"
        )
        title = "Primary 4G" if entry.get("technology") == "LTE" else "Primary 5G"
        if entry.get("technology") == "LTE" and entry.get("role") == "secondary":
            title = f"CA 4G #{entry.get('ca_index', '')}".strip()
        if band_display != "N/A":
            title = f"{title} ({band_display})"

        detail = {
            "title": title,
            "technology": entry.get("technology"),
            "band": entry.get("band"),
            "band_display": band_display,
            "bandwidth": entry.get("bandwidth") or "-",
            "channel": entry.get("channel") or "-",
            "pci": entry.get("pci") or "-",
            "rx_diversity": entry.get("rx_diversity") or "",
            "tx_power": f"{_round_value(entry.get('tx_power'))} dBm" if entry.get("tx_power") is not None else "",
            "metrics": [],
            "antennas": entry.get("antennas") or [],
        }

        def add_metric(key: str, label: str, value: Optional[float], unit: str) -> None:
            normalized = _round_value(value)
            detail["metrics"].append(
                {
                    "key": key,
                    "label": label,
                    "value": normalized,
                    "display": f"{normalized} {unit}" if normalized is not None else "N/A",
                }
            )

        add_metric("rsrq", "RSRQ" if entry.get("technology") == "LTE" else "SS_RSRQ", entry.get("rsrq"), "dB")
        add_metric("rsrp", "RSRP" if entry.get("technology") == "LTE" else "SS_RSRP", entry.get("rsrp"), "dBm")
        add_metric("rssi", "RSSI", entry.get("rssi"), "dBm")
        add_metric("snr", "SINR" if entry.get("technology") == "LTE" else "SS_SINR", entry.get("snr"), "dB")
        advanced.append(detail)

    current_entry = None
    scell_counter = 0
    advanced_entries = []
    pending_lte_antennas = []
    pending_lte_diversity: Optional[str] = None
    pending_lte_tx_power: Optional[float] = None
    pending_nr_tx_power: Optional[float] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.lower().startswith("output:"):
            line = line.split(":", 1)[1].strip()
            if not line:
                continue

        if line.lower().startswith("rat:"):
            info["rat"] = line.split(":", 1)[1].strip()
            continue

        if re.search(r"mcc:\d+", line, re.IGNORECASE) and re.search(r"mnc:\d+", line, re.IGNORECASE):
            mcc = re.search(r"mcc:(\d+)", line, re.IGNORECASE)
            mnc = re.search(r"mnc:(\d+)", line, re.IGNORECASE)
            if mcc and mnc:
                info["mccmnc"] = f"{mcc.group(1)}/{mnc.group(1)}"
            continue

        if line.startswith("lte_ant_rsrp"):
            pending_lte_antennas = _parse_antennas(line)
            diversity = re.search(r"rx_diversity:([0-9]+)", line, re.IGNORECASE)
            if diversity:
                pending_lte_diversity = diversity.group(1)
            continue

        if line.startswith("lte_tx_pwr"):
            pending_lte_tx_power = _extract_first_float(line)
            continue

        if line.startswith("nr_tx_pwr"):
            pending_nr_tx_power = _extract_first_float(line)
            continue

        if line.startswith("pcell:"):
            _finalize_entry(current_entry, advanced_entries)
            current_entry = {
                "technology": "LTE",
                "role": "primary",
                "band": None,
                "bandwidth": None,
                "channel": None,
                "pci": None,
                "rsrp": None,
                "rsrq": None,
                "rssi": None,
                "snr": None,
                "antennas": pending_lte_antennas,
                "rx_diversity": pending_lte_diversity,
                "tx_power": pending_lte_tx_power,
            }
            pending_lte_antennas = []
            pending_lte_diversity = None
            pending_lte_tx_power = None
            band_match = re.search(r"lte_band:(\d+)", line, re.IGNORECASE)
            bw_match = re.search(r"lte_band_width:([^\s]+)", line, re.IGNORECASE)
            if band_match:
                current_entry["band"] = band_match.group(1)
                if info.get("bands") == "-":
                    info["bands"] = band_match.group(1)
            if bw_match:
                current_entry["bandwidth"] = bw_match.group(1)
            continue

        if line.startswith("scell:"):
            _finalize_entry(current_entry, advanced_entries)
            scell_counter += 1
            current_entry = {
                "technology": "LTE",
                "role": "secondary",
                "ca_index": scell_counter,
                "band": None,
                "bandwidth": None,
                "channel": None,
                "pci": None,
                "rsrp": None,
                "rsrq": None,
                "rssi": None,
                "snr": None,
                "antennas": [],
                "rx_diversity": None,
                "tx_power": None,
            }
            band_match = re.search(r"lte_band:(\d+)", line, re.IGNORECASE)
            bw_match = re.search(r"lte_band_width:([^\s]+)", line, re.IGNORECASE)
            if band_match:
                current_entry["band"] = band_match.group(1)
                if info.get("bands") == "-":
                    info["bands"] = band_match.group(1)
            if bw_match:
                current_entry["bandwidth"] = bw_match.group(1)
            continue

        if line.startswith("nr_band:"):
            _finalize_entry(current_entry, advanced_entries)
            current_entry = {
                "technology": "NR",
                "role": "primary",
                "band": None,
                "bandwidth": None,
                "channel": None,
                "pci": None,
                "rsrp": None,
                "rsrq": None,
                "rssi": None,
                "snr": None,
                "antennas": [],
                "rx_diversity": None,
                "tx_power": pending_nr_tx_power,
            }
            pending_nr_tx_power = None
            band_match = re.search(r"nr_band:([^\s]+)", line, re.IGNORECASE)
            if band_match:
                current_entry["band"] = band_match.group(1)
                if info.get("bands") == "-":
                    info["bands"] = band_match.group(1)
            continue

        if current_entry:
            if line.startswith("channel:") and current_entry.get("technology") == "LTE":
                channel_match = re.search(r"channel:(\d+)", line, re.IGNORECASE)
                pci_match = re.search(r"pci:(\d+)", line, re.IGNORECASE)
                if channel_match:
                    current_entry["channel"] = channel_match.group(1)
                    if info.get("channel") == "-":
                        info["channel"] = current_entry["channel"]
                if pci_match:
                    current_entry["pci"] = pci_match.group(1)
                    if info.get("pci") == "-":
                        info["pci"] = current_entry["pci"]
                continue

            if line.startswith("nr_channel:") and current_entry.get("technology") == "NR":
                parts = line.split(":", 1)
                if len(parts) > 1:
                    current_entry["channel"] = parts[1].strip()
                    if info.get("channel") == "-":
                        info["channel"] = current_entry["channel"]
                continue

            if line.startswith("nr_pci:") and current_entry.get("technology") == "NR":
                parts = line.split(":", 1)
                if len(parts) > 1:
                    current_entry["pci"] = parts[1].strip()
                    if info.get("pci") == "-":
                        info["pci"] = current_entry["pci"]
                continue

            if line.startswith("nr_band_width:") and current_entry.get("technology") == "NR":
                parts = line.split(":", 1)
                if len(parts) > 1:
                    current_entry["bandwidth"] = parts[1].strip()
                continue

            if line.startswith("lte_rsrp:") and current_entry.get("technology") == "LTE":
                rsrp_match = re.search(r"lte_rsrp:([-\d.]+)", line, re.IGNORECASE)
                rsrq_match = re.search(r"rsrq:([-\d.]+)", line, re.IGNORECASE)
                if rsrp_match:
                    current_entry["rsrp"] = _to_float(rsrp_match.group(1))
                    if info.get("rsrp") == "-":
                        info["rsrp_value"] = current_entry["rsrp"]
                        info["rsrp"] = f"{current_entry['rsrp']}dBm" if current_entry["rsrp"] is not None else "-"
                if rsrq_match:
                    current_entry["rsrq"] = _to_float(rsrq_match.group(1))
                    if info.get("rsrq") == "-":
                        info["rsrq_value"] = current_entry["rsrq"]
                        info["rsrq"] = f"{current_entry['rsrq']}dB" if current_entry["rsrq"] is not None else "-"
                continue

            if line.startswith("lte_rssi:") and current_entry.get("technology") == "LTE":
                rssi_match = re.search(r"lte_rssi:([-\d.]+)", line, re.IGNORECASE)
                snr_match = re.search(r"lte_snr:([-\d.]+)", line, re.IGNORECASE)
                if rssi_match:
                    current_entry["rssi"] = _to_float(rssi_match.group(1))
                    if info.get("rssi") == "-":
                        info["rssi_value"] = current_entry["rssi"]
                        info["rssi"] = f"{current_entry['rssi']}dBm" if current_entry["rssi"] is not None else "-"
                if snr_match:
                    current_entry["snr"] = _to_float(snr_match.group(1))
                    if info.get("snr") == "-":
                        info["snr_value"] = current_entry["snr"]
                        info["snr"] = f"{current_entry['snr']}dB" if current_entry["snr"] is not None else "-"
                continue

            if line.startswith("nr_rsrp:") and current_entry.get("technology") == "NR":
                rsrp_match = re.search(r"nr_rsrp:([-\d.]+)", line, re.IGNORECASE)
                diversity = re.search(r"rx_diversity:([\d]+)", line, re.IGNORECASE)
                if rsrp_match:
                    current_entry["rsrp"] = _to_float(rsrp_match.group(1))
                    if info.get("rsrp") == "-":
                        info["rsrp_value"] = current_entry["rsrp"]
                        info["rsrp"] = f"{current_entry['rsrp']}dBm" if current_entry["rsrp"] is not None else "-"
                if diversity:
                    current_entry["rx_diversity"] = diversity.group(1)
                antennas = _parse_antennas(line)
                if antennas:
                    current_entry["antennas"] = antennas
                continue

            if line.startswith("nr_rsrq:") and current_entry.get("technology") == "NR":
                rsrq_match = re.search(r"nr_rsrq:([-\d.]+)", line, re.IGNORECASE)
                if rsrq_match:
                    current_entry["rsrq"] = _to_float(rsrq_match.group(1))
                    if info.get("rsrq") == "-":
                        info["rsrq_value"] = current_entry["rsrq"]
                        info["rsrq"] = f"{current_entry['rsrq']}dB" if current_entry["rsrq"] is not None else "-"
                continue

            if line.startswith("nr_rssi:") and current_entry.get("technology") == "NR":
                rssi_match = re.search(r"nr_rssi:([-\d.]+)", line, re.IGNORECASE)
                if rssi_match:
                    current_entry["rssi"] = _to_float(rssi_match.group(1))
                    if info.get("rssi") == "-":
                        info["rssi_value"] = current_entry["rssi"]
                        info["rssi"] = f"{current_entry['rssi']}dBm" if current_entry["rssi"] is not None else "-"
                continue

            if line.startswith("nr_snr:") and current_entry.get("technology") == "NR":
                snr_match = re.search(r"nr_snr:([-\d.]+)", line, re.IGNORECASE)
                if snr_match:
                    current_entry["snr"] = _to_float(snr_match.group(1))
                    if info.get("snr") == "-":
                        info["snr_value"] = current_entry["snr"]
                        info["snr"] = f"{current_entry['snr']}dB" if current_entry["snr"] is not None else "-"
                continue

        cell = re.search(r"(lte_cell_id|nr_cell_id):(\d+)", line, re.IGNORECASE)
        if cell:
            info["cell_id"] = cell.group(2)
        tac = re.search(r"(lte_tac|nr_tac):(\d+)", line, re.IGNORECASE)
        if tac:
            info["tac"] = tac.group(2)
        channel_match = re.search(r"channel:(\d+)", line, re.IGNORECASE)
        if channel_match and info.get("channel") == "-":
            info["channel"] = channel_match.group(1)
        pci_match = re.search(r"pci:(\d+)", line, re.IGNORECASE)
        if pci_match and info.get("pci") == "-":
            info["pci"] = pci_match.group(1)
        band_match = re.search(r"(?:lte_band|nr_band):([\w/+-]+)", line, re.IGNORECASE)
        if band_match:
            existing = info["bands"].split(", ") if info["bands"] != "-" else []
            if band_match.group(1) not in existing:
                existing.append(band_match.group(1))
            info["bands"] = ", ".join(existing)

        rsrp_match = re.search(r"(?:lte_rsrp|nr_rsrp):\s*([-\d.]+)", line, re.IGNORECASE)
        if rsrp_match and info.get("rsrp") == "-":
            info["rsrp_value"] = _to_float(rsrp_match.group(1))
            info["rsrp"] = f"{info['rsrp_value']}dBm" if info["rsrp_value"] is not None else "-"

        rsrq_match = re.search(r"(?:rsrq|nr_rsrq):\s*([-\d.]+)", line, re.IGNORECASE)
        if rsrq_match and info.get("rsrq") == "-":
            info["rsrq_value"] = _to_float(rsrq_match.group(1))
            info["rsrq"] = f"{info['rsrq_value']}dB" if info["rsrq_value"] is not None else "-"

        snr_match = re.search(r"(?:lte_snr|nr_snr):\s*([-\d.]+)", line, re.IGNORECASE)
        if snr_match and info.get("snr") == "-":
            info["snr_value"] = _to_float(snr_match.group(1))
            info["snr"] = f"{info['snr_value']}dB" if info["snr_value"] is not None else "-"

        rssi_match = re.search(r"lte_rssi:([-\d.]+)", line, re.IGNORECASE)
        if rssi_match and info.get("rssi") == "-":
            info["rssi_value"] = _to_float(rssi_match.group(1))
            info["rssi"] = f"{info['rssi_value']}dBm" if info["rssi_value"] is not None else "-"

    _finalize_entry(current_entry, advanced_entries)
    info["advanced"] = advanced_entries

    def _build_band_display(entries: list) -> str:
        seen = set()
        ordered_bands = []

        for entry in entries:
            band = entry.get("band")
            technology = entry.get("technology")

            if not band:
                continue

            normalized_band = str(band).strip()
            if technology == "NR" and not normalized_band.lower().startswith("n"):
                normalized_band = f"n{normalized_band}"

            if normalized_band in seen:
                continue

            seen.add(normalized_band)
            ordered_bands.append(normalized_band)

        return " + ".join(ordered_bands) if ordered_bands else "-"

    info["bands"] = _build_band_display(advanced_entries)

    def _build_channel_display(entries: list) -> str:
        channels = []

        for entry in entries:
            channel = entry.get("channel")
            if not channel:
                continue

            normalized_band = entry.get("band")
            technology = entry.get("technology")

            if technology == "NR" and normalized_band and not str(normalized_band).lower().startswith("n"):
                normalized_band = f"n{normalized_band}"

            label = str(channel).strip()
            if normalized_band:
                label = f"{label} ({normalized_band})"

            channels.append(label)

        return " + ".join(channels) if channels else "-"

    info["channels"] = _build_channel_display(advanced_entries)

    return info


def _assess_signal(rsrp: str, rsrq: str, snr: str) -> str:
    try:
        rsrp_val = float(rsrp.replace("dBm", "")) if rsrp.endswith("dBm") else None
        rsrq_val = float(rsrq.replace("dB", "")) if rsrq.endswith("dB") else None
        snr_val = float(snr.replace("dB", "")) if snr.endswith("dB") else None
    except Exception:
        return "-"

    if rsrp_val is None:
        return "-"

    if rsrp_val >= -90 and (snr_val or 0) >= 10:
        return "Ottimo"
    if rsrp_val >= -105 and (rsrq_val or -40) >= -14:
        return "Buono"
    if rsrp_val >= -115:
        return "Discreto"
    return "Debole"


def _run_ros_cmd(client: paramiko.SSHClient, ros_cmd: str, timeout: int = 12) -> Tuple[str, str]:
    """
    Esegue un comando RouterOS in modalità non-interattiva.
    Ritorna (stdout, stderr) come stringhe.
    """
    logger.debug("exec_command: %s", ros_cmd)
    stdin, stdout, stderr = client.exec_command(ros_cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="ignore")
    err = stderr.read().decode("utf-8", errors="ignore")
    return out, err


@app.route("/", methods=["GET"])
def index() -> str:
    logger.info("Richiesta pagina principale")
    return HTML_PAGE


@app.route("/connect", methods=["POST"])
def connect():
    logger.info("Richiesta POST a /connect ricevuta")

    try:
        data = request.get_json(force=True)
        logger.debug("Dati JSON ricevuti: %s", {k: v if k != 'password' else '***' for k, v in data.items()})
    except Exception as e:
        logger.error("Errore parsing JSON: %s", e)
        return jsonify({"error": "JSON non valido"}), 400

    required = ["host", "username", "password", "interface"]
    missing = [key for key in required if not data.get(key)]
    if missing:
        logger.warning("Campi mancanti: %s", missing)
        return jsonify({"error": f"Campi mancanti: {', '.join(missing)}"}), 400

    host = data["host"].strip()
    username = data["username"].strip()
    password = data["password"]
    interface = data["interface"].strip()
    port = int(data.get("port", 22))

    logger.info(
        "Tentativo connessione: host=%s port=%s user=%s interface=%s password=%s",
        host, port, username, interface, _mask_password(password),
    )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        logger.debug("Connessione SSH a %s:%s...", host, port)
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=10,
        )
        logger.info("Connessione SSH stabilita")
    except Exception as exc:
        logger.exception("Connessione SSH fallita verso %s:%s", host, port)
        return jsonify({"error": f"Connessione SSH fallita: {str(exc)}"}), 502

    # Test preview: ATI
    try:
        ros_cmd = _build_ros_at_chat_cmd(interface, "ATI")
        out, err = _run_ros_cmd(client, ros_cmd, timeout=15)
        preview = (out or "") + (("\n" + err) if err else "")
        if not preview.strip():
            preview = "(nessun output)"
        logger.info("Preview OK, len=%d", len(preview))
    except Exception as exc:
        client.close()
        logger.exception("Test at-chat fallito")
        return jsonify({"error": f"Test at-chat fallito: {str(exc)}"}), 500

    session = sessions.add(client, interface, host, username, port)
    sessions.cleanup()
    return jsonify({"token": session.token, "preview": preview})


@app.route("/send", methods=["POST"])
def send_command():
    logger.info("Richiesta POST a /send ricevuta")

    data = request.get_json(force=True)
    token = data.get("token")
    command = (data.get("command") or "").strip()

    if not token or not command:
        logger.warning("Token o comando mancante")
        return jsonify({"error": "Token o comando mancante"}), 400

    session = sessions.get(token)
    if not session:
        logger.warning("Sessione non trovata per token=%s", token[:10] if token else "None")
        return jsonify({"error": "Sessione non trovata o scaduta"}), 404

    ros_cmd = _build_ros_at_chat_cmd(session.interface, command)
    logger.info("AT->ROS (token=%s): %s", token[:10] + "...", ros_cmd)

    try:
        # Evita concorrenza sullo stesso SSHClient se arrivano richieste simultanee
        with session.lock:
            out, err = _run_ros_cmd(session.client, ros_cmd, timeout=20)

        output = (out or "")
        if err:
            output = (output.rstrip() + "\n" + err).strip("\n")

        if not output.strip():
            output = "(nessun output)"

    except Exception as exc:
        sessions.remove(token)
        logger.exception("Errore durante comando AT '%s'", command)
        return jsonify({"error": f"Comando fallito: {str(exc)}"}), 502

    return jsonify({"output": output})


@app.route("/info", methods=["POST"])
def modem_info():
    logger.info("Richiesta POST a /info ricevuta")
    data = request.get_json(force=True)
    token = data.get("token")
    if not token:
        return jsonify({"error": "Token mancante"}), 400

    session = sessions.get(token)
    if not session:
        return jsonify({"error": "Sessione non trovata o scaduta"}), 404

    try:
        ati_text = _run_at_command(session, "ATI", timeout=15)
    except Exception as exc:
        logger.exception("Errore durante la lettura di ATI")
        return jsonify({"error": f"Comando ATI fallito: {str(exc)}"}), 502

    parsed = _parse_ati_output(ati_text)
    return jsonify({"parsed": parsed, "raw": ati_text})


@app.route("/signals", methods=["POST"])
def signals():
    logger.info("Richiesta POST a /signals ricevuta")
    data = request.get_json(force=True)
    token = data.get("token")
    if not token:
        return jsonify({"error": "Token mancante"}), 400

    session = sessions.get(token)
    if not session:
        return jsonify({"error": "Sessione non trovata o scaduta"}), 404

    try:
        ati_text = _run_at_command(session, "ATI", timeout=15)
        debug_text = _run_at_command(session, "AT^DEBUG?", timeout=25)
        temp_text = _run_at_command(session, "AT^TEMP?", timeout=15)
    except Exception as exc:
        logger.exception("Errore durante raccolta segnali")
        return jsonify({"error": f"Comandi AT falliti: {str(exc)}"}), 502

    info = _parse_debug_output(debug_text)
    ati = _parse_ati_output(ati_text)

    info["operator"] = ati.get("manufacturer", "") + (" " + ati.get("model", "") if ati.get("model") else "")
    info["temperature"] = _parse_temp_output(temp_text)
    info["signal_assessment"] = _assess_signal(info.get("rsrp", "-"), info.get("rsrq", "-"), info.get("snr", "-"))

    raw = "\n\n".join([
        "ATI\n" + ati_text,
        "AT^DEBUG?\n" + debug_text,
        "AT^TEMP?\n" + temp_text,
    ])

    return jsonify({"parsed": info, "raw": raw})


@app.route("/disconnect", methods=["POST"])
def disconnect():
    logger.info("Richiesta POST a /disconnect ricevuta")

    data = request.get_json(force=True)
    token = data.get("token")

    if token:
        logger.info("Disconnessione per token=%s", token[:10] + "...")
        sessions.remove(token)
        logger.info("Sessione chiusa")

    return jsonify({"status": "disconnected"})


if __name__ == "__main__":
    logger.info("Avvio server Flask...")
    app.run(host="0.0.0.0", port=5000, debug=True)
