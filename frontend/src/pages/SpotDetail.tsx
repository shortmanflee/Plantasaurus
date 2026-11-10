import { Alert, Anchor, Badge, Button, Card, Group, Modal, SimpleGrid, Stack, Table, Text } from "@mantine/core";
import { IconAlertTriangle, IconPencil } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, S, unwrap } from "../api/client";
import { CustomFieldValues } from "../components/CustomFields";
import { Empty, PageHeader, QueryState, Stars } from "../components/common";
import { DeviceBadge, INVALIDATE_HA, problemText, ROLE_LABELS } from "../components/HomeAssistant";
import { SpotForm, spotTraits } from "../components/LocationForms";
import { useApiMutation } from "../lib/mutations";
import type { HARole } from "../lib/queries";
import { ENVIRONMENTS, EVENT_TYPES, fmtDate, label } from "../lib/labels";

export default function SpotDetail() {
  const id = Number(useParams().id);
  const [editing, setEditing] = useState(false);
  const { data: spot, isLoading, error } = useQuery({
    queryKey: ["spots", id],
    queryFn: () => unwrap(api.GET("/api/v1/spots/{spot_id}", { params: { path: { spot_id: id } } })),
  });
  const { data: areas = [] } = useQuery({ queryKey: ["locations", "areas"], queryFn: () => unwrap(api.GET("/api/v1/areas")) });
  const { data: insights } = useQuery({
    queryKey: ["insights", "spot", id],
    queryFn: () => unwrap(api.GET("/api/v1/spots/{spot_id}/insights", { params: { path: { spot_id: id } } })),
  });

  if (!spot) return <QueryState isLoading={isLoading} error={error} />;
  const area = areas.find((a) => a.id === spot.area_id);

  return (
    <>
      <PageHeader
        title={spot.name}
        subtitle={
          <>
            {area?.name} · {label(ENVIRONMENTS, area?.environment)}
            {spot.archived && " · archived"}
          </>
        }
        actions={
          <Button variant="default" leftSection={<IconPencil size={16} />} onClick={() => setEditing(true)}>
            Edit
          </Button>
        }
      />
      <Group gap={4} mb="md">
        {spotTraits(spot).map((t) => (
          <Badge key={t} variant="outline" color="gray" tt="none">
            {t}
          </Badge>
        ))}
      </Group>
      <SpotDevices spot={spot} onEdit={() => setEditing(true)} />
      {spot.notes && <Text mb="md" style={{ whiteSpace: "pre-wrap" }}>{spot.notes}</Text>}
      <CustomFieldValues entity="spot" value={spot.attributes as Record<string, unknown>} />
      {insights && (
        <Stack>
          <SimpleGrid cols={{ base: 2, sm: 4 }}>
            <Card withBorder>
              <Text size="xs" c="dimmed">Here now</Text>
              <Text fw={700}>{insights.current_count}</Text>
            </Card>
            <Card withBorder>
              <Text size="xs" c="dimmed">Previously here</Text>
              <Text fw={700}>{insights.historic_count}</Text>
            </Card>
            <Card withBorder>
              <Text size="xs" c="dimmed">Died here</Text>
              <Text fw={700}>{insights.deaths}</Text>
            </Card>
            <Card withBorder>
              <Text size="xs" c="dimmed">Avg. rating here</Text>
              <Stars value={insights.avg_overall} />
            </Card>
          </SimpleGrid>
          {insights.history.length ? (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Plant</Table.Th>
                  <Table.Th>Position</Table.Th>
                  <Table.Th>From</Table.Th>
                  <Table.Th>To</Table.Th>
                  <Table.Th>Days</Table.Th>
                  <Table.Th>Rating</Table.Th>
                  <Table.Th>Outcome</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {insights.history.map((h) => (
                  <Table.Tr key={h.placement_id}>
                    <Table.Td>
                      <Anchor component={Link} to={`/instances/${h.instance_id}`}>
                        {h.nickname || h.plant_name}
                      </Anchor>
                    </Table.Td>
                    <Table.Td>{h.position_label ?? "-"}</Table.Td>
                    <Table.Td>{fmtDate(h.started_at as string)}</Table.Td>
                    <Table.Td>{h.ended_at ? fmtDate(h.ended_at as string) : "now"}</Table.Td>
                    <Table.Td>{Math.round(h.days)}</Table.Td>
                    <Table.Td>
                      <Stars value={h.avg_overall} />
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="light" color={h.outcome === "died" ? "red" : h.outcome === "current" ? "green" : "gray"}>
                        {h.outcome === "current" ? "Here now" : label(EVENT_TYPES, h.outcome)}
                      </Badge>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          ) : (
            <Empty>Nothing has been planted here yet.</Empty>
          )}
        </Stack>
      )}
      <Modal opened={editing} onClose={() => setEditing(false)} title="Edit spot" size="lg">
        <SpotForm spot={spot} areas={areas} onDone={() => setEditing(false)} />
      </Modal>
    </>
  );
}

function SpotDevices({ spot, onEdit }: { spot: S["SpotRead"]; onEdit: () => void }) {
  const unassign = useApiMutation(
    (role: HARole) =>
      unwrap(
        api.PATCH("/api/v1/spots/{spot_id}", {
          params: { path: { spot_id: spot.id } },
          body: role === "irrigation_zone" ? { irrigation_zone_device_id: null } : { plant_monitor_device_id: null },
        }),
      ),
    { invalidate: INVALIDATE_HA, success: "Device unassigned" },
  );
  const devices = (
    [
      ["irrigation_zone", spot.irrigation_zone],
      ["plant_monitor", spot.plant_monitor],
    ] as const
  ).filter((d): d is readonly [HARole, S["HADeviceRef"]] => !!d[1]);
  if (!devices.length) return null;
  return (
    <Stack gap="xs" mb="md">
      <Group gap="xs">
        {devices.map(([role, device]) => (
          <DeviceBadge key={role} role={role} device={device} />
        ))}
      </Group>
      {devices
        .filter(([, device]) => device.problem)
        .map(([role, device]) => (
          <Alert key={role} color="orange" icon={<IconAlertTriangle />} title={`${ROLE_LABELS[role]} needs attention`}>
            <Text size="sm" mb="xs">
              “{device.name || device.device_id}” — {problemText(device.problem).toLowerCase()}. Restore it in Home Assistant, or
              choose a different device for this spot.
            </Text>
            <Group gap="xs">
              <Button size="xs" variant="light" color="orange" onClick={onEdit}>
                Choose another
              </Button>
              <Button size="xs" variant="subtle" color="orange" loading={unassign.isPending} onClick={() => unassign.mutate(role)}>
                Unassign
              </Button>
            </Group>
          </Alert>
        ))}
    </Stack>
  );
}
