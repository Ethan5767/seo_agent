import type { MonitorWidget } from "./types";

/** Pure widget actions used by the Monitor UI and its interaction tests. */
export function moveWidget(widgets: MonitorWidget[], index: number, direction: "left" | "right"): MonitorWidget[] {
  const target = direction === "left" ? index - 1 : index + 1;
  if (index < 0 || index >= widgets.length || target < 0 || target >= widgets.length) return widgets;
  const next = [...widgets];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export function saveWidget(widgets: MonitorWidget[], saved: MonitorWidget): MonitorWidget[] {
  const index = widgets.findIndex((widget) => widget.id === saved.id);
  if (index < 0) return [...widgets, saved];
  const next = [...widgets];
  next[index] = saved;
  return next;
}

export function deleteWidget(widgets: MonitorWidget[], id: string): MonitorWidget[] {
  return widgets.filter((widget) => widget.id !== id);
}
