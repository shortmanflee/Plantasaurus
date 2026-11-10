import { Badge, Button, Card, Group, Pagination, Select, SimpleGrid, Stack, Text, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconPlus, IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import AddPlantModal from "../components/AddPlantModal";
import { Empty, PageHeader, PlantImage, QueryState } from "../components/common";

const PAGE = 48;

export default function Plants() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [debounced] = useDebouncedValue(q, 250);
  const [category, setCategory] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);

  const { data: categories = [] } = useQuery({
    queryKey: ["plants", "categories"],
    queryFn: () => unwrap(api.GET("/api/v1/plants/categories")),
  });
  const { data, isLoading, error } = useQuery({
    queryKey: ["plants", "list", debounced, category, page],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/plants", {
          params: { query: { q: debounced || undefined, category: category ?? undefined, limit: PAGE, offset: (page - 1) * PAGE } },
        }),
      ),
  });

  return (
    <>
      <PageHeader
        title="Plants"
        subtitle="Your plant library: each entry can have many plants in different places"
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
            Add plant
          </Button>
        }
      />
      <Group mb="md">
        <TextInput
          placeholder="Search"
          leftSection={<IconSearch size={16} />}
          value={q}
          onChange={(e) => {
            setQ(e.currentTarget.value);
            setPage(1);
          }}
        />
        <Select placeholder="All categories" data={categories} clearable searchable value={category} onChange={(v) => { setCategory(v); setPage(1); }} />
      </Group>
      <QueryState isLoading={isLoading} error={error} />
      {data && !data.items.length && <Empty>No plants yet. Add one from Open Plantbook or manually.</Empty>}
      <SimpleGrid cols={{ base: 1, xs: 2, md: 3, lg: 4 }}>
        {data?.items.map((p) => (
          <Card key={p.id} withBorder component={Link} to={`/plants/${p.id}`} padding="sm">
            <Card.Section>
              <PlantImage mediaId={p.image_media_id} size="100%" height={160} radius="0" />
            </Card.Section>
            <Stack gap={2} mt="sm">
              <Text fw={600} lineClamp={1}>
                {p.common_name}
              </Text>
              <Text size="sm" c="dimmed" fs="italic" lineClamp={1}>
                {p.scientific_name || " "}
              </Text>
              <Group gap={4} mt={4}>
                <Badge variant="light">{p.active_instance_count} active</Badge>
                {p.category && (
                  <Badge variant="outline" color="gray">
                    {p.category}
                  </Badge>
                )}
              </Group>
            </Stack>
          </Card>
        ))}
      </SimpleGrid>
      {data && data.total > PAGE && (
        <Group justify="center" mt="lg">
          <Pagination total={Math.ceil(data.total / PAGE)} value={page} onChange={setPage} />
        </Group>
      )}
      <AddPlantModal opened={adding} onClose={() => setAdding(false)} onCreated={(p) => navigate(`/plants/${p.id}`)} />
    </>
  );
}
