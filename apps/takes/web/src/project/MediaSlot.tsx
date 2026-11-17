import { useRef, useState } from "react";
import { api, mediaUrl } from "../api";
import { mediaName } from "./defaults";

/** A picture or audio file for the generate form: click or drop a file to upload it. */
export function MediaSlot({
  slug,
  kind,
  label,
  value,
  onChange,
}: {
  slug: string;
  kind: "picture" | "audio";
  label: string;
  value: string | null;
  onChange: (id: string | null) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const info = await api.uploadMedia(slug, file);
      if (info.kind !== kind) throw new Error(kind === "picture" ? "Choose a picture" : "Choose an audio file");
      onChange(info.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div
      className={`slot ${kind} ${over ? "over" : ""} ${value ? "filled" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        upload(e.dataTransfer.files[0]);
      }}
    >
      <span className="slot-label">{label}</span>
      {value ? (
        kind === "picture" ? (
          <img src={mediaUrl(slug, value)} alt={label} onClick={() => input.current?.click()} />
        ) : (
          <div className="slot-audio">
            <span className="slot-name" title={mediaName(value)}>
              {mediaName(value)}
            </span>
            <audio src={mediaUrl(slug, value)} controls preload="none" />
          </div>
        )
      ) : (
        <button type="button" className="slot-empty" onClick={() => input.current?.click()} disabled={busy}>
          {busy ? "Uploading…" : `Drop ${kind === "picture" ? "a picture" : "an audio file"} or click`}
        </button>
      )}
      {value && (
        <div className="slot-actions">
          <button type="button" className="link" onClick={() => input.current?.click()}>
            Replace
          </button>
          <button type="button" className="link" onClick={() => onChange(null)}>
            Remove
          </button>
        </div>
      )}
      {error && <span className="error small">{error}</span>}
      <input
        ref={input}
        type="file"
        hidden
        accept={kind === "picture" ? "image/*" : "audio/*"}
        onChange={(e) => upload(e.target.files?.[0])}
      />
    </div>
  );
}
