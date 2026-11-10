import { Alert, Badge, Center, Group, Image, Loader, Stack, Text, Title } from "@mantine/core";
import { IconAlertCircle, IconPlant } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { mediaUrl } from "../api/client";
import { label, STATUS_COLORS, STATUSES } from "../lib/labels";

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-start" mb="md" wrap="wrap">
      <Stack gap={2}>
        <Title order={2}>{title}</Title>
        {subtitle && <Text c="dimmed">{subtitle}</Text>}
      </Stack>
      {actions && <Group gap="xs">{actions}</Group>}
    </Group>
  );
}

export function QueryState({ isLoading, error }: { isLoading: boolean; error: Error | null }) {
  if (isLoading) {
    return (
      <Center p="xl">
        <Loader />
      </Center>
    );
  }
  if (error) {
    return (
      <Alert color="red" icon={<IconAlertCircle />} title="Could not load">
        {error.message}
      </Alert>
    );
  }
  return null;
}

export function PlantImage({
  mediaId,
  size = 64,
  height,
  radius = "md",
}: {
  mediaId?: number | null;
  size?: number | string;
  height?: number;
  radius?: string;
}) {
  const h = height ?? size;
  if (!mediaId) {
    return (
      <Center w={size} h={h} bg="var(--mantine-color-green-light)" style={{ borderRadius: `var(--mantine-radius-${radius}, 0)` }}>
        <IconPlant size={typeof h === "number" ? Math.min(h * 0.5, 64) : 32} color="var(--mantine-color-green-6)" />
      </Center>
    );
  }
  return <Image src={mediaUrl(mediaId)} w={size} h={h} radius={radius} fit="cover" alt="" />;
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge color={STATUS_COLORS[status] ?? "gray"} variant="light">
      {label(STATUSES, status)}
    </Badge>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <Text c="dimmed" ta="center" py="lg">
      {children}
    </Text>
  );
}

export function Stars({ value }: { value: number | null | undefined }) {
  if (value == null) return <Text c="dimmed">-</Text>;
  return (
    <Text c="yellow.7" fw={600} span>
      {"★".repeat(Math.round(value))}
      <Text span c="gray.4">
        {"★".repeat(5 - Math.round(value))}
      </Text>{" "}
      <Text span size="xs" c="dimmed">
        {Number.isInteger(value) ? value : value.toFixed(1)}
      </Text>
    </Text>
  );
}
