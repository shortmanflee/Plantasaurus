import { Anchor, Card, Grid, Group, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Empty, PageHeader, QueryState } from "../components/common";
import { HAIssuesAlert } from "../components/HomeAssistant";
import { EVENT_TYPES, fromNow, label } from "../lib/labels";

function Stat({ label, value, to }: { label: string; value: number; to: string }) {
  return (
    <Card withBorder component={Link} to={to}>
      <Text c="dimmed" size="sm">
        {label}
      </Text>
      <Text fw={700} size="xl">
        {value}
      </Text>
    </Card>
  );
}

export default function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["insights", "summary"],
    queryFn: () => unwrap(api.GET("/api/v1/insights/summary")),
  });
  if (!data) return <QueryState isLoading={isLoading} error={error} />;

  const who = (e: { nickname?: string | null; plant_name: string }) => e.nickname ? `${e.nickname} (${e.plant_name})` : e.plant_name;

  return (
    <>
      <PageHeader title="Dashboard" />
      <HAIssuesAlert />
      <SimpleGrid cols={{ base: 2, sm: 4 }} mb="lg">
        <Stat label="Plant types" value={data.plants} to="/plants" />
        <Stat label="Active plants" value={data.active_instances} to="/instances" />
        <Stat label="Areas" value={data.areas} to="/locations" />
        <Stat label="Spots" value={data.spots} to="/locations" />
      </SimpleGrid>
      <Grid>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Card withBorder>
            <Title order={4} mb="sm">
              Recent activity
            </Title>
            {data.recent_events.length ? (
              <Table>
                <Table.Tbody>
                  {data.recent_events.map((e) => (
                    <Table.Tr key={e.id}>
                      <Table.Td>
                        <Anchor component={Link} to={`/instances/${e.instance_id}`}>
                          {who(e)}
                        </Anchor>
                      </Table.Td>
                      <Table.Td>{label(EVENT_TYPES, e.event_type)}</Table.Td>
                      <Table.Td>
                        <Text size="sm" c="dimmed">
                          {fromNow(e.occurred_at)}
                        </Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            ) : (
              <Empty>Nothing yet. Add a plant to get started.</Empty>
            )}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Stack>
            <Card withBorder>
              <Title order={4} mb="sm">
                Due an assessment
              </Title>
              <Text size="xs" c="dimmed" mb="xs">
                Active plants not assessed in the last 90 days
              </Text>
              {data.needs_assessment.length ? (
                <Stack gap={4}>
                  {data.needs_assessment.map((n) => (
                    <Group key={n.instance_id} justify="space-between">
                      <Anchor component={Link} to={`/instances/${n.instance_id}`}>
                        {who(n)}
                      </Anchor>
                      <Text size="xs" c="dimmed">
                        {n.last_assessed_at ? fromNow(n.last_assessed_at) : "never"}
                      </Text>
                    </Group>
                  ))}
                </Stack>
              ) : (
                <Empty>All caught up</Empty>
              )}
            </Card>
            <Card withBorder>
              <Title order={4} mb="sm">
                Recent losses
              </Title>
              {data.recent_losses.length ? (
                <Stack gap={4}>
                  {data.recent_losses.map((e) => (
                    <Group key={e.id} justify="space-between">
                      <Anchor component={Link} to={`/instances/${e.instance_id}`}>
                        {who(e)}
                      </Anchor>
                      <Text size="xs" c="dimmed">
                        {label(EVENT_TYPES, e.event_type)} {fromNow(e.occurred_at)}
                      </Text>
                    </Group>
                  ))}
                </Stack>
              ) : (
                <Empty>None</Empty>
              )}
            </Card>
          </Stack>
        </Grid.Col>
      </Grid>
    </>
  );
}
