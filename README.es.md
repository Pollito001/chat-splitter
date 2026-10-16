# Chat Splitter (Decky Loader)

[Read in English](README.md)

Plugin de Decky Loader para la Steam Deck que separa el audio del **chat de voz** (**chat de Steam**, Discord, Vesktop, etc.) del audio del **juego**, para que cada uno suene por una salida distinta.

**Chat de voz de Steam:** el chat de Steam corre dentro del cliente de Steam, así que no se detecta solo. Durante una llamada, abre el panel y, en *Apps sonando ahora*, activa el toggle de **Steam**. Se guarda, así que solo lo haces una vez. Discord y apps parecidas se detectan solas.

> ⚠️ **Aviso:** Este es un proyecto personal, hecho con ayuda de IA (Claude de Anthropic). Se ofrece tal cual, sin garantía. Si decides probarlo, **lo haces bajo tu propio riesgo**.

## Qué hace

| Situación | Juego | Chat |
|---|---|---|
| Conectada a TV, sin audífonos | TV | Bocinas de la Deck |
| Conectada a TV, con audífonos (jack/Bluetooth/USB) | TV | Audífonos |
| Portátil, con audífonos | Bocinas de la Deck | Audífonos |
| Portátil, sin audífonos | Todo junto en las bocinas | |

Cambia solo al conectar o desconectar la TV o los audífonos. Si hay más de unos audífonos conectados, la prioridad es Bluetooth > USB > jack.

> En la Steam Deck **LCD**, las bocinas y el jack son el mismo dispositivo de audio y no pueden sonar a la vez, así que el modo portátil necesita audífonos Bluetooth o USB. En la OLED son dispositivos separados.

## Instalar

1. Descarga `chat-splitter.zip` desde [Releases](https://github.com/Pollito001/chat-splitter/releases).
2. En Modo Juego, abre Decky (`...`) → ⚙️ → **Developer** → activa *Developer mode*.
3. En **Developer**, escoge *Install Plugin from ZIP File* y selecciona el zip.
   (Alternativa: descomprímelo en `~/homebrew/plugins/` y reinicia Decky.)

## Uso

Abre el panel **Chat Splitter** en el menú de acceso rápido:

- **Separar chat y juego**: activa o desactiva todo el plugin.
- **Separar también sin TV**: activa el modo portátil (juego en bocinas, chat en audífonos).
- **Fijar la salida del juego**: SteamOS suele mudar todo el audio a los audífonos cuando los conectas; esto deja el juego en la TV o en las bocinas.
- **Volumen**: sliders separados para juego y chat.
- **Apps sonando ahora**: lista todo lo que está reproduciendo audio. Activa el toggle de cualquier app para tratarla como chat (por ejemplo, el chat de voz de Steam o un navegador). Se guarda como regla.
- **Reglas de chat**: palabras clave que identifican apps de chat. Por defecto: discord, vesktop, webcord, armcord, legcord.

## Notas técnicas

- Usa `pactl` (pipewire-pulse) como el usuario `deck`; no necesita root.
- Reacciona a los eventos de audio con `pactl subscribe` y revisa cada 5 segundos como respaldo.
- Al desactivarlo o desinstalarlo, le devuelve a SteamOS el control de la salida y pone los volúmenes en 100%.
- El chat de voz de Steam corre dentro del cliente de Steam. Si lo marcas como chat, los sonidos de la interfaz de Steam también se van a la salida del chat.
- Probado en Steam Deck OLED. Otros equipos con SteamOS (como el Legion Go S) tienen otro hardware de audio y probablemente necesitan ajustes.

## Compilar desde el código

```bash
npm install
npm run build
```

Después empaqueta `dist/index.js`, `main.py`, `plugin.json`, `package.json` y `README.md` dentro de una carpeta `Chat Splitter/` y comprímela en zip.

## Licencia

BSD-3-Clause
