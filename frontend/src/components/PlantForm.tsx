import { Button, Checkbox, Divider, Group, NumberInput, SimpleGrid, Stack, Text, Textarea, TextInput, Select } from "@mantine/core";
import { useForm } from "@mantine/form";
import type { S } from "../api/client";
import { clean } from "../lib/labels";
import { CustomFieldInputs } from "./CustomFields";

type Values = Omit<S["PlantCreate"], "attributes"> & { attributes: Record<string, unknown> };

const RANGES: [string, keyof Values, keyof Values, string][] = [
  ["Light (lux)", "min_light_lux", "max_light_lux", "lux"],
  ["Light (mmol)", "min_light_mmol", "max_light_mmol", "mmol"],
  ["Temperature", "min_temp", "max_temp", "°C"],
  ["Air humidity", "min_env_humid", "max_env_humid", "%"],
  ["Soil moisture", "min_soil_moist", "max_soil_moist", "%"],
  ["Soil EC", "min_soil_ec", "max_soil_ec", "µS/cm"],
];

interface Props {
  initial?: Partial<S["PlantRead"]>;
  submitLabel: string;
  loading?: boolean;
  onSubmit: (values: S["PlantCreate"]) => void;
}

export default function PlantForm({ initial, submitLabel, loading, onSubmit }: Props) {
  const form = useForm<Values>({
    initialValues: {
      common_name: initial?.common_name ?? "",
      scientific_name: initial?.scientific_name ?? "",
      cultivar: initial?.cultivar ?? "",
      category: initial?.category ?? "",
      description: initial?.description ?? "",
      notes: initial?.notes ?? "",
      hardiness: initial?.hardiness ?? "",
      sun_preference: initial?.sun_preference ?? null,
      water_needs: initial?.water_needs ?? null,
      is_perennial: initial?.is_perennial ?? null,
      toxic_to_pets: initial?.toxic_to_pets ?? null,
      min_light_lux: initial?.min_light_lux ?? null,
      max_light_lux: initial?.max_light_lux ?? null,
      min_light_mmol: initial?.min_light_mmol ?? null,
      max_light_mmol: initial?.max_light_mmol ?? null,
      min_temp: initial?.min_temp ?? null,
      max_temp: initial?.max_temp ?? null,
      min_env_humid: initial?.min_env_humid ?? null,
      max_env_humid: initial?.max_env_humid ?? null,
      min_soil_moist: initial?.min_soil_moist ?? null,
      max_soil_moist: initial?.max_soil_moist ?? null,
      min_soil_ec: initial?.min_soil_ec ?? null,
      max_soil_ec: initial?.max_soil_ec ?? null,
      attributes: (initial?.attributes as Record<string, unknown>) ?? {},
    },
    validate: { common_name: (v) => (v.trim() ? null : "Required") },
  });

  const num = (key: keyof Values) => ({
    value: (form.values[key] as number | null) ?? "",
    onChange: (v: string | number) => form.setFieldValue(key, (v === "" ? null : Number(v)) as never),
  });

  return (
    <form onSubmit={form.onSubmit((v) => onSubmit(clean(v) as S["PlantCreate"]))}>
      <Stack>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Common name" required {...form.getInputProps("common_name")} />
          <TextInput label="Scientific name" {...form.getInputProps("scientific_name")} />
          <TextInput label="Cultivar / variety" {...form.getInputProps("cultivar")} />
          <TextInput label="Category / family" {...form.getInputProps("category")} />
          <Select
            label="Sun preference"
            clearable
            data={[
              { value: "full_sun", label: "Full sun" },
              { value: "part_shade", label: "Part shade" },
              { value: "shade", label: "Shade" },
              { value: "bright_indirect", label: "Bright indirect" },
            ]}
            {...form.getInputProps("sun_preference")}
          />
          <Select
            label="Water needs"
            clearable
            data={[
              { value: "low", label: "Low" },
              { value: "medium", label: "Medium" },
              { value: "high", label: "High" },
            ]}
            {...form.getInputProps("water_needs")}
          />
          <TextInput label="Hardiness" placeholder="e.g. H4, -10°C, tender" {...form.getInputProps("hardiness")} />
          <Group mt="lg">
            <Checkbox label="Perennial" checked={!!form.values.is_perennial} onChange={(e) => form.setFieldValue("is_perennial", e.currentTarget.checked)} />
            <Checkbox label="Toxic to pets" checked={!!form.values.toxic_to_pets} onChange={(e) => form.setFieldValue("toxic_to_pets", e.currentTarget.checked)} />
          </Group>
        </SimpleGrid>
        <Textarea label="Description" autosize minRows={2} {...form.getInputProps("description")} />
        <Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} />
        <Divider label="Care ranges" labelPosition="left" />
        <Stack gap={6}>
          {RANGES.map(([label, min, max, unit]) => (
            <Group key={label} grow>
              <Text size="sm">{label}</Text>
              <NumberInput size="xs" placeholder={`min ${unit}`} {...num(min)} />
              <NumberInput size="xs" placeholder={`max ${unit}`} {...num(max)} />
            </Group>
          ))}
        </Stack>
        <CustomFieldInputs entity="plant" value={form.values.attributes} onChange={(v) => form.setFieldValue("attributes", v)} />
        <Group justify="flex-end">
          <Button type="submit" loading={loading}>
            {submitLabel}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
