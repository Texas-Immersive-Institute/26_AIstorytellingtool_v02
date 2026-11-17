import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useChat } from "../run/useRun";

const ID_KEY = "story-chat-participant";
const NAME_KEY = "story-chat-name";

/** A random id for this device, kept across reloads, so thumbs-ups count once per person. */
function participantId(): string {
  let id = localStorage.getItem(ID_KEY);
  if (!id || !/^[A-Za-z0-9_-]{6,40}$/.test(id)) {
    // getRandomValues works on plain-http LAN pages; randomUUID needs HTTPS or localhost.
    const bytes = crypto.getRandomValues(new Uint8Array(8));
    id = `p-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
    localStorage.setItem(ID_KEY, id);
  }
  return id;
}

/** The Chat view: what each audience member opens on their phone or laptop. */
export function Chat() {
  const [me] = useState(participantId);
  const [name, setName] = useState(() => localStorage.getItem(NAME_KEY) ?? "");
  const [draftName, setDraftName] = useState(name);
  const { snap, remaining, connected } = useChat();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [voted, setVoted] = useState<Set<string>>(new Set());
  const feed = useRef<HTMLUListElement>(null);

  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight });
  }, [snap?.messages?.length]);

  if (!name)
    return (
      <div className="chat chat-join">
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            const n = draftName.trim().slice(0, 24);
            if (!n) return;
            localStorage.setItem(NAME_KEY, n);
            setName(n);
          }}
        >
          <h1>Join the story</h1>
          <label>
            Your name
            <input value={draftName} maxLength={24} autoFocus onChange={(e) => setDraftName(e.target.value)} />
          </label>
          <button className="primary" disabled={!draftName.trim()}>
            Join
          </button>
        </form>
      </div>
    );

  async function send(message: string) {
    const body = message.trim();
    if (!body) return;
    setError(null);
    try {
      await api.chatSend(me, name, body);
      setText("");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const win = snap?.active ? snap.window : null;
  const left = remaining();

  return (
    <div className="chat">
      <header className="chat-top">
        <strong>{snap?.active ? snap.title : "Story"}</strong>
        <span className="muted">
          {name}
          {!connected && " · reconnecting…"}
        </span>
      </header>

      {!snap?.active ? (
        <p className="chat-wait muted">Waiting for the story to start…</p>
      ) : win ? (
        <section className={`chat-window ${win.kind}`}>
          <div className="chat-prompt">{win.prompt || (win.kind === "choice" ? "What happens next?" : "Tell us…")}</div>
          {left !== null && <div className="chat-countdown">{Math.ceil(left)}s</div>}
          {win.options.length > 0 && (
            <div className="chat-options">
              {win.options.map((o) => (
                <button key={o.id} onClick={() => send(o.label)}>
                  {o.label}
                </button>
              ))}
            </div>
          )}
          <div className="muted small">{win.kind === "choice" ? "Tap an option or say it your own way." : "Say anything — the best ideas shape the story."}</div>
        </section>
      ) : (
        snap.line && (
          <section className="chat-line">
            {snap.line.speaker_name && <strong>{snap.line.speaker_name}: </strong>}
            {snap.line.text}
          </section>
        )
      )}

      <ul className="chat-feed" ref={feed}>
        {(snap?.messages ?? []).map((m) => {
          const mine = m.author_id === me;
          return (
            <li key={m.id} className={mine ? "mine" : ""}>
              <span className="who">{m.author}</span> {m.text}
              <button
                className="thumb"
                disabled={mine || voted.has(m.id)}
                title={mine ? "Your message" : "Thumbs-up gives this message more weight"}
                onClick={async () => {
                  setVoted(new Set(voted).add(m.id));
                  await api.chatThumbs(m.id, me).catch(() => undefined);
                }}
              >
                👍 {m.thumbs || ""}
              </button>
            </li>
          );
        })}
      </ul>

      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          void send(text);
        }}
      >
        <input value={text} maxLength={280} placeholder={snap?.active ? "Say something…" : "The story hasn't started"} onChange={(e) => setText(e.target.value)} />
        <button className="primary" disabled={!text.trim() || !snap?.active}>
          Send
        </button>
      </form>
      {error && <p className="error small chat-error">{error}</p>}
    </div>
  );
}
