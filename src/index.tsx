import {
  ButtonItem,
  Field,
  PanelSection,
  PanelSectionRow,
  SliderField,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin } from "@decky/api";
import { useEffect, useRef, useState } from "react";
import { FaHeadphones } from "react-icons/fa";

type App = { id: string; name: string; chat: boolean; sink: string };
type Status = {
  mode?: "tv" | "portable" | "off";
  warning?: string | null;
  docked?: boolean;
  game_sink?: string | null;
  chat_sink?: string | null;
  chat_kind?: "headphones" | "bluetooth" | "usb" | "speakers" | null;
  apps?: App[];
  error?: string | null;
};
type State = {
  enabled: boolean;
  keep_game_on_tv: boolean;
  split_undocked: boolean;
  chat_rules: string[];
  game_volume: number;
  chat_volume: number;
  status: Status;
};

const getState = callable<[], State>("get_state");
const refresh = callable<[], State>("refresh");
const setEnabled = callable<[boolean], State>("set_enabled");
const setKeepGameOnTv = callable<[boolean], State>("set_keep_game_on_tv");
const setSplitUndocked = callable<[boolean], State>("set_split_undocked");
const setAppChat = callable<[string, boolean], State>("set_app_chat");
const removeRule = callable<[string], State>("remove_rule");
const resetRules = callable<[], State>("reset_rules");
const setVolume = callable<["game" | "chat", number], State>("set_volume");

function VolumeSlider({
  label,
  kind,
  initial,
  onState,
}: {
  label: string;
  kind: "game" | "chat";
  initial: number;
  onState: (s: State) => void;
}) {
  const [value, setValue] = useState(initial);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dragging = useRef(false);

  // sincronizar con el backend solo si el usuario no está moviendo el slider
  useEffect(() => {
    if (!dragging.current) setValue(initial);
  }, [initial]);

  return (
    <SliderField
      label={label}
      value={value}
      min={0}
      max={100}
      step={5}
      showValue
      valueSuffix="%"
      resetValue={100}
      onChange={(v) => {
        setValue(v);
        dragging.current = true;
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(async () => {
          try {
            onState(await setVolume(kind, v));
          } finally {
            dragging.current = false;
          }
        }, 250);
      }}
    />
  );
}

function withTimeout<T>(p: Promise<T>, ms = 4000): Promise<T> {
  return Promise.race([
    p,
    new Promise<T>((_, rej) => setTimeout(() => rej(new Error("timeout")), ms)),
  ]);
}

function Content() {
  const [state, setState] = useState<State | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await withTimeout(getState());
        if (alive) {
          setState(s);
          setBackendError(null);
        }
      } catch (e) {
        console.error("ChatSplitter", e);
        if (alive) setBackendError(String((e as Error)?.message ?? e));
      }
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  if (!state) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <Field
            label={backendError ? "El backend no responde" : "Cargando..."}
            description={
              backendError
                ? `(${backendError}) Decky no está contestando. Reinicia Decky o revisa ~/homebrew/logs/Chat Splitter/.`
                : undefined
            }
          />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const st = state.status || {};
  const kindLabel: Record<string, string> = {
    headphones: "Audífonos (jack)",
    bluetooth: "Audífonos Bluetooth",
    usb: "Audífonos USB",
    speakers: "Bocinas de la Deck",
  };
  const chatLabel = st.chat_kind ? `${kindLabel[st.chat_kind]} · ${st.chat_sink ?? ""}` : "—";
  const modeLabel =
    st.mode === "tv"
      ? "TV: juego en la TV, chat en la Deck"
      : st.mode === "portable"
      ? "Portátil: juego en bocinas, chat en audífonos"
      : "Sin separar (todo suena junto)";

  return (
    <>
      <PanelSection title="Separación de audio">
        <PanelSectionRow>
          <ToggleField
            label="Separar chat y juego"
            description="Activa o desactiva todo el plugin"
            checked={state.enabled}
            onChange={async (v) => setState(await setEnabled(v))}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Separar también sin TV"
            description="Juego en las bocinas de la Deck y chat en audífonos (jack, Bluetooth o USB)"
            checked={state.split_undocked}
            onChange={async (v) => setState(await setSplitUndocked(v))}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Fijar la salida del juego"
            description="Si conectas audífonos, el juego no se muda a ellos"
            checked={state.keep_game_on_tv}
            onChange={async (v) => setState(await setKeepGameOnTv(v))}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Volumen">
        <PanelSectionRow>
          <VolumeSlider label="Juego" kind="game" initial={state.game_volume ?? 100} onState={setState} />
        </PanelSectionRow>
        <PanelSectionRow>
          <VolumeSlider label="Chat" kind="chat" initial={state.chat_volume ?? 100} onState={setState} />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Estado">
        <PanelSectionRow>
          <Field label="Modo" description={modeLabel} focusable />
        </PanelSectionRow>
        {st.mode && st.mode !== "off" && (
          <>
            <PanelSectionRow>
              <Field label="Juego" description={st.game_sink || "—"} focusable />
            </PanelSectionRow>
            <PanelSectionRow>
              <Field label="Chat" description={chatLabel} focusable />
            </PanelSectionRow>
          </>
        )}
        {st.warning && (
          <PanelSectionRow>
            <Field label="Aviso" description={st.warning} focusable />
          </PanelSectionRow>
        )}
        {st.error && (
          <PanelSectionRow>
            <Field label="Error" description={st.error} focusable />
          </PanelSectionRow>
        )}
      </PanelSection>

      <PanelSection title="Apps sonando ahora">
        {(st.apps || []).length === 0 && (
          <PanelSectionRow>
            <Field description="No hay apps reproduciendo audio. Abre Discord o el juego y vuelve aquí." />
          </PanelSectionRow>
        )}
        {(st.apps || []).map((a) => (
          <PanelSectionRow key={a.id}>
            <ToggleField
              label={a.name}
              description={a.chat ? "Chat → Deck" : "Juego → TV"}
              checked={a.chat}
              onChange={async (v) => setState(await setAppChat(a.id, v))}
            />
          </PanelSectionRow>
        ))}
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={async () => setState(await refresh())}>
            Refrescar
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Reglas de chat">
        {state.chat_rules.map((r) => (
          <PanelSectionRow key={r}>
            <ButtonItem
              layout="inline"
              label={r}
              onClick={async () => setState(await removeRule(r))}
            >
              Quitar
            </ButtonItem>
          </PanelSectionRow>
        ))}
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={async () => setState(await resetRules())}>
            Restaurar reglas por defecto
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => ({
  name: "Chat Splitter",
  titleView: <div className={staticClasses.Title}>Chat Splitter</div>,
  content: <Content />,
  icon: <FaHeadphones />,
  onDismount() {},
}));
