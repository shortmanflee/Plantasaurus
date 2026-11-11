import { ActionIcon, Alert, Badge, Button, FileButton, Group, Loader, Stack, Table, Text, Tooltip } from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconDownload, IconRestore, IconTrash, IconUpload } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, backupDownloadUrl, restoreBackupFile, S, unwrap } from "../api/client";
import { fmtDateTime } from "../lib/labels";
import { useApiMutation } from "../lib/mutations";
import { Empty } from "./common";

const COUNT_LABELS: [key: string, one: string, many: string][] = [
  ["plants", "plant", "plants"],
  ["plant_instances", "my plant", "my plants"],
  ["areas", "area", "areas"],
  ["spots", "spot", "spots"],
  ["instance_events", "event", "events"],
  ["assessments", "assessment", "assessments"],
  ["media", "photo", "photos"],
  ["custom_field_definitions", "custom field", "custom fields"],
];

export function summarizeCounts(counts: Record<string, number>): string {
  return COUNT_LABELS.filter(([key]) => counts[key])
    .map(([key, one, many]) => `${counts[key]} ${counts[key] === 1 ? one : many}`)
    .join(", ");
}

function fmtBytes(bytes: number | null): string {
  if (bytes == null) return "";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value.toFixed(unit && value < 10 ? 1 : 0)} ${units[unit]}`;
}

const STATUS_COLORS: Record<S["BackupRead"]["status"], string> = { pending: "blue", running: "blue", ready: "green", failed: "red" };

const REPLACE_WARNING = (
  <Stack gap="xs">
    <Text size="sm">
      This <b>replaces all plants, locations, my plants, history and photos</b> with the contents of the backup.
    </Text>
    <Text size="sm">
      Your current data is backed up first, so you can undo this by restoring that backup. Users, API tokens and integration
      settings are not changed.
    </Text>
  </Stack>
);

export function Backups() {
  const qc = useQueryClient();
  const [restoring, setRestoring] = useState(false);
  const { data: backups = [] } = useQuery({
    queryKey: ["backups"],
    queryFn: () => unwrap(api.GET("/api/v1/backups")),
    // Poll while a job is being built so it flips to "ready" without a reload.
    refetchInterval: (query) => (query.state.data?.some((b) => b.status === "pending" || b.status === "running") ? 2000 : false),
  });
  const busy = backups.some((b) => b.status === "pending" || b.status === "running");

  const create = useApiMutation(() => unwrap(api.POST("/api/v1/backups")), {
    invalidate: [["backups"]],
    success: "Backup started",
  });
  const remove = useApiMutation(
    (id: number) => unwrap(api.DELETE("/api/v1/backups/{backup_id}", { params: { path: { backup_id: id } } })),
    { invalidate: [["backups"]], success: "Backup deleted" },
  );

  const runRestore = async (fn: () => Promise<S["RestoreResult"]>) => {
    setRestoring(true);
    try {
      const result = await fn();
      // Everything may have changed.
      await qc.invalidateQueries();
      notifications.show({ color: "green", title: "Restored", message: summarizeCounts(result.counts) || "The backup was empty" });
    } catch (err) {
      notifications.show({ color: "red", title: "Restore failed", message: (err as Error).message });
      qc.invalidateQueries({ queryKey: ["backups"] });
    } finally {
      setRestoring(false);
    }
  };

  const confirmRestore = (title: string, fn: () => Promise<S["RestoreResult"]>) =>
    modals.openConfirmModal({
      title,
      children: REPLACE_WARNING,
      labels: { confirm: "Replace my data", cancel: "Cancel" },
      confirmProps: { color: "red" },
      onConfirm: () => runRestore(fn),
    });

  const restoreFromServer = (b: S["BackupRead"]) =>
    confirmRestore(`Restore the backup from ${fmtDateTime(b.created_at)}?`, () =>
      unwrap(api.POST("/api/v1/backups/{backup_id}/restore", { params: { path: { backup_id: b.id } } })),
    );

  const restoreFromFile = (file: File | null) => {
    if (file) confirmRestore(`Restore from ${file.name}?`, () => restoreBackupFile(file));
  };

  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Builds a zip with every plant, my plant, location, placement, event, assessment, custom field and photo. The job runs in
        the background; the backup will appear in the table below when it's ready. Users, API tokens and integration credentials
        are not included.
      </Text>
      <Group>
        <Button onClick={() => create.mutate(undefined)} loading={create.isPending} disabled={busy || restoring}>
          Create backup
        </Button>
        <FileButton onChange={restoreFromFile} accept="application/zip,.zip">
          {(props) => (
            <Button {...props} variant="default" leftSection={<IconUpload size={16} />} loading={restoring} disabled={busy}>
              Restore from file…
            </Button>
          )}
        </FileButton>
      </Group>
      {restoring && <Alert color="blue">Restoring… this can take a moment if there are many photos.</Alert>}
      {backups.length ? (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Created</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Contents</Table.Th>
              <Table.Th>Size</Table.Th>
              <Table.Th></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {backups.map((b) => (
              <Table.Tr key={b.id}>
                <Table.Td>
                  {fmtDateTime(b.created_at)}
                  {b.note && (
                    <Text size="xs" c="dimmed">
                      {b.note}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Group gap={6} wrap="nowrap">
                    {(b.status === "pending" || b.status === "running") && <Loader size={12} />}
                    <Badge color={STATUS_COLORS[b.status]} variant="light">
                      {b.status === "pending" ? "queued" : b.status === "running" ? "building" : b.status}
                    </Badge>
                  </Group>
                  {b.error && (
                    <Text size="xs" c="red">
                      {b.error}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{summarizeCounts(b.counts)}</Text>
                  {!!b.counts.missing_media_files && (
                    <Text size="xs" c="orange">
                      {b.counts.missing_media_files} photo file(s) were missing on disk and were skipped
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>{fmtBytes(b.size_bytes)}</Table.Td>
                <Table.Td>
                  <Group gap={4} justify="flex-end" wrap="nowrap">
                    {b.status === "ready" && (
                      <>
                        <Tooltip label="Download">
                          <ActionIcon variant="subtle" component="a" href={backupDownloadUrl(b.id)} download>
                            <IconDownload size={16} />
                          </ActionIcon>
                        </Tooltip>
                        <Tooltip label="Restore">
                          <ActionIcon variant="subtle" disabled={busy || restoring} onClick={() => restoreFromServer(b)}>
                            <IconRestore size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </>
                    )}
                    {b.status !== "pending" && b.status !== "running" && (
                      <Tooltip label="Delete">
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          onClick={() =>
                            modals.openConfirmModal({
                              title: "Delete this backup?",
                              children: <Text size="sm">The zip is removed from the server. Copies you downloaded are not affected.</Text>,
                              labels: { confirm: "Delete", cancel: "Cancel" },
                              confirmProps: { color: "red" },
                              onConfirm: () => remove.mutate(b.id),
                            })
                          }
                        >
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Tooltip>
                    )}
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : (
        <Empty>No backups yet</Empty>
      )}
    </Stack>
  );
}
