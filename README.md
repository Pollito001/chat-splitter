# Chat Splitter (Decky Loader)

🇪🇸 [Leer en español](README.es.md)

A Decky Loader plugin for the Steam Deck that splits **chat** audio (Discord, Vesktop, etc.) from **game** audio, so each one plays on a different output.

> ⚠️ **Disclaimer:** This is a personal project, built with the help of AI (Claude by Anthropic). It is provided as-is, with no warranty. If you decide to try it, **you do so at your own risk**.

## What it does

| Situation | Game | Chat |
|---|---|---|
| Docked to TV, no headphones | TV | Steam Deck speakers |
| Docked to TV, with headphones (jack/Bluetooth/USB) | TV | Headphones |
| Handheld, with headphones | Steam Deck speakers | Headphones |
| Handheld, no headphones | Everything together on the speakers | |

It switches automatically when you plug or unplug the TV or headphones. If more than one pair of headphones is connected, the priority is Bluetooth > USB > jack.

> On the Steam Deck **LCD**, the speakers and the headphone jack are the same audio device and can't play at the same time, so handheld mode needs Bluetooth or USB headphones. On the OLED they are separate devices.

## Install

1. Download `chat-splitter.zip` from [Releases](https://github.com/Pollito001/chat-splitter/releases).
2. In Game Mode, open Decky (`...`) → ⚙️ → **Developer** → turn on *Developer mode*.
3. In **Developer**, choose *Install Plugin from ZIP File* and pick the zip.
   (Alternative: unzip it into `~/homebrew/plugins/` and restart Decky.)

## Usage

Open the **Chat Splitter** panel in the Quick Access menu:

- **Split chat and game** (*Separar chat y juego*): turns the whole plugin on or off.
- **Split without TV too** (*Separar también sin TV*): enables handheld mode (game on speakers, chat on headphones).
- **Lock game output** (*Fijar la salida del juego*): SteamOS usually moves all audio to headphones when you plug them in; this keeps the game on the TV or speakers.
- **Volume**: separate sliders for game and chat.
- **Apps playing now**: lists everything that is playing audio. Toggle any app to treat it as chat (for example, Steam voice chat or a browser). It is saved as a rule.
- **Chat rules**: keywords that identify chat apps. Defaults: discord, vesktop, webcord, armcord, legcord.

The panel itself is in Spanish; the labels above include the Spanish text you'll see.

## Technical notes

- Uses `pactl` (pipewire-pulse) as the `deck` user; it doesn't need root.
- Reacts to audio events with `pactl subscribe`, with a 5-second check as a fallback.
- When disabled or uninstalled, it hands output selection back to SteamOS and resets volumes to 100%.
- Steam voice chat runs inside the Steam client. If you mark it as chat, Steam's interface sounds will also go to the chat output.
- Tested on a Steam Deck OLED. Other SteamOS handhelds (e.g. Legion Go S) use different audio hardware and probably need adjustments.

## Build from source

```bash
npm install
npm run build
```

Then package `dist/index.js`, `main.py`, `plugin.json`, `package.json` and `README.md` inside a `Chat Splitter/` folder and zip it.

## License

BSD-3-Clause
