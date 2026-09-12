const KEY = "redacted-field-notes-v1";

export type FieldNote = {
  id: string;
  body: string;
  at: number;
};

function read(): FieldNote[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as FieldNote[];
    return Array.isArray(parsed) ? parsed.slice(0, 40) : [];
  } catch {
    return [];
  }
}

function write(notes: FieldNote[]) {
  localStorage.setItem(KEY, JSON.stringify(notes.slice(0, 40)));
}

export function listNotes(): FieldNote[] {
  return read();
}

export function addNote(body: string): FieldNote[] {
  const trimmed = body.trim().slice(0, 400);
  if (!trimmed) return read();
  const next = [{ id: crypto.randomUUID(), body: trimmed, at: Date.now() }, ...read()];
  write(next);
  return next;
}

export function removeNote(id: string): FieldNote[] {
  const next = read().filter((n) => n.id !== id);
  write(next);
  return next;
}

const CHAMBER_KEY = "redacted-chamber-log-v1";

export type ChamberLog = {
  id: string;
  at: number;
  proposal: string;
  verdict: string;
};

export function listChamberLog(): ChamberLog[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(CHAMBER_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ChamberLog[];
    return Array.isArray(parsed) ? parsed.slice(0, 12) : [];
  } catch {
    return [];
  }
}

export function pushChamberLog(entry: Omit<ChamberLog, "id" | "at">): ChamberLog[] {
  const next = [
    { ...entry, id: crypto.randomUUID(), at: Date.now() },
    ...listChamberLog(),
  ].slice(0, 12);
  localStorage.setItem(CHAMBER_KEY, JSON.stringify(next));
  return next;
}
