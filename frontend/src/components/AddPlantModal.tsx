import {
  Alert,
  Anchor,
  Badge,
  Button,
  Group,
  Image,
  Loader,
  Modal,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  UnstyledButton,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconDatabase, IconPencil, IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, S, unwrap } from "../api/client";
import { useApiMutation } from "../lib/mutations";
import PlantForm from "./PlantForm";

interface Props {
  opened: boolean;
  onClose: () => void;
  onCreated: (plant: S["PlantRead"]) => void;
}

export default function AddPlantModal({ opened, onClose, onCreated }: Props) {
  const { data: opb } = useQuery({
    queryKey: ["opb", "status"],
    queryFn: () => unwrap(api.GET("/api/v1/openplantbook/status")),
    enabled: opened,
  });
  const configured = opb?.configured ?? false;
  const [tab, setTab] = useState<string | null>("opb");

  const create = useApiMutation((body: S["PlantCreate"]) => unwrap(api.POST("/api/v1/plants", { body })), {
    invalidate: [["plants"]],
    success: "Plant added",
    onSuccess: (p) => {
      onClose();
      onCreated(p);
    },
  });

  return (
    <Modal opened={opened} onClose={onClose} title="Add a plant" size="xl">
      <Tabs value={configured ? tab : "manual"} onChange={setTab}>
        <Tabs.List mb="md">
          <Tabs.Tab value="opb" leftSection={<IconDatabase size={16} />} disabled={!configured}>
            Search Open Plantbook
          </Tabs.Tab>
          <Tabs.Tab value="manual" leftSection={<IconPencil size={16} />}>
            Enter manually
          </Tabs.Tab>
        </Tabs.List>
        {!configured && opb && (
          <Alert color="yellow" mb="md">
            Open Plantbook isn't configured. Add API credentials under{" "}
            <Anchor component={Link} to="/settings?tab=integrations" onClick={onClose}>
              Settings → Integrations
            </Anchor>{" "}
            to search it.
          </Alert>
        )}
        <Tabs.Panel value="opb">
          {opened && configured && (
            <OPBSearch
              onImported={(p) => {
                onClose();
                onCreated(p);
              }}
            />
          )}
        </Tabs.Panel>
        <Tabs.Panel value="manual">
          <PlantForm submitLabel="Add plant" loading={create.isPending} onSubmit={(values) => create.mutate(values)} />
        </Tabs.Panel>
      </Tabs>
    </Modal>
  );
}

function OPBSearch({ onImported }: { onImported: (p: S["PlantRead"]) => void }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [debounced] = useDebouncedValue(q.trim(), 400);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("");

  const search = useQuery({
    queryKey: ["opb", "search", debounced],
    queryFn: () => unwrap(api.GET("/api/v1/openplantbook/search", { params: { query: { q: debounced } } })),
    enabled: debounced.length >= 2,
  });
  const detail = useQuery({
    queryKey: ["opb", "detail", selected],
    queryFn: () => unwrap(api.GET("/api/v1/openplantbook/plants/{pid}", { params: { path: { pid: selected! } } })),
    enabled: !!selected,
  });
  const importPlant = useApiMutation(
    () =>
      unwrap(api.POST("/api/v1/plants/import-opb", { body: { pid: selected!, common_name: name.trim() || null, download_image: true } })),
    { invalidate: [["plants"]], success: (p) => `Imported ${p.common_name}`, onSuccess: onImported },
  );

  const ranges: [string, number | null | undefined, number | null | undefined, string][] = detail.data
    ? [
        ["Light", detail.data.min_light_lux, detail.data.max_light_lux, "lux"],
        ["Temperature", detail.data.min_temp, detail.data.max_temp, "°C"],
        ["Humidity", detail.data.min_env_humid, detail.data.max_env_humid, "%"],
        ["Soil moisture", detail.data.min_soil_moist, detail.data.max_soil_moist, "%"],
        ["Soil EC", detail.data.min_soil_ec, detail.data.max_soil_ec, "µS/cm"],
      ]
    : [];

  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      <Stack>
        <TextInput
          placeholder="e.g. monstera, lavender, tomato"
          leftSection={<IconSearch size={16} />}
          rightSection={search.isFetching ? <Loader size="xs" /> : null}
          value={q}
          onChange={(e) => setQ(e.currentTarget.value)}
          data-autofocus
        />
        {search.error && <Alert color="red">{search.error.message}</Alert>}
        <ScrollArea h={360}>
          <Stack gap={4}>
            {search.data?.map((r) => (
              <UnstyledButton
                key={r.pid}
                p="xs"
                style={{
                  borderRadius: 8,
                  background: r.pid === selected ? "var(--mantine-color-green-light)" : undefined,
                }}
                onClick={() => {
                  setSelected(r.pid);
                  setName("");
                }}
              >
                <Text fw={500} fs="italic">
                  {r.display_pid ?? r.pid}
                </Text>
                <Group gap={4}>
                  {r.alias && (
                    <Text size="xs" c="dimmed">
                      {r.alias}
                    </Text>
                  )}
                  {r.already_imported_plant_id && (
                    <Badge size="xs" variant="light">
                      already added
                    </Badge>
                  )}
                </Group>
              </UnstyledButton>
            ))}
            {search.data && !search.data.length && (
              <Text c="dimmed" size="sm" ta="center">
                No matches
              </Text>
            )}
          </Stack>
        </ScrollArea>
      </Stack>
      <Stack>
        {!selected && (
          <Text c="dimmed" size="sm">
            Search and pick a result to preview it.
          </Text>
        )}
        {detail.isLoading && <Loader />}
        {detail.error && <Alert color="red">{detail.error.message}</Alert>}
        {detail.data && (
          <>
            {detail.data.image_url && <Image src={detail.data.image_url} h={180} radius="md" fit="cover" alt="" />}
            <div>
              <Text fw={600} fs="italic">
                {detail.data.display_pid}
              </Text>
              <Text size="sm" c="dimmed">
                {detail.data.alias} {detail.data.category && `· ${detail.data.category}`}
              </Text>
            </div>
            <Table>
              <Table.Tbody>
                {ranges.map(([label, min, max, unit]) => (
                  <Table.Tr key={label}>
                    <Table.Td>{label}</Table.Td>
                    <Table.Td>{min != null || max != null ? `${min ?? "?"} – ${max ?? "?"} ${unit}` : "-"}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            {(() => {
              const existing = search.data?.find((r) => r.pid === selected)?.already_imported_plant_id;
              return existing ? (
                <Button variant="light" onClick={() => navigate(`/plants/${existing}`)}>
                  Already in your library: open it
                </Button>
              ) : (
                <Group align="flex-end">
                  <TextInput
                    style={{ flex: 1 }}
                    label="Name (optional)"
                    placeholder="Defaults to the common name"
                    value={name}
                    onChange={(e) => setName(e.currentTarget.value)}
                  />
                  <Button loading={importPlant.isPending} onClick={() => importPlant.mutate(undefined)}>
                    Import
                  </Button>
                </Group>
              );
            })()}
          </>
        )}
      </Stack>
    </SimpleGrid>
  );
}
