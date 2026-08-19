export function formatTimestamp(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;

  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const h = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  const s = String(d.getSeconds()).padStart(2, "0");

  return `${y}-${m}-${day} ${h}:${min}:${s}`;
}
