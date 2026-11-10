import { Group, Select } from "@mantine/core";
import { useMemo } from "react";
import { label, ENVIRONMENTS } from "../lib/labels";
import { useLocationTree } from "../lib/queries";

export interface LocationValue {
  spot_id: number | null;
  position_id: number | null;
}

interface Props {
  value: LocationValue;
  onChange: (value: LocationValue) => void;
  required?: boolean;
  error?: string | null;
}

/** Pick a spot (grouped by area) and optionally a position within it. */
export default function LocationPicker({ value, onChange, required, error }: Props) {
  const { data: tree = [] } = useLocationTree();

  const spotData = useMemo(
    () =>
      tree
        .filter((a) => a.spots.length)
        .map((a) => ({
          group: `${a.name} · ${label(ENVIRONMENTS, a.environment)}`,
          items: a.spots.map((s) => ({ value: String(s.id), label: `${s.name} (${a.name})` })),
        })),
    [tree],
  );

  const spot = useMemo(
    () => tree.flatMap((a) => a.spots).find((s) => s.id === value.spot_id),
    [tree, value.spot_id],
  );

  const positionData = (spot?.positions ?? []).map((p) => {
    const taken = p.occupants.map((o) => o.nickname || o.plant_name).join(", ");
    return { value: String(p.id), label: taken ? `${p.label} - ${taken}` : `${p.label} - empty` };
  });

  return (
    <Group grow align="flex-start">
      <Select
        label="Spot"
        placeholder={tree.length ? "Choose a spot" : "Create a location first"}
        data={spotData}
        searchable
        clearable={!required}
        required={required}
        error={error}
        value={value.spot_id ? String(value.spot_id) : null}
        onChange={(v) => onChange({ spot_id: v ? Number(v) : null, position_id: null })}
        nothingFoundMessage="No spots"
      />
      <Select
        label="Position"
        placeholder={positionData.length ? "Optional" : "No positions"}
        data={positionData}
        disabled={!positionData.length}
        clearable
        value={value.position_id ? String(value.position_id) : null}
        onChange={(v) => onChange({ spot_id: value.spot_id, position_id: v ? Number(v) : null })}
      />
    </Group>
  );
}
