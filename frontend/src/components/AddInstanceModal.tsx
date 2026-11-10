import { Button, Group, Modal, NumberInput, Select, SimpleGrid, Stack, Textarea, TextInput } from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import { useForm } from "@mantine/form";
import dayjs from "dayjs";
import { api, S, unwrap } from "../api/client";
import { options, SOURCES } from "../lib/labels";
import { useApiMutation } from "../lib/mutations";
import { usePlantOptions } from "../lib/queries";
import { CustomFieldInputs } from "./CustomFields";
import LocationPicker from "./LocationPicker";

interface Props {
  opened: boolean;
  onClose: () => void;
  plantId?: number;
  onCreated?: (inst: S["InstanceDetail"]) => void;
}

export default function AddInstanceModal({ opened, onClose, plantId, onCreated }: Props) {
  const { data: plantOptions = [] } = usePlantOptions();
  const form = useForm({
    initialValues: {
      plant_id: plantId ? String(plantId) : (null as string | null),
      nickname: "",
      quantity: 1 as number | string,
      spot_id: null as number | null,
      position_id: null as number | null,
      occurred_at: new Date() as Date | null,
      source: "bought" as string | null,
      source_detail: "",
      cost: "" as number | string,
      notes: "",
      attributes: {} as Record<string, unknown>,
    },
    validate: { plant_id: (v: string | null) => (v ? null : "Choose a plant") },
  });

  const create = useApiMutation(
    (body: S["InstanceCreate"]) => unwrap(api.POST("/api/v1/instances", { body })),
    {
      invalidate: [["instances"], ["plants"], ["locations"], ["insights"]],
      success: "Plant added",
      onSuccess: (inst) => {
        form.reset();
        onClose();
        onCreated?.(inst);
      },
    },
  );

  const submit = form.onSubmit((v) =>
    create.mutate({
      plant_id: Number(v.plant_id),
      nickname: v.nickname || null,
      quantity: Number(v.quantity) || 1,
      spot_id: v.spot_id,
      position_id: v.position_id,
      occurred_at: v.occurred_at ? dayjs(v.occurred_at).toISOString() : null,
      acquired_date: v.occurred_at ? dayjs(v.occurred_at).format("YYYY-MM-DD") : null,
      source: (v.source as S["InstanceCreate"]["source"]) ?? null,
      source_detail: v.source_detail || null,
      cost: v.cost === "" ? null : Number(v.cost),
      event_notes: v.notes || null,
      attributes: v.attributes,
    }),
  );

  return (
    <Modal opened={opened} onClose={onClose} title="Add a plant to a location" size="lg">
      <form onSubmit={submit}>
        <Stack>
          <Select
            label="Plant"
            data={plantOptions}
            searchable
            required
            disabled={!!plantId}
            {...form.getInputProps("plant_id")}
          />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label="Nickname" placeholder="Optional" {...form.getInputProps("nickname")} />
            <NumberInput label="Quantity" min={1} {...form.getInputProps("quantity")} />
          </SimpleGrid>
          <LocationPicker
            value={{ spot_id: form.values.spot_id, position_id: form.values.position_id }}
            onChange={(v) => form.setValues(v)}
          />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <DateTimePicker label="Acquired / planted" maxDate={new Date()} {...form.getInputProps("occurred_at")} />
            <Select label="Source" data={options(SOURCES)} clearable {...form.getInputProps("source")} />
            <TextInput label="Where from" placeholder="Nursery, shop, friend…" {...form.getInputProps("source_detail")} />
            <NumberInput label="Cost" min={0} decimalScale={2} prefix="£" {...form.getInputProps("cost")} />
          </SimpleGrid>
          <Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} />
          <CustomFieldInputs entity="instance" value={form.values.attributes} onChange={(v) => form.setFieldValue("attributes", v)} />
          <Group justify="flex-end">
            <Button type="submit" loading={create.isPending}>
              Add
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
