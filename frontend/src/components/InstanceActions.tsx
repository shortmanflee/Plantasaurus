import {
  Autocomplete,
  Button,
  Checkbox,
  FileInput,
  Group,
  Modal,
  NumberInput,
  Rating,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { DateInput, DateTimePicker } from "@mantine/dates";
import { useForm } from "@mantine/form";
import dayjs from "dayjs";
import { useNavigate } from "react-router-dom";
import { api, S, unwrap, uploadMedia } from "../api/client";
import {
  END_REASONS,
  EVENT_TYPES,
  KEEP_LOCATION,
  LOGGABLE_EVENTS,
  options,
  SOURCES,
  STATUSES,
  YES_NO_MAYBE,
} from "../lib/labels";
import { useApiMutation } from "../lib/mutations";
import { CustomFieldInputs } from "./CustomFields";
import LocationPicker from "./LocationPicker";

export type ActionKind =
  | "move"
  | "transplant"
  | "repot"
  | "log"
  | "assess"
  | "retire"
  | "revive"
  | "propagate"
  | "photo"
  | "edit";

const TITLES: Record<ActionKind, string> = {
  move: "Move",
  transplant: "Transplant",
  repot: "Repot",
  log: "Log care / observation",
  assess: "How is it doing?",
  retire: "Record death or removal",
  revive: "Revive",
  propagate: "Propagate",
  photo: "Add photo",
  edit: "Edit details",
};

interface Props {
  kind: ActionKind | null;
  instance: S["InstanceDetail"];
  onClose: () => void;
}

const INVALIDATE = [["instances"], ["plants"], ["locations"], ["insights"], ["timeline"]];
const iso = (d: Date | null) => (d ? dayjs(d).toISOString() : null);
const path = (id: number) => ({ params: { path: { instance_id: id } } });

export default function InstanceActionModal({ kind, instance, onClose }: Props) {
  return (
    <Modal opened={!!kind} onClose={onClose} title={kind ? TITLES[kind] : ""} size="lg">
      {kind === "move" && <MoveForm instance={instance} onDone={onClose} />}
      {kind === "transplant" && <MoveForm instance={instance} onDone={onClose} transplant />}
      {kind === "repot" && <RepotForm instance={instance} onDone={onClose} />}
      {kind === "log" && <LogForm instance={instance} onDone={onClose} />}
      {kind === "assess" && <AssessForm instance={instance} onDone={onClose} />}
      {kind === "retire" && <RetireForm instance={instance} onDone={onClose} />}
      {kind === "revive" && <ReviveForm instance={instance} onDone={onClose} />}
      {kind === "propagate" && <PropagateForm instance={instance} onDone={onClose} />}
      {kind === "photo" && <PhotoForm instance={instance} onDone={onClose} />}
      {kind === "edit" && <EditForm instance={instance} onDone={onClose} />}
    </Modal>
  );
}

interface FormProps {
  instance: S["InstanceDetail"];
  onDone: () => void;
}

function When({ value, onChange, label = "When" }: { value: Date | null; onChange: (d: Date | null) => void; label?: string }) {
  return <DateTimePicker label={label} maxDate={new Date()} value={value} onChange={(d) => onChange(d as Date | null)} />;
}

function Submit({ loading, label = "Save", color }: { loading: boolean; label?: string; color?: string }) {
  return (
    <Group justify="flex-end">
      <Button type="submit" loading={loading} color={color}>
        {label}
      </Button>
    </Group>
  );
}

function MoveForm({ instance, onDone, transplant }: FormProps & { transplant?: boolean }) {
  const form = useForm({
    initialValues: {
      spot_id: null as number | null,
      position_id: null as number | null,
      occurred_at: new Date() as Date | null,
      notes: "",
      pot_size: "",
      soil: "",
    },
    validate: { spot_id: (v: number | null) => (v ? null : "Choose where it's going") },
  });
  const m = useApiMutation(
    (v: typeof form.values) => {
      const base = { spot_id: v.spot_id, position_id: v.position_id, occurred_at: iso(v.occurred_at), notes: v.notes || null };
      return transplant
        ? unwrap(api.POST("/api/v1/instances/{instance_id}/transplant", { ...path(instance.id), body: { ...base, pot_size: v.pot_size || null, soil: v.soil || null } }))
        : unwrap(api.POST("/api/v1/instances/{instance_id}/move", { ...path(instance.id), body: base }));
    },
    { invalidate: INVALIDATE, success: transplant ? "Transplanted" : "Moved", onSuccess: onDone },
  );
  return (
    <form onSubmit={form.onSubmit((v) => m.mutate(v))}>
      <Stack>
        <Text size="sm" c="dimmed">
          Currently: {instance.spot_name ? `${instance.area_name} › ${instance.spot_name}${instance.position_label ? ` › ${instance.position_label}` : ""}` : "not placed"}
        </Text>
        <LocationPicker
          required
          error={form.errors.spot_id as string | undefined}
          value={{ spot_id: form.values.spot_id, position_id: form.values.position_id }}
          onChange={(v) => form.setValues(v)}
        />
        {transplant && (
          <SimpleGrid cols={2}>
            <TextInput label="Pot size" placeholder="e.g. 20cm, in ground" {...form.getInputProps("pot_size")} />
            <TextInput label="Soil / compost" {...form.getInputProps("soil")} />
          </SimpleGrid>
        )}
        <When value={form.values.occurred_at} onChange={(d) => form.setFieldValue("occurred_at", d)} />
        <Textarea label="Notes" placeholder="Why are you moving it?" autosize {...form.getInputProps("notes")} />
        <Submit loading={m.isPending} label={transplant ? "Transplant" : "Move"} />
      </Stack>
    </form>
  );
}

function RepotForm({ instance, onDone }: FormProps) {
  const form = useForm({ initialValues: { occurred_at: new Date() as Date | null, pot_size: "", soil: "", notes: "" } });
  const m = useApiMutation(
    (v: typeof form.values) =>
      unwrap(
        api.POST("/api/v1/instances/{instance_id}/repot", {
          ...path(instance.id),
          body: { occurred_at: iso(v.occurred_at), pot_size: v.pot_size || null, soil: v.soil || null, notes: v.notes || null },
        }),
      ),
    { invalidate: INVALIDATE, success: "Repotted", onSuccess: onDone },
  );
  return (
    <form onSubmit={form.onSubmit((v) => m.mutate(v))}>
      <Stack>
        <SimpleGrid cols={2}>
          <TextInput label="New pot size" {...form.getInputProps("pot_size")} />
          <TextInput label="Soil / compost" {...form.getInputProps("soil")} />
        </SimpleGrid>
        <When value={form.values.occurred_at} onChange={(d) => form.setFieldValue("occurred_at", d)} />
        <Textarea label="Notes" autosize {...form.getInputProps("notes")} />
        <Submit loading={m.isPending} />
      </Stack>
    </form>
  );
}

function LogForm({ instance, onDone }: FormProps) {
  const form = useForm({
    initialValues: {
      event_type: "watered" as string,
      occurred_at: new Date() as Date | null,
      notes: "",
      product: "",
      amount: "",
      photo: null as File | null,
    },
  });
  const m = useApiMutation(
    async (v: typeof form.values) => {
      const data: Record<string, string> = {};
      if (v.product) data.product = v.product;
      if (v.amount) data.amount = v.amount;
      const event = await unwrap(
        api.POST("/api/v1/events", {
          body: {
            instance_id: instance.id,
            event_type: v.event_type as S["EventCreate"]["event_type"],
            occurred_at: iso(v.occurred_at),
            notes: v.notes || null,
            data,
          },
        }),
      );
      if (v.photo) await uploadMedia(v.photo, { instanceId: instance.id, eventId: event.id, takenAt: iso(v.occurred_at) ?? undefined });
      return event;
    },
    { invalidate: INVALIDATE, success: (e) => `${EVENT_TYPES[e.event_type]} logged`, onSuccess: onDone },
  );
  const showProduct = ["fed", "treated", "pest_disease"].includes(form.values.event_type);
  return (
    <form onSubmit={form.onSubmit((v) => m.mutate(v))}>
      <Stack>
        <SegmentedControl
          data={LOGGABLE_EVENTS.map((t) => ({ value: t, label: EVENT_TYPES[t] }))}
          {...form.getInputProps("event_type")}
          style={{ flexWrap: "wrap" }}
        />
        {showProduct && (
          <SimpleGrid cols={2}>
            <TextInput
              label={form.values.event_type === "pest_disease" ? "Pest / disease" : "Product"}
              {...form.getInputProps("product")}
            />
            <TextInput label={form.values.event_type === "pest_disease" ? "Severity" : "Amount"} {...form.getInputProps("amount")} />
          </SimpleGrid>
        )}
        {form.values.event_type === "harvested" && <TextInput label="Amount harvested" {...form.getInputProps("amount")} />}
        <When value={form.values.occurred_at} onChange={(d) => form.setFieldValue("occurred_at", d)} />
        <Textarea label="Notes" autosize {...form.getInputProps("notes")} />
        <FileInput label="Photo (optional)" accept="image/*" clearable {...form.getInputProps("photo")} />
        <Submit loading={m.isPending} label="Log" />
      </Stack>
    </form>
  );
}

type AssessValues = {
  health: number;
  vigour: number;
  flowering_fruiting: number;
  overall: number;
  would_buy_again: string | null;
  would_keep_location: string | null;
  notes: string;
};

const blankAssessment = (): AssessValues => ({
  health: 0,
  vigour: 0,
  flowering_fruiting: 0,
  overall: 0,
  would_buy_again: null,
  would_keep_location: null,
  notes: "",
});

function toAssessment(v: AssessValues): S["AssessmentInput"] {
  const r = (n: number) => (n > 0 ? n : null);
  return {
    health: r(v.health),
    vigour: r(v.vigour),
    flowering_fruiting: r(v.flowering_fruiting),
    overall: r(v.overall),
    would_buy_again: (v.would_buy_again as S["AssessmentInput"]["would_buy_again"]) ?? null,
    would_keep_location: (v.would_keep_location as S["AssessmentInput"]["would_keep_location"]) ?? null,
    notes: v.notes || null,
  };
}

function AssessmentFields({ value, onChange }: { value: AssessValues; onChange: (v: AssessValues) => void }) {
  const set = <K extends keyof AssessValues>(k: K, v: AssessValues[K]) => onChange({ ...value, [k]: v });
  const rating = (k: "health" | "vigour" | "flowering_fruiting" | "overall", lbl: string) => (
    <Group justify="space-between">
      <Text size="sm">{lbl}</Text>
      <Rating value={value[k]} onChange={(n) => set(k, n)} />
    </Group>
  );
  return (
    <Stack gap="xs">
      {rating("overall", "Overall")}
      {rating("health", "Health")}
      {rating("vigour", "Growth / vigour")}
      {rating("flowering_fruiting", "Flowering / fruiting")}
      <Text size="sm" mt="xs">
        Would you buy this plant again?
      </Text>
      <SegmentedControl
        data={options(YES_NO_MAYBE)}
        value={value.would_buy_again ?? ""}
        onChange={(v) => set("would_buy_again", v)}
      />
      <Text size="sm">Is this a good location for it?</Text>
      <SegmentedControl
        data={options(KEEP_LOCATION)}
        value={value.would_keep_location ?? ""}
        onChange={(v) => set("would_keep_location", v)}
      />
      <Textarea label="Notes" autosize value={value.notes} onChange={(e) => set("notes", e.currentTarget.value)} />
    </Stack>
  );
}

function AssessForm({ instance, onDone }: FormProps) {
  const form = useForm({ initialValues: { a: blankAssessment(), assessed_at: new Date() as Date | null } });
  const m = useApiMutation(
    (v: typeof form.values) =>
      unwrap(
        api.POST("/api/v1/instances/{instance_id}/assess", {
          ...path(instance.id),
          body: { ...toAssessment(v.a), assessed_at: iso(v.assessed_at) },
        }),
      ),
    { invalidate: INVALIDATE, success: "Assessment saved", onSuccess: onDone },
  );
  return (
    <form onSubmit={form.onSubmit((v) => m.mutate(v))}>
      <Stack>
        <AssessmentFields value={form.values.a} onChange={(a) => form.setFieldValue("a", a)} />
        <When value={form.values.assessed_at} onChange={(d) => form.setFieldValue("assessed_at", d)} />
        <Submit loading={m.isPending} />
      </Stack>
    </form>
  );
}

function RetireForm({ instance, onDone }: FormProps) {
  const form = useForm({
    initialValues: {
      status: "dead",
      reason: "",
      occurred_at: new Date() as Date | null,
      notes: "",
      withAssessment: true,
      a: blankAssessment(),
    },
  });
  const m = useApiMutation(
    (v: typeof form.values) =>
      unwrap(
        api.POST("/api/v1/instances/{instance_id}/retire", {
          ...path(instance.id),
          body: {
            status: v.status as S["RetireRequest"]["status"],
            reason: v.reason || null,
            occurred_at: iso(v.occurred_at),
            notes: v.notes || null,
            final_assessment: v.withAssessment ? toAssessment(v.a) : null,
          },
        }),
      ),
    { invalidate: INVALIDATE, success: "Recorded", onSuccess: onDone },
  );
  return (
    <form onSubmit={form.onSubmit((v) => m.mutate(v))}>
      <Stack>
        <SegmentedControl
          data={options({ dead: STATUSES.dead, removed: STATUSES.removed, given_away: STATUSES.given_away })}
          {...form.getInputProps("status")}
        />
        <Autocomplete label="Reason" data={END_REASONS} placeholder="What happened?" {...form.getInputProps("reason")} />
        <When value={form.values.occurred_at} onChange={(d) => form.setFieldValue("occurred_at", d)} />
        <Textarea label="Notes" autosize {...form.getInputProps("notes")} />
        <Checkbox label="Add a final assessment" {...form.getInputProps("withAssessment", { type: "checkbox" })} />
        {form.values.withAssessment && <AssessmentFields value={form.values.a} onChange={(a) => form.setFieldValue("a", a)} />}
        <Submit loading={m.isPending} label="Record" color="red" />
      </Stack>
    </form>
  );
}

function ReviveForm({ instance, onDone }: FormProps) {
  const form = useForm({
    initialValues: { spot_id: null as number | null, position_id: null as number | null, occurred_at: new Date() as Date | null, notes: "" },
  });
  const m = useApiMutation(
    (v: typeof form.values) =>
      unwrap(
        api.POST("/api/v1/instances/{instance_id}/revive", {
          ...path(instance.id),
          body: { spot_id: v.spot_id, position_id: v.position_id, occurred_at: iso(v.occurred_at), notes: v.notes || null },
        }),
      ),
    { invalidate: INVALIDATE, success: "Revived", onSuccess: onDone },
  );
  return (
    <form onSubmit={form.onSubmit((v) => m.mutate(v))}>
      <Stack>
        <Text size="sm" c="dimmed">
          Use this if it was recorded by mistake or has come back to life.
        </Text>
        <LocationPicker value={{ spot_id: form.values.spot_id, position_id: form.values.position_id }} onChange={(v) => form.setValues(v)} />
        <When value={form.values.occurred_at} onChange={(d) => form.setFieldValue("occurred_at", d)} />
        <Textarea label="Notes" autosize {...form.getInputProps("notes")} />
        <Submit loading={m.isPending} label="Revive" />
      </Stack>
    </form>
  );
}

function PropagateForm({ instance, onDone }: FormProps) {
  const navigate = useNavigate();
  const form = useForm({
    initialValues: {
      method: "cutting",
      quantity: 1 as number | string,
      nickname: "",
      spot_id: null as number | null,
      position_id: null as number | null,
      occurred_at: new Date() as Date | null,
      notes: "",
    },
  });
  const m = useApiMutation(
    (v: typeof form.values) =>
      unwrap(
        api.POST("/api/v1/instances/{instance_id}/propagate", {
          ...path(instance.id),
          body: {
            method: v.method as S["PropagateRequest"]["method"],
            quantity: Number(v.quantity) || 1,
            nickname: v.nickname || null,
            spot_id: v.spot_id,
            position_id: v.position_id,
            occurred_at: iso(v.occurred_at),
            notes: v.notes || null,
          },
        }),
      ),
    {
      invalidate: INVALIDATE,
      success: "New plant created",
      onSuccess: (child) => {
        onDone();
        navigate(`/instances/${child.id}`);
      },
    },
  );
  return (
    <form onSubmit={form.onSubmit((v) => m.mutate(v))}>
      <Stack>
        <SegmentedControl
          data={options({ cutting: SOURCES.cutting, division: SOURCES.division, seed: "Seed" })}
          {...form.getInputProps("method")}
        />
        <SimpleGrid cols={2}>
          <TextInput label="Nickname" {...form.getInputProps("nickname")} />
          <NumberInput label="How many" min={1} {...form.getInputProps("quantity")} />
        </SimpleGrid>
        <LocationPicker value={{ spot_id: form.values.spot_id, position_id: form.values.position_id }} onChange={(v) => form.setValues(v)} />
        <When value={form.values.occurred_at} onChange={(d) => form.setFieldValue("occurred_at", d)} />
        <Textarea label="Notes" autosize {...form.getInputProps("notes")} />
        <Submit loading={m.isPending} label="Create" />
      </Stack>
    </form>
  );
}

function PhotoForm({ instance, onDone }: FormProps) {
  const form = useForm({
    initialValues: { file: null as File | null, caption: "", taken_at: new Date() as Date | null },
    validate: { file: (f: File | null) => (f ? null : "Choose a photo") },
  });
  const m = useApiMutation(
    (v: typeof form.values) =>
      uploadMedia(v.file!, { instanceId: instance.id, caption: v.caption || undefined, takenAt: iso(v.taken_at) ?? undefined, logPhotoEvent: true }),
    { invalidate: INVALIDATE, success: "Photo added", onSuccess: onDone },
  );
  return (
    <form onSubmit={form.onSubmit((v) => m.mutate(v))}>
      <Stack>
        <FileInput label="Photo" accept="image/*" required {...form.getInputProps("file")} />
        <TextInput label="Caption" {...form.getInputProps("caption")} />
        <When label="Taken" value={form.values.taken_at} onChange={(d) => form.setFieldValue("taken_at", d)} />
        <Submit loading={m.isPending} label="Upload" />
      </Stack>
    </form>
  );
}

function EditForm({ instance, onDone }: FormProps) {
  const form = useForm({
    initialValues: {
      nickname: instance.nickname ?? "",
      quantity: instance.quantity as number | string,
      acquired_date: instance.acquired_date ? dayjs(instance.acquired_date).toDate() : (null as Date | null),
      source: (instance.source ?? null) as string | null,
      source_detail: instance.source_detail ?? "",
      cost: (instance.cost ?? "") as number | string,
      notes: instance.notes ?? "",
      end_reason: instance.end_reason ?? "",
      attributes: (instance.attributes ?? {}) as Record<string, unknown>,
    },
  });
  const m = useApiMutation(
    (v: typeof form.values) =>
      unwrap(
        api.PATCH("/api/v1/instances/{instance_id}", {
          ...path(instance.id),
          body: {
            nickname: v.nickname || null,
            quantity: Number(v.quantity) || 1,
            acquired_date: v.acquired_date ? dayjs(v.acquired_date).format("YYYY-MM-DD") : null,
            source: (v.source as S["InstanceUpdate"]["source"]) ?? null,
            source_detail: v.source_detail || null,
            cost: v.cost === "" ? null : Number(v.cost),
            notes: v.notes || null,
            ...(instance.status !== "active" ? { end_reason: v.end_reason || null } : {}),
            attributes: v.attributes,
          },
        }),
      ),
    { invalidate: INVALIDATE, success: "Saved", onSuccess: onDone },
  );
  return (
    <form onSubmit={form.onSubmit((v) => m.mutate(v))}>
      <Stack>
        <SimpleGrid cols={2}>
          <TextInput label="Nickname" {...form.getInputProps("nickname")} />
          <NumberInput label="Quantity" min={1} {...form.getInputProps("quantity")} />
          <DateInput label="Acquired" clearable maxDate={new Date()} {...form.getInputProps("acquired_date")} />
          <Select label="Source" data={options(SOURCES)} clearable {...form.getInputProps("source")} />
          <TextInput label="Where from" {...form.getInputProps("source_detail")} />
          <NumberInput label="Cost" min={0} decimalScale={2} prefix="£" {...form.getInputProps("cost")} />
        </SimpleGrid>
        {instance.status !== "active" && <Autocomplete label="End reason" data={END_REASONS} {...form.getInputProps("end_reason")} />}
        <Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} />
        <CustomFieldInputs entity="instance" value={form.values.attributes} onChange={(v) => form.setFieldValue("attributes", v)} />
        <Submit loading={m.isPending} />
      </Stack>
    </form>
  );
}
