import logging
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

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
            session.client.close()

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
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
sessions = SessionStore()


HTML_PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Remote LTE AT Chat</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 2rem; background: #f5f5f5; }
      form, .panel { background: white; padding: 1rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
      label { display: block; margin-top: 0.5rem; font-weight: bold; }
      input { width: 100%; padding: 0.5rem; margin-top: 0.25rem; box-sizing: border-box; }
      button { margin-top: 1rem; padding: 0.5rem 1rem; font-size: 1rem; }
      #terminal { background: #111; color: #0f0; font-family: monospace; min-height: 200px; padding: 0.75rem; border-radius: 6px; white-space: pre-wrap; }
      #status { margin-top: 0.5rem; }
      .hidden { display: none; }
    </style>
  </head>
  <body>
    <h1>Remote LTE AT Chat</h1>
    <p>Inserisci i dettagli di connessione SSH per il modem MikroTik e prova a stabilire la sessione.</p>
    <div class="panel" style="margin-bottom: 1rem;">
      <h2>Come testare</h2>
      <ol>
        <li>Avvia il server Flask (di default sulla porta 5000) e apri la pagina nel browser.</li>
        <li>Compila i campi Host, Username, Password, Porta e Interfaccia LTE.</li>
        <li>Clicca su <strong>Prova connessione</strong>.</li>
        <li>Se la connessione va a buon fine, comparirà il riquadro "Terminale AT" con il risultato del comando iniziale.</li>
        <li>Digita i comandi AT nel campo dedicato e premi <strong>Invia</strong>; usa <strong>Disconnetti</strong> per chiudere la sessione.</li>
      </ol>
    </div>
    <form id="connection-form">
      <label>Indirizzo IP / Host
        <input name="host" required placeholder="192.168.88.1" />
      </label>
      <label>Username
        <input name="username" required placeholder="admin" />
      </label>
      <label>Password
        <input type="password" name="password" required />
      </label>
      <label>Porta SSH
        <input name="port" type="number" min="1" max="65535" value="22" />
      </label>
      <label>Interfaccia LTE
        <input name="interface" required placeholder="lte1" />
      </label>
      <button type="button" id="connect-button">Prova connessione</button>
      <div id="status"></div>
    </form>

    <div id="terminal-panel" class="panel hidden">
      <h2>Terminale AT</h2>
      <div id="terminal" aria-live="polite"></div>
      <label>Comando AT
        <input id="command-input" placeholder="ati" />
      </label>
      <button id="send-button">Invia</button>
      <button id="disconnect-button">Disconnetti</button>
    </div>

    <script>
      const form = document.getElementById('connection-form');
      const statusEl = document.getElementById('status');
      const terminalPanel = document.getElementById('terminal-panel');
      const terminal = document.getElementById('terminal');
      const commandInput = document.getElementById('command-input');
      const sendButton = document.getElementById('send-button');
      const disconnectButton = document.getElementById('disconnect-button');
      const connectButton = document.getElementById('connect-button');
      let sessionToken = null;

      function appendTerminal(text) {
        terminal.textContent += text + "\n";
        terminal.scrollTop = terminal.scrollHeight;
      }

      async function handleConnect(event) {
        event.preventDefault();
        statusEl.textContent = 'Connessione in corso...';
        const formData = new FormData(form);
        const payload = Object.fromEntries(formData.entries());
        payload.port = Number(payload.port || 22);
        try {
          const response = await fetch('/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          const data = await response.json();
          if (!response.ok) {
            statusEl.textContent = data.error || 'Connessione fallita';
            return;
          }
          sessionToken = data.token;
          statusEl.textContent = 'Connessione stabilita.';
          terminalPanel.classList.remove('hidden');
          appendTerminal('Output iniziale:\n' + data.preview.trim());
          commandInput.focus();
        } catch (error) {
          console.error(error);
          statusEl.textContent = 'Errore durante la connessione.';
        }
      }

      form.addEventListener('submit', handleConnect);
      connectButton.addEventListener('click', handleConnect);

      sendButton.addEventListener('click', async () => {
        if (!sessionToken) return;
        const command = commandInput.value.trim();
        if (!command) return;
        appendTerminal('> ' + command);
        commandInput.value = '';
        try {
          const response = await fetch('/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: sessionToken, command }),
          });
          const data = await response.json();
          if (!response.ok) {
            appendTerminal('Errore: ' + (data.error || 'Impossibile inviare il comando'));
            return;
          }
          appendTerminal(data.output.trim());
        } catch (error) {
          console.error(error);
          appendTerminal('Errore di rete durante l\'invio.');
        }
      });

      disconnectButton.addEventListener('click', async () => {
        if (!sessionToken) return;
        await fetch('/disconnect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: sessionToken })
        });
        terminalPanel.classList.add('hidden');
        terminal.textContent = '';
        statusEl.textContent = 'Sessione terminata.';
        sessionToken = null;
      });
    </script>
  </body>
</html>
"""


def _run_at_command(session: SSHSession, at_command: str) -> str:
    full_command = f"interface/lte/at-chat {session.interface}\ninput: {at_command}"
    stdin, stdout, stderr = session.client.exec_command(full_command, timeout=15)
    output = stdout.read().decode(errors="ignore")
    error_output = stderr.read().decode(errors="ignore")
    return output + ("\n" + error_output if error_output else "")


def _mask_password(password: str) -> str:
    if not password:
        return "<vuoto>"
    if len(password) <= 4:
        return "*" * len(password)
    return f"{password[0]}***{password[-1]} (len={len(password)})"


@app.route("/", methods=["GET"])
def index() -> str:
    return HTML_PAGE


@app.route("/connect", methods=["POST"])
def connect():
    data = request.get_json(force=True)
    required = ["host", "username", "password", "interface"]
    missing = [key for key in required if not data.get(key)]
    if missing:
        return jsonify({"error": f"Campi mancanti: {', '.join(missing)}"}), 400
    host = data["host"].strip()
    username = data["username"].strip()
    password = data["password"]
    interface = data["interface"].strip()
    port = int(data.get("port", 22))

    logger.info(
        "Richiesta connessione ricevuta: host=%s port=%s user=%s interface=%s password=%s",
        host,
        port,
        username,
        interface,
        _mask_password(password),
    )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=10,
        )
    except Exception as exc:  # pragma: no cover - network errors
        logger.exception("Connessione SSH fallita verso %s:%s", host, port)
        return jsonify({"error": f"Connessione SSH fallita: {exc}"}), 502

    session = sessions.add(client, interface, host, username, port)
    try:
        preview = _run_at_command(session, "ati")
    except Exception as exc:  # pragma: no cover - command errors
        sessions.remove(session.token)
        logger.exception(
            "Comando di prova 'ati' fallito per %s@%s:%s (token=%s)",
            username,
            host,
            port,
            session.token,
        )
        return jsonify({"error": f"SSH attivo ma comando non riuscito: {exc}"}), 500

    logger.info(
        "Connessione stabilita (token=%s) per %s@%s:%s su %s. Output iniziale: %s",
        session.token,
        username,
        host,
        port,
        interface,
        (preview.strip()[:300] + "...") if len(preview) > 300 else preview.strip(),
    )
    sessions.cleanup()
    return jsonify({"token": session.token, "preview": preview})


@app.route("/send", methods=["POST"])
def send_command():
    data = request.get_json(force=True)
    token = data.get("token")
    command = (data.get("command") or "").strip()
    if not token or not command:
        return jsonify({"error": "Token o comando mancante."}), 400

    session = sessions.get(token)
    if not session:
        return jsonify({"error": "Sessione non trovata o scaduta."}), 404

    logger.info(
        "Invio comando AT per token=%s (%s@%s:%s su %s): %s",
        token,
        session.username,
        session.host,
        session.port,
        session.interface,
        command,
    )
    try:
        output = _run_at_command(session, command)
    except Exception as exc:  # pragma: no cover - network errors
        sessions.remove(token)
        logger.exception("Errore durante l'esecuzione del comando '%s' (token=%s)", command, token)
        return jsonify({"error": f"Comando fallito: {exc}"}), 502

    logger.info("Comando completato (token=%s): %s", token, command)
    return jsonify({"output": output})


@app.route("/disconnect", methods=["POST"])
def disconnect():
    data = request.get_json(force=True)
    token = data.get("token")
    if token:
        logger.info("Richiesta disconnessione per token=%s", token)
        sessions.remove(token)
        logger.info("Sessione chiusa per token=%s", token)
    return jsonify({"status": "disconnected"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
