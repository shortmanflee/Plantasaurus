import {
  Anchor,
  Badge,
  Button,
  Card,
  Grid,
  Group,
  Menu,
  Modal,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconDots, IconPhoto, IconPlus, IconRefresh, IconTrash, IconPencil } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, S, unwrap, uploadMedia } from "../api/client";
import AddInstanceModal from "../components/AddInstanceModal";
import { CustomFieldValues } from "../components/CustomFields";
import { Empty, PageHeader, PlantImage, QueryState, Stars, StatusBadge } from "../components/common";
import PlantForm from "../components/PlantForm";
import { fmtDate, fromNow, YES_NO_MAYBE, label } from "../lib/labels";
import { useApiMutation } from "../lib/mutations";

export default function PlantDetail() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  // Lives outside the Menu: the dropdown unmounts on item click, which would drop the chosen file.
  const fileInput = useRef<HTMLInputElement>(null);

  const { data: plant, isLoading, error } = useQuery({
    queryKey: ["plants", id],
    queryFn: () => unwrap(api.GET("/api/v1/plants/{plant_id}", { params: { path: { plant_id: id } } })),
  });
  const { data: instances = [] } = useQuery({
    queryKey: ["instances", "by-plant", id],
    queryFn: () => unwrap(api.GET("/api/v1/plants/{plant_id}/instances", { params: { path: { plant_id: id } } })),
  });
  const { data: insights } = useQuery({
    queryKey: ["insights", "plant", id],
    queryFn: () => unwrap(api.GET("/api/v1/plants/{plant_id}/insights", { params: { path: { plant_id: id } } })),
  });

  const invalidate = [["plants"], ["instances"], ["insights"]];
  const update = useApiMutation(
    (body: S["PlantUpdate"]) => unwrap(api.PATCH("/api/v1/plants/{plant_id}", { params: { path: { plant_id: id } }, body })),
    { invalidate, success: "Saved", onSuccess: () => setEditing(false) },
  );
  const refresh = useApiMutation(
    () => unwrap(api.POST("/api/v1/plants/{plant_id}/opb-refresh", { params: { path: { plant_id: id }, query: { refresh_image: false } } })),
    { invalidate, success: "Refreshed from Open Plantbook" },
  );
  const remove = useApiMutation(
    () => unwrap(api.DELETE("/api/v1/plants/{plant_id}", { params: { path: { plant_id: id } } })),
    { invalidate: [["plants"]], success: "Plant deleted", onSuccess: () => navigate("/plants") },
  );
  const upload = useApiMutation(
    async (file: File) => {
      const media = await uploadMedia(file, { plantId: id });
      return unwrap(api.PATCH("/api/v1/plants/{plant_id}", { params: { path: { plant_id: id } }, body: { image_media_id: media.id } }));
    },
    { invalidate, success: "Image updated" },
  );

  if (!plant) return <QueryState isLoading={isLoading} error={error} />;

  const ranges: [string, number | null | undefined, number | null | undefined, string][] = [
    ["Light", plant.min_light_lux, plant.max_light_lux, "lux"],
    ["Light (PAR)", plant.min_light_mmol, plant.max_light_mmol, "mmol"],
    ["Temperature", plant.min_temp, plant.max_temp, "°C"],
    ["Air humidity", plant.min_env_humid, plant.max_env_humid, "%"],
    ["Soil moisture", plant.min_soil_moist, plant.max_soil_moist, "%"],
    ["Soil EC", plant.min_soil_ec, plant.max_soil_ec, "µS/cm"],
  ];
  const hasRanges = ranges.some(([, a, b]) => a != null || b != null);

  return (
    <>
      <PageHeader
        title={plant.common_name}
        subtitle={
          <Text span fs="italic">
            {[plant.scientific_name, plant.cultivar && `'${plant.cultivar}'`].filter(Boolean).join(" ")}
          </Text>
        }
        actions={
          <>
            <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
              Add to a location
            </Button>
            <Menu position="bottom-end">
              <Menu.Target>
                <Button variant="default" px="xs">
                  <IconDots size={18} />
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<IconPencil size={16} />} onClick={() => setEditing(true)}>
                  Edit
                </Menu.Item>
                <Menu.Item leftSection={<IconPhoto size={16} />} onClick={() => fileInput.current?.click()}>
                  Change image
                </Menu.Item>
                {plant.openplantbook_pid && (
                  <Menu.Item leftSection={<IconRefresh size={16} />} onClick={() => refresh.mutate(undefined)}>
                    Refresh from Open Plantbook
                  </Menu.Item>
                )}
                <Menu.Divider />
                <Menu.Item
                  color="red"
                  leftSection={<IconTrash size={16} />}
                  onClick={() =>
                    modals.openConfirmModal({
                      title: `Delete ${plant.common_name}?`,
                      children: <Text size="sm">This only works if it has no plants recorded against it.</Text>,
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
            <input
              ref={fileInput}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                const f = e.currentTarget.files?.[0];
                e.currentTarget.value = "";
                if (f) upload.mutate(f);
              }}
            />
          </>
        }
      />
      <Grid>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Stack>
            <PlantImage mediaId={plant.image_media_id} size="100%" height={260} />
            <Card withBorder>
              <Stack gap={6}>
                <Group gap={4}>
                  {plant.category && <Badge variant="outline">{plant.category}</Badge>}
                  {plant.is_perennial && <Badge variant="light">Perennial</Badge>}
                  {plant.toxic_to_pets && <Badge color="red" variant="light">Toxic to pets</Badge>}
                  {plant.sun_preference && <Badge color="yellow" variant="light">{plant.sun_preference.replace("_", " ")}</Badge>}
                  {plant.water_needs && <Badge color="blue" variant="light">{plant.water_needs} water</Badge>}
                  {plant.hardiness && <Badge color="cyan" variant="light">{plant.hardiness}</Badge>}
                </Group>
                {plant.description && <Text size="sm">{plant.description}</Text>}
                {plant.notes && (
                  <Text size="sm" c="dimmed" style={{ whiteSpace: "pre-wrap" }}>
                    {plant.notes}
                  </Text>
                )}
                {plant.openplantbook_pid && (
                  <Text size="xs" c="dimmed">
                    Open Plantbook: {plant.openplantbook_pid} · synced {fromNow(plant.opb_last_synced_at)}
                  </Text>
                )}
              </Stack>
            </Card>
            {hasRanges && (
              <Card withBorder>
                <Title order={5} mb="xs">
                  Care ranges
                </Title>
                <Table>
                  <Table.Tbody>
                    {ranges
                      .filter(([, a, b]) => a != null || b != null)
                      .map(([l, a, b, unit]) => (
                        <Table.Tr key={l}>
                          <Table.Td>{l}</Table.Td>
                          <Table.Td>
                            {a ?? "?"} – {b ?? "?"} {unit}
                          </Table.Td>
                        </Table.Tr>
                      ))}
                  </Table.Tbody>
                </Table>
              </Card>
            )}
            <CustomFieldValues entity="plant" value={plant.attributes as Record<string, unknown>} />
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Tabs defaultValue="instances">
            <Tabs.List mb="md">
              <Tabs.Tab value="instances">Plants ({instances.length})</Tabs.Tab>
              <Tabs.Tab value="insights">How it's done</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="instances">
              {instances.length ? (
                <Table highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Plant</Table.Th>
                      <Table.Th>Location</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th>Rating</Table.Th>
                      <Table.Th>Acquired</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {instances.map((i) => (
                      <Table.Tr key={i.id}>
                        <Table.Td>
                          <Anchor component={Link} to={`/instances/${i.id}`}>
                            {i.nickname || `#${i.id}`}
                          </Anchor>
                          {i.quantity > 1 && <Text span c="dimmed"> ×{i.quantity}</Text>}
                        </Table.Td>
                        <Table.Td>{i.spot_name ? `${i.area_name} › ${i.spot_name}${i.position_label ? ` › ${i.position_label}` : ""}` : "-"}</Table.Td>
                        <Table.Td>
                          <StatusBadge status={i.status} />
                        </Table.Td>
                        <Table.Td>
                          <Stars value={i.latest_overall_rating} />
                        </Table.Td>
                        <Table.Td>{fmtDate(i.acquired_date)}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              ) : (
                <Empty>None yet. Use “Add to a location” to record one.</Empty>
              )}
            </Tabs.Panel>
            <Tabs.Panel value="insights">{insights && <Insights data={insights} />}</Tabs.Panel>
          </Tabs>
        </Grid.Col>
      </Grid>
      <Modal opened={editing} onClose={() => setEditing(false)} title="Edit plant" size="xl">
        <PlantForm initial={plant} submitLabel="Save" loading={update.isPending} onSubmit={(v) => update.mutate(v)} />
      </Modal>
      <AddInstanceModal opened={adding} onClose={() => setAdding(false)} plantId={id} onCreated={(i) => navigate(`/instances/${i.id}`)} />
    </>
  );
}

const VERDICT_COLORS: Record<string, string> = { "Buy again": "green", "Mixed results": "yellow" };

function Insights({ data }: { data: S["PlantInsights"] }) {
  if (!data.instances_total) return <Empty>No history yet.</Empty>;
  const groups: [string, S["GroupPerformance"][]][] = [
    ["By spot", data.by_spot],
    ["Indoor / outdoor", data.by_environment],
    ["By aspect", data.by_aspect],
    ["By sun exposure", data.by_sun_exposure],
  ];
  return (
    <Stack>
      <Group>
        <Badge size="lg" color={VERDICT_COLORS[data.verdict] ?? (data.verdict.startsWith("Avoid") ? "red" : "gray")}>
          {data.verdict}
        </Badge>
      </Group>
      <SimpleGrid cols={{ base: 2, sm: 4 }}>
        <Card withBorder>
          <Text size="xs" c="dimmed">Survival rate</Text>
          <Text fw={700}>{data.survival_rate != null ? `${Math.round(data.survival_rate * 100)}%` : "-"}</Text>
        </Card>
        <Card withBorder>
          <Text size="xs" c="dimmed">Avg. rating</Text>
          <Stars value={data.ratings.avg_overall} />
        </Card>
        <Card withBorder>
          <Text size="xs" c="dimmed">Avg. lifespan (dead)</Text>
          <Text fw={700}>{data.avg_lifespan_days_dead != null ? `${Math.round(data.avg_lifespan_days_dead)} days` : "-"}</Text>
        </Card>
        <Card withBorder>
          <Text size="xs" c="dimmed">Buy again?</Text>
          <Text fw={700}>
            {Object.keys(data.would_buy_again).length
              ? Object.entries(data.would_buy_again).map(([k, v]) => `${label(YES_NO_MAYBE, k)}: ${v}`).join(", ")
              : "-"}
          </Text>
        </Card>
      </SimpleGrid>
      {Object.keys(data.end_reasons).length > 0 && (
        <Text size="sm">
          <b>Losses:</b> {Object.entries(data.end_reasons).map(([k, v]) => `${k} (${v})`).join(", ")}
        </Text>
      )}
      {groups.map(([title, rows]) =>
        rows.length ? (
          <div key={title}>
            <Title order={5} mb={4}>
              {title}
            </Title>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th></Table.Th>
                  <Table.Th>Plants</Table.Th>
                  <Table.Th>Avg. rating</Table.Th>
                  <Table.Th>Deaths</Table.Th>
                  <Table.Th>Avg. days there</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.map((r) => (
                  <Table.Tr key={r.key}>
                    <Table.Td>{r.label.replace("_", " ")}</Table.Td>
                    <Table.Td>{r.instances}</Table.Td>
                    <Table.Td>
                      <Stars value={r.avg_overall} />
                    </Table.Td>
                    <Table.Td>{r.deaths || "-"}</Table.Td>
                    <Table.Td>{r.avg_days != null ? Math.round(r.avg_days) : "-"}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </div>
        ) : null,
      )}
    </Stack>
  );
}
