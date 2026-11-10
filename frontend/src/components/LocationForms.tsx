import { Button, Group, NumberInput, Select, SimpleGrid, Stack, Textarea, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api, S, unwrap } from "../api/client";
import { ASPECTS, ENVIRONMENTS, LEVELS, options, SPOT_TYPES, SUN_EXPOSURES } from "../lib/labels";
import { useApiMutation } from "../lib/mutations";
import { useHAStatus } from "../lib/queries";
import { CustomFieldInputs } from "./CustomFields";
import { DevicePicker } from "./HomeAssistant";

const INVALIDATE = [["locations"], ["instances"], ["insights"], ["spots"], ["homeassistant"]];

export function AreaForm({ area, onDone }: { area?: S["AreaRead"]; onDone: () => void }) {
  const form = useForm({
    initialValues: {
      name: area?.name ?? "",
      environment: area?.environment ?? "indoor",
      description: area?.description ?? "",
      sort_order: area?.sort_order ?? 0,
      attributes: (area?.attributes ?? {}) as Record<string, unknown>,
    },
    validate: { name: (v: string) => (v.trim() ? null : "Required") },
  });
  const save = useApiMutation(
    (v: typeof form.values) => {
      const body = { ...v, description: v.description || null, environment: v.environment as S["AreaCreate"]["environment"] };
      return area
        ? unwrap(api.PATCH("/api/v1/areas/{area_id}", { params: { path: { area_id: area.id } }, body }))
        : unwrap(api.POST("/api/v1/areas", { body }));
    },
    { invalidate: INVALIDATE, success: "Saved", onSuccess: onDone },
  );
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        <TextInput label="Name" placeholder="e.g. Back Garden, Living Room" required data-autofocus {...form.getInputProps("name")} />
        <Select label="Environment" data={options(ENVIRONMENTS)} allowDeselect={false} {...form.getInputProps("environment")} />
        <Textarea label="Description" autosize {...form.getInputProps("description")} />
        <NumberInput label="Sort order" {...form.getInputProps("sort_order")} />
        <CustomFieldInputs entity="area" value={form.values.attributes} onChange={(v) => form.setFieldValue("attributes", v)} />
        <Group justify="flex-end">
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

const tri = (v: boolean | null | undefined) => (v == null ? null : v ? "yes" : "no");
const fromTri = (v: string | null) => (v == null ? null : v === "yes");
const TRI = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];

export function SpotForm({
  spot,
  areaId,
  areas,
  onDone,
}: {
  spot?: S["SpotRead"];
  areaId?: number;
  areas: S["AreaRead"][];
  onDone: () => void;
}) {
  const form = useForm({
    initialValues: {
      area_id: String(spot?.area_id ?? areaId ?? ""),
      name: spot?.name ?? "",
      spot_type: spot?.spot_type ?? null,
      aspect: spot?.aspect ?? null,
      sun_exposure: spot?.sun_exposure ?? null,
      near_window: tri(spot?.near_window),
      near_heat_source: tri(spot?.near_heat_source),
      near_draught: tri(spot?.near_draught),
      humidity_level: spot?.humidity_level ?? null,
      is_container: tri(spot?.is_container),
      container_size: spot?.container_size ?? "",
      soil_type: spot?.soil_type ?? "",
      notes: spot?.notes ?? "",
      sort_order: spot?.sort_order ?? 0,
      position_count: 0 as number | string,
      irrigation_zone_device_id: spot?.irrigation_zone_device_id ?? null,
      plant_monitor_device_id: spot?.plant_monitor_device_id ?? null,
      attributes: (spot?.attributes ?? {}) as Record<string, unknown>,
    },
    validate: { name: (v: string) => (v.trim() ? null : "Required"), area_id: (v: string) => (v ? null : "Required") },
  });
  const area = areas.find((a) => String(a.id) === form.values.area_id);
  const indoor = area?.environment === "indoor";
  const { data: ha } = useHAStatus();
  // Irrigation is for outdoor-ish spots, but keep showing it if one is already assigned.
  const showZone = !!ha?.configured && (!indoor || !!form.values.irrigation_zone_device_id);

  const save = useApiMutation(
    (v: typeof form.values) => {
      const body = {
        area_id: Number(v.area_id),
        name: v.name.trim(),
        spot_type: v.spot_type,
        aspect: v.aspect as S["SpotCreate"]["aspect"],
        sun_exposure: v.sun_exposure as S["SpotCreate"]["sun_exposure"],
        near_window: fromTri(v.near_window),
        near_heat_source: fromTri(v.near_heat_source),
        near_draught: fromTri(v.near_draught),
        humidity_level: v.humidity_level as S["SpotCreate"]["humidity_level"],
        is_container: fromTri(v.is_container),
        container_size: v.container_size || null,
        soil_type: v.soil_type || null,
        notes: v.notes || null,
        sort_order: Number(v.sort_order) || 0,
        attributes: v.attributes,
        ...(ha?.configured || spot?.irrigation_zone_device_id || spot?.plant_monitor_device_id
          ? { irrigation_zone_device_id: v.irrigation_zone_device_id, plant_monitor_device_id: v.plant_monitor_device_id }
          : {}),
      };
      return spot
        ? unwrap(api.PATCH("/api/v1/spots/{spot_id}", { params: { path: { spot_id: spot.id } }, body }))
        : unwrap(api.POST("/api/v1/spots", { body: { ...body, position_count: Number(v.position_count) || 0 } }));
    },
    { invalidate: INVALIDATE, success: "Saved", onSuccess: onDone },
  );

  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        <SimpleGrid cols={2}>
          <Select label="Area" data={areas.map((a) => ({ value: String(a.id), label: a.name }))} required allowDeselect={false} {...form.getInputProps("area_id")} />
          <TextInput label="Name" placeholder="e.g. Windowsill, Flowerbed, Hanging Basket 1" required data-autofocus {...form.getInputProps("name")} />
          <Select label="Type" data={options(SPOT_TYPES)} clearable searchable {...form.getInputProps("spot_type")} />
          <Select label="Facing (aspect)" data={options(ASPECTS)} clearable {...form.getInputProps("aspect")} />
          <Select label="Sun exposure" data={options(SUN_EXPOSURES)} clearable {...form.getInputProps("sun_exposure")} />
          <Select label="In a container?" data={TRI} clearable {...form.getInputProps("is_container")} />
          {form.values.is_container === "yes" && <TextInput label="Container size" {...form.getInputProps("container_size")} />}
          <TextInput label="Soil / compost" placeholder="e.g. clay, loam, peat-free" {...form.getInputProps("soil_type")} />
          {indoor && (
            <>
              <Select label="Near a window?" data={TRI} clearable {...form.getInputProps("near_window")} />
              <Select label="Near a heat source?" data={TRI} clearable {...form.getInputProps("near_heat_source")} />
              <Select label="Draughty?" data={TRI} clearable {...form.getInputProps("near_draught")} />
              <Select label="Humidity" data={options(LEVELS)} clearable {...form.getInputProps("humidity_level")} />
            </>
          )}
          {!spot && (
            <NumberInput
              label="Number of positions"
              description="Creates positions 1…N (optional)"
              min={0}
              max={200}
              {...form.getInputProps("position_count")}
            />
          )}
          <NumberInput label="Sort order" {...form.getInputProps("sort_order")} />
        </SimpleGrid>
        {ha?.configured && (
          <SimpleGrid cols={2}>
            {showZone && (
              <DevicePicker
                role="irrigation_zone"
                value={form.values.irrigation_zone_device_id}
                onChange={(v) => form.setFieldValue("irrigation_zone_device_id", v)}
                current={spot?.irrigation_zone}
                spotId={spot?.id}
              />
            )}
            <DevicePicker
              role="plant_monitor"
              value={form.values.plant_monitor_device_id}
              onChange={(v) => form.setFieldValue("plant_monitor_device_id", v)}
              current={spot?.plant_monitor}
              spotId={spot?.id}
            />
          </SimpleGrid>
        )}
        <Textarea label="Notes" autosize {...form.getInputProps("notes")} />
        <CustomFieldInputs entity="spot" value={form.values.attributes} onChange={(v) => form.setFieldValue("attributes", v)} />
        <Group justify="flex-end">
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

export function spotTraits(spot: S["SpotRead"]): string[] {
  const items: string[] = [];
  if (spot.spot_type) items.push(SPOT_TYPES[spot.spot_type as keyof typeof SPOT_TYPES] ?? spot.spot_type);
  if (spot.aspect && spot.aspect !== "none") items.push(`${ASPECTS[spot.aspect]}-facing`);
  if (spot.sun_exposure) items.push(SUN_EXPOSURES[spot.sun_exposure]);
  if (spot.near_window) items.push("Near window");
  if (spot.near_heat_source) items.push("Near heat");
  if (spot.near_draught) items.push("Draughty");
  if (spot.humidity_level) items.push(`${LEVELS[spot.humidity_level]} humidity`);
  if (spot.is_container) items.push(spot.container_size ? `Container (${spot.container_size})` : "Container");
  if (spot.soil_type) items.push(spot.soil_type);
  return items;
}

