import { Anchor, Button, Group, MultiSelect, Pagination, Select, Table, Text, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconPlus, IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, S, unwrap } from "../api/client";
import AddInstanceModal from "../components/AddInstanceModal";
import { Empty, PageHeader, PlantImage, QueryState, Stars, StatusBadge } from "../components/common";
import { fmtDate, options, STATUSES } from "../lib/labels";
import { useLocationTree } from "../lib/queries";

const PAGE = 50;
type Status = S["InstanceRead"]["status"];

export default function Instances() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [debounced] = useDebouncedValue(q, 250);
  const [statuses, setStatuses] = useState<string[]>(["active"]);
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const areaId = params.get("area");
  const { data: tree = [] } = useLocationTree();

  const { data, isLoading, error } = useQuery({
    queryKey: ["instances", "list", debounced, statuses, areaId, page],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/instances", {
          params: {
            query: {
              q: debounced || undefined,
              status: statuses.length ? (statuses as Status[]) : undefined,
              area_id: areaId ? Number(areaId) : undefined,
              limit: PAGE,
              offset: (page - 1) * PAGE,
            },
          },
        }),
      ),
  });

  return (
    <>
      <PageHeader
        title="My plants"
        subtitle="Every plant you have (or had), and where it lives"
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
            Add
          </Button>
        }
      />
      <Group mb="md" align="flex-end">
        <TextInput placeholder="Search" leftSection={<IconSearch size={16} />} value={q} onChange={(e) => { setQ(e.currentTarget.value); setPage(1); }} />
        <MultiSelect
          placeholder="Any status"
          data={options(STATUSES)}
          value={statuses}
          onChange={(v) => { setStatuses(v); setPage(1); }}
          clearable
          w={260}
        />
        <Select
          placeholder="Any area"
          data={tree.map((a) => ({ value: String(a.id), label: a.name }))}
          value={areaId}
          clearable
          onChange={(v) => {
            setParams(v ? { area: v } : {});
            setPage(1);
          }}
        />
      </Group>
      <QueryState isLoading={isLoading} error={error} />
      {data && !data.items.length && <Empty>No plants match.</Empty>}
      {data && data.items.length > 0 && (
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th></Table.Th>
              <Table.Th>Plant</Table.Th>
              <Table.Th>Location</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Rating</Table.Th>
              <Table.Th>Acquired</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.items.map((i) => (
              <Table.Tr key={i.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/instances/${i.id}`)}>
                <Table.Td w={48}>
                  <PlantImage mediaId={i.plant_image_media_id} size={36} />
                </Table.Td>
                <Table.Td>
                  <Anchor component={Link} to={`/instances/${i.id}`} onClick={(e) => e.stopPropagation()}>
                    {i.nickname || i.plant_name}
                  </Anchor>
                  {i.nickname && <Text size="xs" c="dimmed">{i.plant_name}</Text>}
                  {i.quantity > 1 && <Text size="xs" c="dimmed">×{i.quantity}</Text>}
                </Table.Td>
                <Table.Td>
                  {i.spot_name ? (
                    <Text size="sm">
                      {i.area_name} › {i.spot_name}
                      {i.position_label && ` › ${i.position_label}`}
                    </Text>
                  ) : (
                    <Text size="sm" c="dimmed">-</Text>
                  )}
                </Table.Td>
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
      )}
      {data && data.total > PAGE && (
        <Group justify="center" mt="lg">
          <Pagination total={Math.ceil(data.total / PAGE)} value={page} onChange={setPage} />
        </Group>
      )}
      <AddInstanceModal opened={adding} onClose={() => setAdding(false)} onCreated={(i) => navigate(`/instances/${i.id}`)} />
    </>
  );
}
