import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";

dayjs.extend(relativeTime);

export const ENVIRONMENTS = {
  indoor: "Indoor",
  outdoor: "Outdoor",
  greenhouse: "Greenhouse",
  covered: "Covered / porch",
} as const;

export const ASPECTS = {
  N: "North",
  NE: "North-east",
  E: "East",
  SE: "South-east",
  S: "South",
  SW: "South-west",
  W: "West",
  NW: "North-west",
  none: "No particular aspect",
} as const;

export const SUN_EXPOSURES = {
  full_sun: "Full sun",
  part_shade: "Part shade",
  shade: "Shade",
} as const;

export const LEVELS = { low: "Low", medium: "Medium", high: "High" } as const;

export const SPOT_TYPES = {
  windowsill: "Windowsill",
  shelf: "Shelf",
  table: "Table / surface",
  floor: "Floor",
  hanging: "Hanging (indoor)",
  flowerbed: "Flowerbed",
  border: "Border",
  raised_bed: "Raised bed",
  vegetable_patch: "Vegetable patch",
  pot: "Pot / container",
  hanging_basket: "Hanging basket",
  window_box: "Window box",
  lawn: "Lawn",
  greenhouse_bench: "Greenhouse bench",
  other: "Other",
} as const;

export const STATUSES = {
  active: "Active",
  dead: "Dead",
  removed: "Removed",
  given_away: "Given away",
} as const;

export const STATUS_COLORS: Record<string, string> = {
  active: "green",
  dead: "red",
  removed: "gray",
  given_away: "blue",
};

export const SOURCES = {
  bought: "Bought",
  seed: "Grown from seed",
  cutting: "Cutting",
  division: "Division",
  gift: "Gift",
  other: "Other",
} as const;

export const EVENT_TYPES: Record<string, string> = {
  acquired: "Acquired",
  planted: "Planted",
  moved: "Moved",
  transplanted: "Transplanted",
  repotted: "Repotted",
  died: "Died",
  removed: "Removed",
  given_away: "Given away",
  revived: "Revived",
  watered: "Watered",
  fed: "Fed",
  pruned: "Pruned",
  pest_disease: "Pest / disease",
  treated: "Treated",
  flowered: "Flowered",
  fruited: "Fruited",
  harvested: "Harvested",
  propagated: "Propagated",
  photo: "Photo",
  note: "Note",
  assessment: "Assessment",
};

/** Event types the user can log directly (others come from actions). */
export const LOGGABLE_EVENTS = [
  "watered",
  "fed",
  "pruned",
  "pest_disease",
  "treated",
  "flowered",
  "fruited",
  "harvested",
  "note",
] as const;

export const YES_NO_MAYBE = { yes: "Yes", maybe: "Maybe", no: "No" } as const;
export const KEEP_LOCATION = { yes: "Keep it here", try_elsewhere: "Try elsewhere", no: "No" } as const;

export const END_REASONS = [
  "Frost / cold",
  "Heat / scorch",
  "Overwatering",
  "Underwatering / drought",
  "Pests",
  "Disease",
  "Too shady",
  "Too sunny",
  "Eaten by animals",
  "Outgrew space",
  "End of season",
  "Unknown",
];

export function options<T extends Record<string, string>>(map: T) {
  return Object.entries(map).map(([value, label]) => ({ value, label }));
}

export function label(map: Record<string, string>, value: string | null | undefined): string {
  if (!value) return "-";
  return map[value] ?? value;
}

export function fmtDate(value: string | null | undefined): string {
  return value ? dayjs(value).format("D MMM YYYY") : "-";
}

export function fmtDateTime(value: string | null | undefined): string {
  return value ? dayjs(value).format("D MMM YYYY, HH:mm") : "-";
}

export function fromNow(value: string | null | undefined): string {
  return value ? dayjs(value).fromNow() : "-";
}

export function instanceName(i: { plant_name?: string | null; nickname?: string | null; id: number }): string {
  return i.nickname ? `${i.nickname} (${i.plant_name ?? "plant"})` : `${i.plant_name ?? "Plant"} #${i.id}`;
}

/** Remove empty-string values so optional fields are sent as null/omitted. */
export function clean<T extends Record<string, unknown>>(values: T): T {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(values)) out[k] = v === "" ? null : v;
  return out as T;
}
