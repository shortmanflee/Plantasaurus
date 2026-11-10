import { Checkbox, NumberInput, Select, SimpleGrid, Table, Text, TextInput } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import dayjs from "dayjs";
import type { S } from "../api/client";
import { useCustomFields } from "../lib/queries";

type Entity = "plant" | "instance" | "area" | "spot";
type Attrs = Record<string, unknown>;

export function CustomFieldInputs({ entity, value, onChange }: { entity: Entity; value: Attrs; onChange: (v: Attrs) => void }) {
  const { data: fields = [] } = useCustomFields(entity);
  if (!fields.length) return null;
  const set = (key: string, v: unknown) => onChange({ ...value, [key]: v });
  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      {fields.map((f) => (
        <FieldInput key={f.id} field={f} value={value[f.key]} onChange={(v) => set(f.key, v)} />
      ))}
    </SimpleGrid>
  );
}

function FieldInput({ field, value, onChange }: { field: S["CustomFieldRead"]; value: unknown; onChange: (v: unknown) => void }) {
  const common = { label: field.label, description: field.help_text ?? undefined };
  switch (field.type) {
    case "number":
      return (
        <NumberInput
          {...common}
          value={(value as number | undefined) ?? ""}
          onChange={(v) => onChange(v === "" ? null : v)}
        />
      );
    case "bool":
      return <Checkbox {...common} mt="lg" checked={!!value} onChange={(e) => onChange(e.currentTarget.checked)} />;
    case "date":
      return (
        <DateInput
          {...common}
          clearable
          value={value ? dayjs(value as string).toDate() : null}
          onChange={(d) => onChange(d ? dayjs(d).format("YYYY-MM-DD") : null)}
        />
      );
    case "select":
      return (
        <Select {...common} clearable data={field.options ?? []} value={(value as string) ?? null} onChange={onChange} />
      );
    default:
      return <TextInput {...common} value={(value as string) ?? ""} onChange={(e) => onChange(e.currentTarget.value)} />;
  }
}

export function CustomFieldValues({ entity, value }: { entity: Entity; value: Attrs }) {
  const { data: fields = [] } = useCustomFields(entity);
  const rows = fields.filter((f) => value[f.key] !== undefined && value[f.key] !== null);
  if (!rows.length) return null;
  return (
    <Table>
      <Table.Tbody>
        {rows.map((f) => (
          <Table.Tr key={f.id}>
            <Table.Td w="40%">
              <Text c="dimmed" size="sm">
                {f.label}
              </Text>
            </Table.Td>
            <Table.Td>{f.type === "bool" ? (value[f.key] ? "Yes" : "No") : String(value[f.key])}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
