import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

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
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Remote LTE AT Chat</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 2rem; background: #f5f5f5; }
      form, .panel { background: white; padding: 1rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 1rem; }
      label { display: block; margin-top: 0.5rem; font-weight: bold; }
      input { width: 100%; padding: 0.5rem; margin-top: 0.25rem; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; }
      button { margin-top: 1rem; padding: 0.5rem 1rem; font-size: 1rem; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
      button:hover { background: #0056b3; }
      button:disabled { background: #ccc; cursor: not-allowed; }
      #terminal { background: #111; color: #0f0; font-family: 'Courier New', monospace; min-height: 300px; max-height: 500px; overflow-y: auto; padding: 0.75rem; border-radius: 6px; white-space: pre-wrap; word-wrap: break-word; }
      #status { margin-top: 0.5rem; font-weight: bold; padding: 0.5rem; border-radius: 4px; }
      .error { background: #ffebee; color: #c62828; }
      .success { background: #e8f5e9; color: #2e7d32; }
      .info { background: #e3f2fd; color: #1565c0; }
      .hidden { display: none; }
      .info-text { color: #666; font-size: 0.9rem; margin-top: 0.25rem; }
      #debug-log { background: #f5f5f5; padding: 0.5rem; border-radius: 4px; font-family: monospace; font-size: 0.8rem; max-height: 150px; overflow-y: auto; margin-top: 1rem; }
    </style>
  </head>
  <body>
    <h1>Remote LTE AT Chat</h1>
    <p>Connettiti al modem LTE MikroTik tramite SSH e invia comandi AT (wrappati in /interface lte at-chat).</p>

    <div class="panel">
      <h2>Istruzioni</h2>
      <ol>
        <li>Compila i campi di connessione SSH (host, username, password)</li>
        <li>Specifica l'interfaccia LTE (es. lte1)</li>
        <li>Clicca su Connetti</li>
        <li>Inserisci comandi AT nel terminale (es: ATI, AT+CSQ, AT+COPS?)</li>
      </ol>
      <p class="info-text">Apri la console del browser (F12) per vedere eventuali errori JavaScript.</p>
    </div>

    <form id="connection-form">
      <h2>Connessione SSH</h2>
      <label>Indirizzo IP / Host
        <input name="host" required placeholder="192.168.88.1" value="192.168.88.1" />
      </label>
      <label>Username
        <input name="username" required placeholder="admin" value="admin" />
      </label>
      <label>Password
        <input type="password" name="password" required />
      </label>
      <label>Porta SSH
        <input name="port" type="number" min="1" max="65535" value="22" />
      </label>
      <label>Interfaccia LTE
        <input name="interface" required placeholder="lte1" value="lte1" />
        <span class="info-text">Nome dell'interfaccia LTE sul router</span>
      </label>
      <button type="button" id="connect-button">Connetti</button>
      <div id="status" class="hidden"></div>
      <div id="debug-log" class="hidden"></div>
    </form>

    <div id="terminal-panel" class="panel hidden">
      <h2>Terminale AT</h2>
      <div id="terminal" aria-live="polite"></div>
      <label>Comando AT
        <input id="command-input" placeholder="ATI" />
        <span class="info-text">Esempi: ATI, AT+CPIN?, AT+CSQ, AT+COPS?</span>
      </label>
      <button id="send-button">Invia</button>
      <button id="disconnect-button" style="background: #dc3545;">Disconnetti</button>
    </div>

    <script>
      const form = document.getElementById('connection-form');
      const statusEl = document.getElementById('status');
      const debugLog = document.getElementById('debug-log');
      const terminalPanel = document.getElementById('terminal-panel');
      const terminal = document.getElementById('terminal');
      const commandInput = document.getElementById('command-input');
      const sendButton = document.getElementById('send-button');
      const disconnectButton = document.getElementById('disconnect-button');
      const connectButton = document.getElementById('connect-button');
      let sessionToken = null;

      function log(message) {
        console.log(message);
        debugLog.classList.remove('hidden');
        const time = new Date().toLocaleTimeString();
        debugLog.textContent += time + ': ' + message + '\\n';
        debugLog.scrollTop = debugLog.scrollHeight;
      }

      function showStatus(message, type) {
        statusEl.classList.remove('hidden', 'error', 'success', 'info');
        statusEl.classList.add(type);
        statusEl.textContent = message;
        log('Status: ' + message);
      }

      function appendTerminal(text, isError) {
        const color = isError ? '#f00' : '#0f0';
        const line = document.createElement('span');
        line.style.color = color;
        line.textContent = text + '\\n';
        terminal.appendChild(line);
        terminal.scrollTop = terminal.scrollHeight;
      }

      async function handleConnect(event) {
        if (event) event.preventDefault();

        log('Bottone Connetti cliccato');
        connectButton.disabled = true;
        showStatus('Connessione in corso...', 'info');

        const formData = new FormData(form);
        const payload = Object.fromEntries(formData.entries());
        payload.port = Number(payload.port || 22);

        const safePayload = Object.assign({}, payload, {password: '***'});
        log('Payload preparato: ' + JSON.stringify(safePayload));

        try {
          log('Invio richiesta a /connect...');
          const response = await fetch('/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });

          log('Risposta ricevuta, status: ' + response.status);
          const data = await response.json();

          if (!response.ok) {
            showStatus('Errore: ' + (data.error || 'Connessione fallita'), 'error');
            connectButton.disabled = false;
            return;
          }

          sessionToken = data.token;
          showStatus('Connessione stabilita!', 'success');
          terminalPanel.classList.remove('hidden');

          appendTerminal('=== Sessione pronta (comandi via /interface lte at-chat) ===');
          appendTerminal(data.preview.trim());
          commandInput.focus();

        } catch (error) {
          log('ERRORE durante fetch: ' + error.message);
          console.error('Errore completo:', error);
          showStatus('Errore: ' + error.message, 'error');
          connectButton.disabled = false;
        }
      }

      connectButton.addEventListener('click', function(e) {
        log('Click event ricevuto');
        handleConnect(e);
      });

      form.addEventListener('submit', function(e) {
        e.preventDefault();
        log('Form submit ricevuto');
        handleConnect(e);
      });

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
            body: JSON.stringify({ token: sessionToken, command: command }),
          });

          const data = await response.json();

          if (!response.ok) {
            appendTerminal('Errore: ' + (data.error || 'Impossibile inviare il comando'), true);
            return;
          }

          appendTerminal(data.output.trim());

        } catch (error) {
          log('ERRORE durante invio comando: ' + error.message);
          console.error('Errore completo:', error);
          appendTerminal('Errore di rete durante invio', true);
        } finally {
          sendButton.disabled = false;
          commandInput.focus();
        }
      });

      disconnectButton.addEventListener('click', async function() {
        if (!sessionToken) return;

        log('Disconnessione richiesta');
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

        terminalPanel.classList.add('hidden');
        terminal.innerHTML = '';
        showStatus('Sessione terminata', 'info');
        sessionToken = null;
        connectButton.disabled = false;
      });

      log('Pagina caricata, JavaScript attivo');
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
