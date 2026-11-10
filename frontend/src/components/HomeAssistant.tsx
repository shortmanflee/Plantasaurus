import { Alert, Anchor, Badge, Button, Group, List, Select, Stack, Text, Tooltip } from "@mantine/core";
import { IconAlertTriangle, IconDroplet, IconHeartRateMonitor } from "@tabler/icons-react";
import { Link } from "react-router-dom";
import { api, S, unwrap } from "../api/client";
import { fromNow } from "../lib/labels";
import { useApiMutation } from "../lib/mutations";
import { HARole, useHADevices, useHAIssues, useHAStatus } from "../lib/queries";

export const ROLE_LABELS: Record<HARole, string> = { irrigation_zone: "Irrigation zone", plant_monitor: "Plant monitor" };
const ROLE_ICONS = { irrigation_zone: IconDroplet, plant_monitor: IconHeartRateMonitor };

export const INVALIDATE_HA = [["homeassistant"], ["locations"], ["spots"]];

export function problemText(problem: S["HADeviceRef"]["problem"]): string {
  return problem === "deleted" ? "Removed from Home Assistant" : "No longer labelled in Home Assistant";
}

const deviceLabel = (name: string | null | undefined, id: string) => name || id;

/** Select for an HA device. Keeps the current (possibly missing) device selectable so it can be seen and cleared. */
export function DevicePicker({
  role,
  value,
  onChange,
  current,
  spotId,
}: {
  role: HARole;
  value: string | null;
  onChange: (v: string | null) => void;
  current?: S["HADeviceRef"] | null;
  spotId?: number;
}) {
  const { data: status } = useHAStatus();
  const { data: devices = [], isFetching, error } = useHADevices(role, !!status?.configured);
  const label = role === "irrigation_zone" ? status?.irrigation_label : status?.monitor_label;

  const data = devices.map((d) => {
    const taken = role === "plant_monitor" && d.assigned_spot_ids.some((id) => id !== spotId);
    return {
      value: d.device_id,
      label: `${deviceLabel(d.name, d.device_id)}${d.area_name ? ` (${d.area_name})` : ""}${taken ? " · in another spot" : ""}`,
      disabled: taken,
    };
  });
  if (current && !data.some((d) => d.value === current.device_id)) {
    data.unshift({
      value: current.device_id,
      label: `${deviceLabel(current.name, current.device_id)} · ${current.problem ? "missing" : "unavailable"}`,
      disabled: false,
    });
  }

  return (
    <Select
      label={ROLE_LABELS[role]}
      description={label ? `HA devices labelled “${label}”` : undefined}
      placeholder={isFetching ? "Loading from Home Assistant…" : data.length ? "None" : "No labelled devices found"}
      data={data}
      value={value}
      onChange={onChange}
      clearable
      searchable
      error={error ? error.message : current?.problem && value === current.device_id ? problemText(current.problem) : undefined}
      leftSection={(() => {
        const Icon = ROLE_ICONS[role];
        return <Icon size={16} />;
      })()}
    />
  );
}

/** Badge for an assigned device, turning into a warning when it has gone from HA. */
export function DeviceBadge({ role, device }: { role: HARole; device: S["HADeviceRef"] }) {
  const Icon = device.problem ? IconAlertTriangle : ROLE_ICONS[role];
  const badge = (
    <Badge
      variant="light"
      color={device.problem ? "orange" : role === "irrigation_zone" ? "blue" : "teal"}
      leftSection={<Icon size={12} />}
      tt="none"
    >
      {deviceLabel(device.name, device.device_id)}
    </Badge>
  );
  return device.problem ? (
    <Tooltip label={`${ROLE_LABELS[role]}: ${problemText(device.problem)}`}>{badge}</Tooltip>
  ) : (
    <Tooltip label={ROLE_LABELS[role]}>{badge}</Tooltip>
  );
}

export function spotHasDeviceProblem(spot: Pick<S["SpotRead"], "irrigation_zone" | "plant_monitor">): boolean {
  return !!(spot.irrigation_zone?.problem || spot.plant_monitor?.problem);
}

/** Lists spots whose irrigation zone or plant monitor has gone from HA, with a quick "unassign". */
export function HAIssuesAlert() {
  const { data: status } = useHAStatus();
  const { data: issues = [] } = useHAIssues(!!status?.issue_count);
  const unassign = useApiMutation(
    (issue: S["HAIssue"]) =>
      unwrap(
        api.PATCH("/api/v1/spots/{spot_id}", {
          params: { path: { spot_id: issue.spot_id } },
          body: issue.role === "irrigation_zone" ? { irrigation_zone_device_id: null } : { plant_monitor_device_id: null },
        }),
      ),
    { invalidate: INVALIDATE_HA, success: "Device unassigned" },
  );
  if (!issues.length) return null;
  return (
    <Alert color="orange" icon={<IconAlertTriangle />} title="Home Assistant devices need attention" mb="md">
      <Stack gap="xs">
        <Text size="sm">
          These devices have been removed from Home Assistant or lost their label. Restore them in Home Assistant, or pick a
          different device for the spot.
        </Text>
        <List size="sm" spacing={4}>
          {issues.map((i) => (
            <List.Item key={`${i.spot_id}-${i.role}`}>
              <Group gap="xs" wrap="wrap">
                <Anchor component={Link} to={`/spots/${i.spot_id}`} size="sm">
                  {i.area_name} → {i.spot_name}
                </Anchor>
                <Text size="sm">
                  {ROLE_LABELS[i.role].toLowerCase()} “{deviceLabel(i.device_name, i.device_id)}”: {problemText(i.problem).toLowerCase()}
                  {i.missing_since && ` (${fromNow(i.missing_since)})`}
                </Text>
                <Button size="compact-xs" variant="subtle" color="orange" loading={unassign.isPending} onClick={() => unassign.mutate(i)}>
                  Unassign
                </Button>
              </Group>
            </List.Item>
          ))}
        </List>
      </Stack>
    </Alert>
  );
}
