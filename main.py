"""
Chat Splitter - backend de Decky Loader.

Idea:
  * El juego (y todo lo demás) sigue la salida por defecto -> la TV (HDMI/DP).
  * Los streams que coinciden con las reglas de "chat" (Discord, Vesktop, etc.)
    se mueven a la salida interna de la Deck:
        - audífonos (jack 3.5mm) si están conectados
        - bocinas de la Deck si no
  * Opcional: si al conectar audífonos WirePlumber cambia la salida por defecto
    a la Deck, la regresamos a la TV para que el juego no se mueva.

Todo se hace con `pactl` (pipewire-pulse), corriendo como el usuario `deck`.
"""

import asyncio
import json
import os
import pwd
import shutil

import decky

_SETTINGS_DIR = (
    getattr(decky, "DECKY_PLUGIN_SETTINGS_DIR", None)
    or os.environ.get("DECKY_PLUGIN_SETTINGS_DIR")
    or os.path.join(
        getattr(decky, "DECKY_USER_HOME", None) or os.path.expanduser("~deck"),
        "homebrew", "settings", "Chat Splitter",
    )
)
SETTINGS_FILE = os.path.join(_SETTINGS_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "enabled": True,
    "keep_game_on_tv": True,
    "split_undocked": True,
    # Palabras clave (minúsculas) que se buscan en application.name / process.binary
    "chat_rules": ["discord", "vesktop", "webcord", "armcord", "legcord"],
    "last_external_sink": "",
    "game_volume": 100,
    "chat_volume": 100,
}

# Pistas para reconocer la salida interna de la Steam Deck (LCD = acp5x, OLED = SOF + nau8821)
INTERNAL_HINTS = ("nau8821", "acp5x", "acp6x", "amd_sof", "sof-nau", "acp-")
IGNORED_SINK_HINTS = ("null", "easyeffects", "monitor", "dummy", "auto_null")


class Plugin:
    settings: dict = {}
    moved: dict = {}  # sink-input index -> node id de PipeWire (object.id)
    vol_applied: dict = {}  # sink-input index -> % aplicado
    overrode_default: bool = False
    natural_default: str = ""
    status: dict = {}
    _tasks: list = []
    _apply_event: asyncio.Event | None = None
    _lock: asyncio.Lock | None = None

    # ------------------------------------------------------------------ util
    def _env(self) -> dict:
        env = dict(os.environ)
        # Decky empaqueta Python con PyInstaller; LD_LIBRARY_PATH rompe binarios del sistema
        env.pop("LD_LIBRARY_PATH", None)
        env.pop("LD_PRELOAD", None)
        uid = os.getuid()
        if uid == 0:
            try:
                uid = pwd.getpwnam(getattr(decky, "DECKY_USER", None) or "deck").pw_uid
            except Exception:
                uid = 1000
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
        env.setdefault("PULSE_SERVER", f"unix:/run/user/{uid}/pulse/native")
        env["LC_ALL"] = "C"
        return env

    def _pactl_path(self) -> str:
        return shutil.which("pactl", path="/usr/bin:/bin:/usr/local/bin") or "/usr/bin/pactl"

    async def _pactl(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            self._pactl_path(), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env(),
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"pactl {' '.join(args)}: {err.decode(errors='ignore').strip()}")
        return out.decode(errors="ignore")

    async def _pw_metadata(self, *args: str) -> bool:
        """Corre pw-metadata; devuelve True si funcionó."""
        exe = shutil.which("pw-metadata", path="/usr/bin:/bin:/usr/local/bin") or "/usr/bin/pw-metadata"
        try:
            proc = await asyncio.create_subprocess_exec(
                exe, *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                env=self._env(),
            )
            _, err = await proc.communicate()
            if proc.returncode != 0:
                decky.logger.warning(f"pw-metadata {' '.join(args)}: {err.decode(errors='ignore').strip()}")
            return proc.returncode == 0
        except Exception as e:
            decky.logger.warning(f"pw-metadata no disponible: {e}")
            return False

    async def _set_default(self, sink: str, current: str):
        """Fija la salida por defecto, recordando la que SteamOS había escogido."""
        if not self.overrode_default:
            self.natural_default = current
            self.overrode_default = True
        await self._pactl("set-default-sink", sink)

    async def _release_default(self):
        """Quita la salida por defecto que puso el plugin para que SteamOS vuelva a escoger sola."""
        if not self.overrode_default:
            return
        self.overrode_default = False
        ok = await self._pw_metadata("-d", "0", "default.configured.audio.sink")
        if not ok and self.natural_default:
            try:
                await self._pactl("set-default-sink", self.natural_default)
            except Exception as e:
                decky.logger.warning(f"No pude restaurar la salida por defecto: {e}")
        decky.logger.info("Salida por defecto liberada")
        await asyncio.sleep(0.4)  # darle tiempo a WirePlumber para escoger

    async def _pactl_json(self, *args: str):
        out = await self._pactl("-f", "json", *args)
        return json.loads(out) if out.strip() else []

    def _load_settings(self):
        data = dict(DEFAULT_SETTINGS)
        try:
            with open(SETTINGS_FILE, "r") as f:
                data.update(json.load(f))
        except FileNotFoundError:
            pass
        except Exception as e:
            decky.logger.error(f"No pude leer settings: {e}")
        self.settings = data

    def _save_settings(self):
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            decky.logger.error(f"No pude guardar settings: {e}")

    # -------------------------------------------------------- clasificación
    @staticmethod
    def _sink_text(sink: dict) -> str:
        props = sink.get("properties", {})
        return " ".join([
            sink.get("name", ""),
            props.get("device.description", ""),
            props.get("alsa.card_name", ""),
            props.get("device.bus", ""),
            props.get("device.api", ""),
            props.get("device.form_factor", ""),
        ]).lower()

    def _is_ignored(self, sink: dict) -> bool:
        name = sink.get("name", "").lower()
        return any(h in name for h in IGNORED_SINK_HINTS)

    def _kind(self, sink: dict) -> str:
        """'bluetooth' | 'usb' | 'display' | 'internal' | 'other'"""
        txt = self._sink_text(sink)
        name = sink.get("name", "").lower()
        if name.startswith("bluez") or "bluez" in txt or "bluetooth" in txt:
            return "bluetooth"
        if "hdmi" in txt or "displayport" in txt:
            return "display"
        if name.startswith("alsa_output.usb") or " usb" in txt:
            return "usb"
        if any(h in txt for h in INTERNAL_HINTS):
            return "internal"
        return "other"

    @staticmethod
    def _port_available(port: dict) -> bool:
        return str(port.get("availability", "")).lower() not in ("not available", "no")

    @staticmethod
    def _is_headphone_port(port: dict) -> bool:
        txt = (port.get("name", "") + " " + port.get("description", "")).lower()
        return ("headphone" in txt or "headset" in txt) and "mic" not in txt

    @staticmethod
    def _is_speaker_port(port: dict) -> bool:
        txt = (port.get("name", "") + " " + port.get("description", "")).lower()
        return "speaker" in txt

    def _jack_target(self, internal: list):
        """(sink, port) de los audífonos de jack si están conectados."""
        for sink in internal:
            for port in sink.get("ports", []):
                if self._is_headphone_port(port) and self._port_available(port):
                    return sink["name"], port["name"]
        return None, None

    def _speaker_target(self, internal: list):
        """(sink, port) de las bocinas de la Deck."""
        for sink in internal:
            for port in sink.get("ports", []):
                if self._is_speaker_port(port):
                    return sink["name"], port["name"]
        for sink in internal:
            if "speaker" in sink.get("name", "").lower():
                return sink["name"], None
        if internal:
            return internal[0]["name"], None
        return None, None

    def _app_id(self, si: dict) -> str:
        props = si.get("properties", {})
        return (props.get("application.process.binary")
                or props.get("application.name")
                or props.get("media.name")
                or "desconocido")

    def _is_chat(self, si: dict) -> bool:
        props = si.get("properties", {})
        hay = " ".join([
            props.get("application.name", ""),
            props.get("application.process.binary", ""),
            props.get("application.id", ""),
            props.get("pipewire.access.portal.app_id", ""),
        ]).lower()
        return any(rule and rule in hay for rule in self.settings.get("chat_rules", []))

    # ------------------------------------------------------------- lógica
    async def _apply(self):
        assert self._lock is not None
        async with self._lock:
            try:
                await self._apply_inner()
            except Exception as e:
                decky.logger.error(f"apply falló: {e}")
                self.status["error"] = str(e)

    async def _apply_inner(self):
        sinks = [s for s in await self._pactl_json("list", "sinks") if not self._is_ignored(s)]
        inputs = await self._pactl_json("list", "sink-inputs")
        default = (await self._pactl("get-default-sink")).strip()

        by_index = {s.get("index"): s for s in sinks}
        kinds = {s["name"]: self._kind(s) for s in sinks}
        internal = [s for s in sinks if kinds[s["name"]] == "internal"]
        displays = [s for s in sinks if kinds[s["name"]] in ("display", "other")]
        display_names = [s["name"] for s in displays]

        enabled = self.settings.get("enabled", True)
        split_undocked = self.settings.get("split_undocked", True)

        # --- salida de pantalla (TV)
        display_sink = None
        if default in display_names:
            display_sink = default
        elif self.settings.get("last_external_sink") in display_names:
            display_sink = self.settings["last_external_sink"]
        elif displays:
            hdmi = [s for s in displays if kinds[s["name"]] == "display"]
            display_sink = (hdmi or displays)[0]["name"]
        if display_sink and display_sink != self.settings.get("last_external_sink"):
            self.settings["last_external_sink"] = display_sink
            self._save_settings()
        docked = display_sink is not None

        # --- audífonos personales: Bluetooth > USB > jack
        jack_sink, jack_port = self._jack_target(internal)
        speaker_sink, speaker_port = self._speaker_target(internal)
        personal = None  # (sink, port, kind)
        for s in sinks:
            if kinds[s["name"]] == "bluetooth":
                personal = (s["name"], None, "bluetooth")
                break
        if not personal:
            for s in sinks:
                if kinds[s["name"]] == "usb":
                    personal = (s["name"], None, "usb")
                    break
        if not personal and jack_sink:
            personal = (jack_sink, jack_port, "headphones")

        # --- decidir rutas
        mode = "off"
        game_sink = game_port = chat_sink = chat_port = None
        chat_kind = None
        warning = None
        if docked:
            mode = "tv"
            game_sink = display_sink
            if personal:
                chat_sink, chat_port, chat_kind = personal
            else:
                chat_sink, chat_port, chat_kind = speaker_sink, speaker_port, "speakers"
        elif personal and split_undocked:
            # Modo portátil: juego en bocinas, chat en audífonos
            if personal[2] == "headphones" and speaker_sink == jack_sink:
                # Deck LCD: bocinas y jack son el mismo dispositivo, no pueden sonar a la vez
                warning = "Con audífonos de jack este modelo no puede usar las bocinas a la vez. Usa audífonos Bluetooth."
            elif speaker_sink:
                mode = "portable"
                game_sink, game_port = speaker_sink, speaker_port
                chat_sink, chat_port, chat_kind = personal
            else:
                warning = "No encontré las bocinas de la Deck mientras hay audífonos conectados."

        active = enabled and mode != "off"

        # --- el juego sigue la salida por defecto: fijarla
        if active and game_sink and self.settings.get("keep_game_on_tv", True) and default != game_sink:
            decky.logger.info(f"Default {default} -> {game_sink} (modo {mode})")
            await self._set_default(game_sink, default)
            default = game_sink
        elif (not active or not self.settings.get("keep_game_on_tv", True)) and self.overrode_default:
            # Ya no hace falta fijar la salida: devolverle el control a SteamOS
            await self._release_default()
            default = (await self._pactl("get-default-sink")).strip()

        # --- puertos correctos (sinks con varios puertos)
        if active:
            for sink_name, port in ((chat_sink, chat_port), (game_sink, game_port)):
                if not sink_name or not port:
                    continue
                sink = next((s for s in sinks if s["name"] == sink_name), None)
                if sink and sink.get("active_port") != port and len(sink.get("ports", [])) > 1:
                    try:
                        await self._pactl("set-sink-port", sink_name, port)
                    except Exception as e:
                        decky.logger.warning(f"No pude cambiar puerto: {e}")

        apps = []
        live_ids = set()
        for si in inputs:
            idx = si.get("index")
            live_ids.add(idx)
            current = by_index.get(si.get("sink"), {}).get("name", "")
            is_chat = self._is_chat(si)
            # Mover también si ya está ahí pero no amarrado: si no, se va detrás de la salida por defecto
            if active and is_chat and chat_sink and (current != chat_sink or idx not in self.moved):
                try:
                    await self._pactl("move-sink-input", str(idx), chat_sink)
                    self.moved.setdefault(idx, si.get("properties", {}).get("object.id"))
                    current = chat_sink
                    decky.logger.info(f"Chat '{self._app_id(si)}' -> {chat_sink}")
                except Exception as e:
                    decky.logger.warning(f"No pude mover {idx}: {e}")
            elif (not active or not is_chat) and idx in self.moved:
                await self._restore_one(idx, default)
                current = default
            # Volumen por stream: chat vs juego
            if enabled:
                key = "chat_volume" if is_chat else "game_volume"
                target = int(self.settings.get(key, 100))
                if self.vol_applied.get(idx) != target:
                    try:
                        await self._pactl("set-sink-input-volume", str(idx), f"{target}%")
                        self.vol_applied[idx] = target
                    except Exception as e:
                        decky.logger.warning(f"No pude ajustar volumen de {idx}: {e}")
            apps.append({
                "id": self._app_id(si),
                "name": self._app_id(si),
                "chat": is_chat,
                "sink": current,
            })

        for idx in list(self.moved):
            if idx not in live_ids:
                self.moved.pop(idx, None)
        for idx in list(self.vol_applied):
            if idx not in live_ids:
                self.vol_applied.pop(idx, None)

        seen = {}
        for a in apps:
            seen.setdefault(a["id"], a)

        desc = {s["name"]: s.get("description", s["name"]) for s in sinks}
        self.status = {
            "mode": mode,
            "docked": docked,
            "game_sink": desc.get(game_sink, game_sink) if game_sink else None,
            "chat_sink": desc.get(chat_sink, chat_sink) if chat_sink else None,
            "chat_kind": chat_kind,
            "apps": list(seen.values()),
            "sinks": {s["name"]: kinds[s["name"]] for s in sinks},
            "warning": warning,
            "error": None,
        }
    async def _restore_one(self, idx, target):
        """Regresa un stream de chat y lo 'suelta' para que siga la salida por defecto."""
        node_id = self.moved.pop(idx, None)
        if target:
            try:
                await self._pactl("move-sink-input", str(idx), target)
            except Exception:
                pass
        if node_id:
            # move-sink-input amarra el stream a esa salida; borrar el amarre
            await self._pw_metadata("-d", str(node_id), "target.object")
            await self._pw_metadata("-d", str(node_id), "target.node")

    async def _restore_all(self):
        await self._release_default()
        try:
            default = (await self._pactl("get-default-sink")).strip()
        except Exception:
            return
        for idx in list(self.moved):
            await self._restore_one(idx, default)
        for idx in list(self.vol_applied):
            try:
                await self._pactl("set-sink-input-volume", str(idx), "100%")
            except Exception:
                pass
        self.vol_applied.clear()

    # --------------------------------------------------------- bucles
    def _trigger(self):
        if self._apply_event:
            self._apply_event.set()

    async def _apply_loop(self):
        assert self._apply_event is not None
        while True:
            try:
                await asyncio.wait_for(self._apply_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
            self._apply_event.clear()
            await asyncio.sleep(0.3)  # debounce
            self._apply_event.clear()
            await self._apply()

    async def _subscribe_loop(self):
        while True:
            try:
                proc = await asyncio.create_subprocess_exec(
                    self._pactl_path(), "subscribe",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=self._env(),
                )
                assert proc.stdout is not None
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    text = line.decode(errors="ignore")
                    if ("'new'" in text or "'change'" in text or "'remove'" in text) and (
                        "sink" in text or "card" in text or "server" in text
                    ):
                        self._trigger()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                decky.logger.warning(f"pactl subscribe cayó: {e}")
            await asyncio.sleep(2)

    # ------------------------------------------------------ API frontend
    async def get_state(self):
        return {
            "enabled": self.settings.get("enabled", True),
            "keep_game_on_tv": self.settings.get("keep_game_on_tv", True),
            "split_undocked": self.settings.get("split_undocked", True),
            "chat_rules": self.settings.get("chat_rules", []),
            "game_volume": int(self.settings.get("game_volume", 100)),
            "chat_volume": int(self.settings.get("chat_volume", 100)),
            "status": self.status,
        }

    async def set_volume(self, kind: str, value: int):
        if kind not in ("game", "chat"):
            return await self.get_state()
        value = max(0, min(150, int(value)))
        self.settings[f"{kind}_volume"] = value
        self._save_settings()
        self.vol_applied.clear()  # forzar que se reaplique a todos los streams
        return await self.refresh()

    async def refresh(self):
        await self._apply()
        return await self.get_state()

    async def set_enabled(self, value: bool):
        self.settings["enabled"] = bool(value)
        self._save_settings()
        if not value:
            await self._restore_all()
        return await self.refresh()

    async def set_keep_game_on_tv(self, value: bool):
        self.settings["keep_game_on_tv"] = bool(value)
        self._save_settings()
        return await self.refresh()

    async def set_split_undocked(self, value: bool):
        self.settings["split_undocked"] = bool(value)
        self._save_settings()
        return await self.refresh()

    async def set_app_chat(self, app_id: str, is_chat: bool):
        key = (app_id or "").strip().lower()
        if not key:
            return await self.get_state()
        rules = [r for r in self.settings.get("chat_rules", []) if r]
        if is_chat and key not in rules:
            rules.append(key)
        elif not is_chat:
            # quitar cualquier regla que haga match con esta app
            rules = [r for r in rules if r not in key and key not in r]
        self.settings["chat_rules"] = rules
        self._save_settings()
        return await self.refresh()

    async def remove_rule(self, rule: str):
        self.settings["chat_rules"] = [r for r in self.settings.get("chat_rules", []) if r != rule]
        self._save_settings()
        return await self.refresh()

    async def reset_rules(self):
        self.settings["chat_rules"] = list(DEFAULT_SETTINGS["chat_rules"])
        self._save_settings()
        return await self.refresh()

    # --------------------------------------------------- ciclo de vida
    async def _main(self):
        self._load_settings()
        self._apply_event = asyncio.Event()
        self._lock = asyncio.Lock()
        loop = asyncio.get_event_loop()
        self._tasks = [
            loop.create_task(self._apply_loop()),
            loop.create_task(self._subscribe_loop()),
        ]
        self._trigger()
        decky.logger.info("Chat Splitter iniciado")

    async def _unload(self):
        for t in self._tasks:
            t.cancel()
        self._tasks = []
        await self._restore_all()
        decky.logger.info("Chat Splitter detenido")

    async def _uninstall(self):
        pass
