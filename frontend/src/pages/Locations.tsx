import { ActionIcon, Anchor, Badge, Button, Card, Group, Menu, Modal, SimpleGrid, Stack, Switch, Text, TextInput, Title } from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconArchive, IconDots, IconPencil, IconPlus, IconTrash, IconArchiveOff } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, S, unwrap } from "../api/client";
import { Empty, PageHeader, QueryState } from "../components/common";
import { DeviceBadge, HAIssuesAlert } from "../components/HomeAssistant";
import { AreaForm, SpotForm, spotTraits } from "../components/LocationForms";
import { ENVIRONMENTS, label } from "../lib/labels";
import { useApiMutation } from "../lib/mutations";

const ENV_COLORS: Record<string, string> = { indoor: "orange", outdoor: "green", greenhouse: "teal", covered: "blue" };
const INVALIDATE = [["locations"], ["instances"], ["insights"], ["homeassistant"]];

type Editing =
  | { kind: "area"; area?: S["AreaRead"] }
  | { kind: "spot"; spot?: S["SpotRead"]; areaId?: number }
  | null;

export default function Locations() {
  const [editing, setEditing] = useState<Editing>(null);
  const [showArchived, setShowArchived] = useState(false);
  const { data: tree, isLoading, error } = useQuery({
    queryKey: ["locations", "tree", showArchived],
    queryFn: () => unwrap(api.GET("/api/v1/locations/tree", { params: { query: { include_archived: showArchived } } })),
  });

  const deleteArea = useApiMutation(
    (id: number) => unwrap(api.DELETE("/api/v1/areas/{area_id}", { params: { path: { area_id: id } } })),
    { invalidate: INVALIDATE, success: "Area deleted" },
  );

  if (!tree) return <QueryState isLoading={isLoading} error={error} />;
  const areas = tree as S["AreaRead"][];

  return (
    <>
      <PageHeader
        title="Locations"
        subtitle="Areas contain spots; spots can have numbered positions"
        actions={
          <>
            <Switch label="Show archived" checked={showArchived} onChange={(e) => setShowArchived(e.currentTarget.checked)} />
            <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing({ kind: "area" })}>
              Add area
            </Button>
          </>
        }
      />
      <HAIssuesAlert />
      {!tree.length && <Empty>No locations yet. Start by adding an area such as “Living Room” or “Back Garden”.</Empty>}
      <Stack gap="xl">
        {tree.map((area) => (
          <div key={area.id}>
            <Group justify="space-between" mb="xs">
              <Group gap="xs">
                <Title order={3}>{area.name}</Title>
                <Badge color={ENV_COLORS[area.environment]} variant="light">
                  {label(ENVIRONMENTS, area.environment)}
                </Badge>
                <Anchor component={Link} to={`/instances?area=${area.id}`} size="sm">
                  {area.spots.reduce((n, s) => n + s.unpositioned_occupants.length + s.positions.reduce((m, p) => m + p.occupants.length, 0), 0)} plants
                </Anchor>
              </Group>
              <Group gap="xs">
                <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditing({ kind: "spot", areaId: area.id })}>
                  Add spot
                </Button>
                <Menu position="bottom-end">
                  <Menu.Target>
                    <ActionIcon variant="subtle">
                      <IconDots size={18} />
                    </ActionIcon>
                  </Menu.Target>
                  <Menu.Dropdown>
                    <Menu.Item leftSection={<IconPencil size={16} />} onClick={() => setEditing({ kind: "area", area })}>
                      Edit area
                    </Menu.Item>
                    <Menu.Item
                      color="red"
                      leftSection={<IconTrash size={16} />}
                      onClick={() =>
                        modals.openConfirmModal({
                          title: `Delete ${area.name}?`,
                          children: <Text size="sm">Its spots and positions will be deleted too. Areas with plant history can't be deleted; archive their spots instead.</Text>,
                          labels: { confirm: "Delete", cancel: "Cancel" },
                          confirmProps: { color: "red" },
                          onConfirm: () => deleteArea.mutate(area.id),
                        })
                      }
                    >
                      Delete area
                    </Menu.Item>
                  </Menu.Dropdown>
                </Menu>
              </Group>
            </Group>
            {area.description && <Text size="sm" c="dimmed" mb="xs">{area.description}</Text>}
            {area.spots.length ? (
              <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
                {area.spots.map((spot) => (
                  <SpotCard key={spot.id} spot={spot} onEdit={() => setEditing({ kind: "spot", spot })} />
                ))}
              </SimpleGrid>
            ) : (
              <Text size="sm" c="dimmed">
                No spots yet
              </Text>
            )}
          </div>
        ))}
      </Stack>
      <Modal opened={!!editing} onClose={() => setEditing(null)} title={editing?.kind === "area" ? (editing.area ? "Edit area" : "New area") : editing?.kind === "spot" && editing.spot ? "Edit spot" : "New spot"} size="lg">
        {editing?.kind === "area" && <AreaForm area={editing.area} onDone={() => setEditing(null)} />}
        {editing?.kind === "spot" && <SpotForm spot={editing.spot} areaId={editing.areaId} areas={areas} onDone={() => setEditing(null)} />}
      </Modal>
    </>
  );
}

function SpotCard({ spot, onEdit }: { spot: S["SpotNode"]; onEdit: () => void }) {
  const [newPos, setNewPos] = useState("");
  const addPosition = useApiMutation(
    () => unwrap(api.POST("/api/v1/positions", { body: { spot_id: spot.id, label: newPos.trim() } })),
    { invalidate: INVALIDATE, onSuccess: () => setNewPos("") },
  );
  const deletePosition = useApiMutation(
    (id: number) => unwrap(api.DELETE("/api/v1/positions/{position_id}", { params: { path: { position_id: id } } })),
    { invalidate: INVALIDATE },
  );
  const archive = useApiMutation(
    (archived: boolean) => unwrap(api.PATCH("/api/v1/spots/{spot_id}", { params: { path: { spot_id: spot.id } }, body: { archived } })),
    { invalidate: INVALIDATE, success: (s) => (s.archived ? "Spot archived" : "Spot restored") },
  );
  const remove = useApiMutation(
    () => unwrap(api.DELETE("/api/v1/spots/{spot_id}", { params: { path: { spot_id: spot.id } } })),
    { invalidate: INVALIDATE, success: "Spot deleted" },
  );
  const traits = spotTraits(spot);
  const name = (o: S["OccupantSummary"]) => o.nickname || o.plant_name;

  return (
    <Card withBorder opacity={spot.archived ? 0.6 : 1}>
      <Group justify="space-between" mb={4} wrap="nowrap">
        <Anchor component={Link} to={`/spots/${spot.id}`} fw={600}>
          {spot.name}
        </Anchor>
        <Menu position="bottom-end">
          <Menu.Target>
            <ActionIcon variant="subtle" size="sm">
              <IconDots size={16} />
            </ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item leftSection={<IconPencil size={16} />} onClick={onEdit}>
              Edit
            </Menu.Item>
            <Menu.Item
              leftSection={spot.archived ? <IconArchiveOff size={16} /> : <IconArchive size={16} />}
              onClick={() => archive.mutate(!spot.archived)}
            >
              {spot.archived ? "Restore" : "Archive"}
            </Menu.Item>
            <Menu.Item
              color="red"
              leftSection={<IconTrash size={16} />}
              onClick={() =>
                modals.openConfirmModal({
                  title: `Delete ${spot.name}?`,
                  children: <Text size="sm">Spots with history can't be deleted; archive them instead.</Text>,
                  labels: { confirm: "Delete", cancel: "Cancel" },
                  confirmProps: { color: "red" },
                  onConfirm: () => remove.mutate(undefined),
                })
              }
            >
              Delete
            </Menu.Item>
          </Menu.Dropdown>
        </Menu>
      </Group>
      {traits.length > 0 && (
        <Group gap={4} mb="xs">
          {traits.map((t) => (
            <Badge key={t} size="xs" variant="outline" color="gray" tt="none">
              {t}
            </Badge>
          ))}
        </Group>
      )}
      {(spot.irrigation_zone || spot.plant_monitor) && (
        <Group gap={4} mb="xs">
          {spot.irrigation_zone && <DeviceBadge role="irrigation_zone" device={spot.irrigation_zone} />}
          {spot.plant_monitor && <DeviceBadge role="plant_monitor" device={spot.plant_monitor} />}
        </Group>
      )}
      <Stack gap={4}>
        {spot.positions.map((p) => (
          <Group key={p.id} gap="xs" wrap="nowrap">
            <Badge variant="light" w={52} style={{ flexShrink: 0 }}>
              {p.label}
            </Badge>
            {p.occupants.length ? (
              <Text size="sm" lineClamp={1}>
                {p.occupants.map((o, i) => (
                  <span key={o.instance_id}>
                    {i > 0 && ", "}
                    <Anchor component={Link} to={`/instances/${o.instance_id}`} inherit>
                      {name(o)}
                    </Anchor>
                  </span>
                ))}
              </Text>
            ) : (
              <Group gap={4} wrap="nowrap">
                <Text size="sm" c="dimmed">
                  empty
                </Text>
                <ActionIcon variant="subtle" color="gray" size="xs" onClick={() => deletePosition.mutate(p.id)} title="Remove position">
                  <IconTrash size={12} />
                </ActionIcon>
              </Group>
            )}
          </Group>
        ))}
        {spot.unpositioned_occupants.map((o) => (
          <Anchor key={o.instance_id} component={Link} to={`/instances/${o.instance_id}`} size="sm">
            {name(o)}
          </Anchor>
        ))}
        {!spot.positions.length && !spot.unpositioned_occupants.length && (
          <Text size="sm" c="dimmed">
            Empty
          </Text>
        )}
      </Stack>
      {!spot.archived && (
        <Group gap={4} mt="sm">
          <TextInput
            size="xs"
            placeholder="New position"
            value={newPos}
            onChange={(e) => setNewPos(e.currentTarget.value)}
            onKeyDown={(e) => e.key === "Enter" && newPos.trim() && addPosition.mutate(undefined)}
            style={{ flex: 1 }}
          />
          <Button size="xs" variant="light" disabled={!newPos.trim()} onClick={() => addPosition.mutate(undefined)}>
            Add
          </Button>
        </Group>
      )}
    </Card>
  );
}
