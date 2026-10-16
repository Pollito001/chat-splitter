# Chat Splitter (Decky Loader)

Separa el audio del **chat** (Discord, Vesktop, etc.) del audio del **juego**:

| Situación | Juego | Chat |
|---|---|---|
| Conectada a TV, sin audífonos | TV | Bocinas de la Deck |
| Conectada a TV, con audífonos (jack/Bluetooth/USB) | TV | Audífonos |
| Portátil, con audífonos | Bocinas de la Deck | Audífonos |
| Portátil, sin audífonos | Todo junto en las bocinas | |

Cambia solo al conectar/desconectar la TV o los audífonos. Si hay varios audífonos
conectados, la prioridad es Bluetooth > USB > jack.

> En la Steam Deck **LCD**, las bocinas y el jack son el mismo dispositivo y no pueden
> sonar a la vez; en modo portátil usa audífonos Bluetooth. En la OLED son
> dispositivos separados, así que deberían poder sonar a la vez.

## Instalar

1. En Modo Escritorio, copia `chat-splitter.zip` a la Deck.
2. Modo Juego → menú de Decky (`...`) → engranaje ⚙️ → **Developer** → activa *Developer mode*.
3. En **Developer** → *Install Plugin from ZIP File* → elige el zip.
   (Alternativa: descomprímelo en `~/homebrew/plugins/` y reinicia Decky.)

## Uso

Abre el panel **Chat Splitter** en el menú de acceso rápido:

- **Separar chat y juego**: activa/desactiva todo el plugin.
- **Separar también sin TV**: activa el modo portátil (juego en bocinas, chat en audífonos).
- **Fijar la salida del juego**: SteamOS suele mudar todo el audio a los audífonos
  cuando los conectas; esto lo regresa a la TV o a las bocinas.
- **Volumen**: sliders separados para juego y chat.
- **Apps sonando ahora**: lista todo lo que está reproduciendo audio. Activa el
  toggle de cualquier app para tratarla como chat (por ejemplo, el chat de voz de
  Steam o un navegador). Se guarda como regla.
- **Reglas de chat**: palabras clave que identifican apps de chat. Por defecto:
  discord, vesktop, webcord, armcord, legcord.

## Notas técnicas

- Usa `pactl` (pipewire-pulse) como el usuario `deck`; no necesita root.
- Reacciona a eventos con `pactl subscribe` y revisa cada 5 s como respaldo.
- Al desactivar o desinstalar, los streams movidos vuelven a la salida por defecto.
- El chat de voz de Steam corre dentro del cliente de Steam. Si quieres separarlo,
  actívalo desde *Apps sonando ahora* mientras hablas; ojo que eso también moverá
  los sonidos de la interfaz de Steam a la Deck.

## Compilar

```bash
npm install
npm run build
```
