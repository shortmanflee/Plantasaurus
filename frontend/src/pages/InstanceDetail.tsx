import {
  ActionIcon,
  Anchor,
  Badge,
  Button,
  Card,
  Grid,
  Group,
  Image,
  Menu,
  SimpleGrid,
  Stack,
  Text,
  Timeline,
  Title,
  Tooltip,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import {
  IconArrowsMove,
  IconBucketDroplet,
  IconCamera,
  IconDots,
  IconHeartbeat,
  IconPencil,
  IconPlant,
  IconSeeding,
  IconShovel,
  IconSkull,
  IconStar,
  IconTrash,
  IconRefresh,
  IconNote,
  IconBug,
  IconScissors,
  IconFlower,
  IconApple,
  IconBasket,
  IconMapPin,
  IconFlask,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, mediaUrl, S, unwrap } from "../api/client";
import { CustomFieldValues } from "../components/CustomFields";
import { Empty, PageHeader, PlantImage, QueryState, Stars, StatusBadge } from "../components/common";
import InstanceActionModal, { ActionKind } from "../components/InstanceActions";
import { EVENT_TYPES, fmtDate, fmtDateTime, KEEP_LOCATION, label, SOURCES, YES_NO_MAYBE } from "../lib/labels";
import { useApiMutation } from "../lib/mutations";

const EVENT_ICONS: Record<string, typeof IconPlant> = {
  acquired: IconBasket,
  planted: IconShovel,
  moved: IconArrowsMove,
  transplanted: IconShovel,
  repotted: IconPlant,
  died: IconSkull,
  removed: IconTrash,
  given_away: IconHeartbeat,
  revived: IconRefresh,
  watered: IconBucketDroplet,
  fed: IconFlask,
  pruned: IconScissors,
  pest_disease: IconBug,
  treated: IconFlask,
  flowered: IconFlower,
  fruited: IconApple,
  harvested: IconBasket,
  propagated: IconSeeding,
  photo: IconCamera,
  note: IconNote,
  assessment: IconStar,
};

const EVENT_COLORS: Record<string, string> = {
  died: "red",
  removed: "gray",
  assessment: "yellow",
  watered: "blue",
  moved: "grape",
  transplanted: "grape",
  planted: "green",
  pest_disease: "orange",
};

export default function InstanceDetail() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const [action, setAction] = useState<ActionKind | null>(null);

  const { data: inst, isLoading, error } = useQuery({
    queryKey: ["instances", id],
    queryFn: () => unwrap(api.GET("/api/v1/instances/{instance_id}", { params: { path: { instance_id: id } } })),
  });
  const { data: timeline = [] } = useQuery({
    queryKey: ["timeline", id],
    queryFn: () => unwrap(api.GET("/api/v1/instances/{instance_id}/timeline", { params: { path: { instance_id: id } } })),
  });
  const { data: tree } = useQuery({
    queryKey: ["locations", "tree", "all"],
    queryFn: () => unwrap(api.GET("/api/v1/locations/tree", { params: { query: { include_archived: true } } })),
  });

  const remove = useApiMutation(
    () => unwrap(api.DELETE("/api/v1/instances/{instance_id}", { params: { path: { instance_id: id } } })),
    { invalidate: [["instances"], ["plants"], ["insights"], ["locations"]], success: "Deleted", onSuccess: () => navigate("/instances") },
  );
  const deleteEvent = useApiMutation(
    (eventId: number) => unwrap(api.DELETE("/api/v1/events/{event_id}", { params: { path: { event_id: eventId } } })),
    { invalidate: [["timeline"], ["insights"]], success: "Removed" },
  );
  const deleteAssessment = useApiMutation(
    (assessmentId: number) =>
      unwrap(api.DELETE("/api/v1/assessments/{assessment_id}", { params: { path: { assessment_id: assessmentId } } })),
    { invalidate: [["timeline"], ["insights"], ["instances"]], success: "Removed" },
  );

  if (!inst) return <QueryState isLoading={isLoading} error={error} />;

  const spots = new Map((tree ?? []).flatMap((a) => a.spots.map((s) => [s.id, `${a.name} › ${s.name}`] as const)));
  const spotName = (sid?: number | null) => (sid ? spots.get(sid) ?? `spot #${sid}` : null);
  const active = inst.status === "active";

  const btn = (kind: ActionKind, text: string, Icon: typeof IconPlant, variant = "light") => (
    <Button size="xs" variant={variant} leftSection={<Icon size={16} />} onClick={() => setAction(kind)}>
      {text}
    </Button>
  );

  return (
    <>
      <PageHeader
        title={
          <Group gap="sm">
            <span>{inst.nickname || inst.plant_name}</span>
            <StatusBadge status={inst.status} />
          </Group>
        }
        subtitle={
          <>
            <Anchor component={Link} to={`/plants/${inst.plant_id}`}>
              {inst.plant_name}
            </Anchor>{" "}
            · #{inst.id}
            {inst.quantity > 1 && ` · ×${inst.quantity}`}
          </>
        }
        actions={
          <Menu position="bottom-end">
            <Menu.Target>
              <ActionIcon variant="default" size="lg">
                <IconDots size={18} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconPencil size={16} />} onClick={() => setAction("edit")}>
                Edit details
              </Menu.Item>
              {active && (
                <Menu.Item leftSection={<IconPlant size={16} />} onClick={() => setAction("repot")}>
                  Repot
                </Menu.Item>
              )}
              {active && (
                <Menu.Item leftSection={<IconSeeding size={16} />} onClick={() => setAction("propagate")}>
                  Propagate
                </Menu.Item>
              )}
              <Menu.Divider />
              <Menu.Item
                color="red"
                leftSection={<IconTrash size={16} />}
                onClick={() =>
                  modals.openConfirmModal({
                    title: "Permanently delete?",
                    children: (
                      <Text size="sm">
                        This erases the plant and its whole history. To keep a record, use “Died / removed” instead.
                      </Text>
                    ),
                    labels: { confirm: "Delete forever", cancel: "Cancel" },
                    confirmProps: { color: "red" },
                    onConfirm: () => remove.mutate(undefined),
                  })
                }
              >
                Delete permanently
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        }
      />

      <Group gap="xs" mb="lg">
        {active ? (
          <>
            {btn("log", "Log care", IconBucketDroplet, "filled")}
            {btn("assess", "Assess", IconStar)}
            {btn("move", "Move", IconArrowsMove)}
            {btn("transplant", "Transplant", IconShovel)}
            {btn("photo", "Photo", IconCamera)}
            {btn("retire", "Died / removed", IconSkull, "outline")}
          </>
        ) : (
          <>
            {btn("revive", "Revive", IconRefresh)}
            {btn("log", "Add note", IconNote)}
            {btn("photo", "Photo", IconCamera)}
          </>
        )}
      </Group>

      <Grid>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Stack>
            <PlantImage mediaId={inst.plant_image_media_id} size="100%" height={200} />
            <Card withBorder>
              <Stack gap={6}>
                <Group gap={6}>
                  <IconMapPin size={16} />
                  {inst.current_spot_id ? (
                    <Anchor component={Link} to={`/spots/${inst.current_spot_id}`}>
                      {inst.area_name} › {inst.spot_name}
                      {inst.position_label && ` › ${inst.position_label}`}
                    </Anchor>
                  ) : (
                    <Text c="dimmed">{active ? "Not placed" : "-"}</Text>
                  )}
                </Group>
                <Info label="Acquired" value={fmtDate(inst.acquired_date)} />
                <Info label="Source" value={[label(SOURCES, inst.source), inst.source_detail].filter((x) => x && x !== "-").join(" · ") || "-"} />
                {inst.cost != null && <Info label="Cost" value={`£${inst.cost.toFixed(2)}`} />}
                {inst.parent_instance_id && (
                  <Info label="Propagated from" value={<Anchor component={Link} to={`/instances/${inst.parent_instance_id}`}>#{inst.parent_instance_id}</Anchor>} />
                )}
                {(inst.children_ids ?? []).length > 0 && (
                  <Info
                    label="Offspring"
                    value={(inst.children_ids ?? []).map((c, i) => (
                      <span key={c}>
                        {i > 0 && ", "}
                        <Anchor component={Link} to={`/instances/${c}`}>#{c}</Anchor>
                      </span>
                    ))}
                  />
                )}
                {!active && <Info label="Ended" value={`${fmtDate(inst.ended_at)}${inst.end_reason ? ` · ${inst.end_reason}` : ""}`} />}
                <Info label="Latest rating" value={<Stars value={inst.latest_overall_rating} />} />
                {inst.notes && <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{inst.notes}</Text>}
              </Stack>
            </Card>
            <CustomFieldValues entity="instance" value={inst.attributes as Record<string, unknown>} />
            <Card withBorder>
              <Title order={5} mb="xs">
                Where it has lived
              </Title>
              {inst.placements.length ? (
                <Stack gap={6}>
                  {[...inst.placements].reverse().map((p) => (
                    <div key={p.id}>
                      <Text size="sm" fw={p.ended_at ? 400 : 600}>
                        {p.spot_id ? (
                          <Anchor component={Link} to={`/spots/${p.spot_id}`} inherit>
                            {p.area_name} › {p.spot_name}
                          </Anchor>
                        ) : (
                          "Unknown spot"
                        )}
                        {p.position_label && ` › ${p.position_label}`}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {fmtDate(p.started_at)} – {p.ended_at ? fmtDate(p.ended_at) : "now"}
                      </Text>
                    </div>
                  ))}
                </Stack>
              ) : (
                <Empty>Never placed</Empty>
              )}
            </Card>
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Title order={4} mb="md">
            Timeline
          </Title>
          {timeline.length ? (
            <Timeline bulletSize={28} lineWidth={2}>
              {timeline.map((entry) => (
                <Timeline.Item
                  key={entry.event.id}
                  bullet={(() => {
                    const Icon = EVENT_ICONS[entry.event.event_type] ?? IconNote;
                    return <Icon size={14} />;
                  })()}
                  color={EVENT_COLORS[entry.event.event_type] ?? "green"}
                  title={
                    <Group justify="space-between" wrap="nowrap">
                      <Text fw={600}>{label(EVENT_TYPES, entry.event.event_type)}</Text>
                      <Group gap={4} wrap="nowrap">
                        <Text size="xs" c="dimmed">
                          {fmtDateTime(entry.event.occurred_at)}
                        </Text>
                        {(entry.assessment || !SYSTEM.has(entry.event.event_type)) && (
                          <Tooltip label="Remove">
                            <ActionIcon
                              variant="subtle"
                              color="gray"
                              size="sm"
                              onClick={() =>
                                modals.openConfirmModal({
                                  title: "Remove this entry?",
                                  labels: { confirm: "Remove", cancel: "Cancel" },
                                  confirmProps: { color: "red" },
                                  onConfirm: () =>
                                    entry.assessment ? deleteAssessment.mutate(entry.assessment.id) : deleteEvent.mutate(entry.event.id),
                                })
                              }
                            >
                              <IconTrash size={14} />
                            </ActionIcon>
                          </Tooltip>
                        )}
                      </Group>
                    </Group>
                  }
                >
                  <EventBody entry={entry} spotName={spotName} />
                </Timeline.Item>
              ))}
            </Timeline>
          ) : (
            <Empty>No history</Empty>
          )}
        </Grid.Col>
      </Grid>
      <InstanceActionModal kind={action} instance={inst} onClose={() => setAction(null)} />
    </>
  );
}

const SYSTEM = new Set([
  "acquired",
  "planted",
  "moved",
  "transplanted",
  "repotted",
  "died",
  "removed",
  "given_away",
  "revived",
  "propagated",
  "assessment",
]);

function Info({ label: l, value }: { label: string; value: ReactNode }) {
  return (
    <Group gap={6} wrap="nowrap" align="flex-start">
      <Text size="sm" c="dimmed" w={110} style={{ flexShrink: 0 }}>
        {l}
      </Text>
      <Text size="sm" component="div">
        {value}
      </Text>
    </Group>
  );
}

function EventBody({ entry, spotName }: { entry: S["TimelineEntry"]; spotName: (id?: number | null) => string | null }) {
  const e = entry.event;
  const a = entry.assessment;
  const data = e.data as Record<string, unknown>;
  const from = spotName(e.from_spot_id);
  const to = spotName(e.to_spot_id);
  const details = Object.entries(data).filter(
    ([k]) => !["final", "child_instance_id", "previous_status", "health", "vigour", "flowering_fruiting", "overall", "would_buy_again", "would_keep_location"].includes(k),
  );
  return (
    <Stack gap={4}>
      {(from || to) && (
        <Text size="sm">
          {from && to ? `${from} → ${to}` : to ? `→ ${to}` : `from ${from}`}
        </Text>
      )}
      {"child_instance_id" in data && (
        <Text size="sm">
          New plant: <Anchor component={Link} to={`/instances/${data.child_instance_id}`}>#{String(data.child_instance_id)}</Anchor>
        </Text>
      )}
      {details.length > 0 && (
        <Group gap={4}>
          {details.map(([k, v]) => (
            <Badge key={k} variant="light" color="gray" tt="none">
              {k.replace("_", " ")}: {String(v)}
            </Badge>
          ))}
        </Group>
      )}
      {a && (
        <SimpleGrid cols={2} spacing={4} maw={420}>
          {a.overall != null && <Text size="sm">Overall <Stars value={a.overall} /></Text>}
          {a.health != null && <Text size="sm">Health <Stars value={a.health} /></Text>}
          {a.vigour != null && <Text size="sm">Vigour <Stars value={a.vigour} /></Text>}
          {a.flowering_fruiting != null && <Text size="sm">Flowering <Stars value={a.flowering_fruiting} /></Text>}
          {a.would_buy_again && <Text size="sm">Buy again: <b>{label(YES_NO_MAYBE, a.would_buy_again)}</b></Text>}
          {a.would_keep_location && <Text size="sm">Location: <b>{label(KEEP_LOCATION, a.would_keep_location)}</b></Text>}
        </SimpleGrid>
      )}
      {e.notes && (
        <Text size="sm" c="dimmed" style={{ whiteSpace: "pre-wrap" }}>
          {e.notes}
        </Text>
      )}
      {(entry.media ?? []).length > 0 && (
        <Group gap="xs">
          {(entry.media ?? []).map((m) => (
            <a key={m.id} href={mediaUrl(m.id, "file")} target="_blank" rel="noreferrer">
              <Image src={mediaUrl(m.id)} w={120} h={90} radius="sm" fit="cover" alt={m.caption ?? ""} />
            </a>
          ))}
        </Group>
      )}
    </Stack>
  );
}
