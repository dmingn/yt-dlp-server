function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { hour12: false });
}

export function toDatetimeLocalValue(iso: string): string {
  const d = new Date(iso);
  return (
    `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}` +
    `T${pad2(d.getHours())}:${pad2(d.getMinutes())}`
  );
}
