/** Move list[from] so it lands just before the item that was at index `to` (0..length). */
export function moveItem<T>(list: T[], from: number, to: number): T[] {
  const out = [...list];
  const [item] = out.splice(from, 1);
  out.splice(to > from ? to - 1 : to, 0, item);
  return out;
}
