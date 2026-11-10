import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Checkbox,
  Code,
  CopyButton,
  Group,
  Modal,
  NumberInput,
  PasswordInput,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Tabs,
  TagsInput,
  Text,
  TextInput,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { modals } from "@mantine/modals";
import { IconCheck, IconCopy, IconTrash, IconPencil } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, BASE_PATH, S, unwrap } from "../api/client";
import { Empty, PageHeader } from "../components/common";
import { fmtDateTime, fromNow } from "../lib/labels";
import { useApiMutation } from "../lib/mutations";
import { useAuthStatus, useHAStatus, useOPBStatus } from "../lib/queries";
import { INVALIDATE_HA } from "../components/HomeAssistant";

export default function Settings() {
  const { data: auth } = useAuthStatus();
  const isAdmin = !!auth?.user?.is_admin;
  const [params, setParams] = useSearchParams();
  return (
    <>
      <PageHeader title="Settings" />
      <Tabs value={params.get("tab") ?? "account"} onChange={(tab) => setParams(tab && tab !== "account" ? { tab } : {}, { replace: true })}>
        <Tabs.List mb="md">
          <Tabs.Tab value="account">Account</Tabs.Tab>
          <Tabs.Tab value="tokens">API tokens</Tabs.Tab>
          <Tabs.Tab value="fields">Custom fields</Tabs.Tab>
          {isAdmin && <Tabs.Tab value="users">Users</Tabs.Tab>}
          <Tabs.Tab value="integrations">Integrations</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="account">{auth?.user && <Account user={auth.user} />}</Tabs.Panel>
        <Tabs.Panel value="tokens">
          <Tokens />
        </Tabs.Panel>
        <Tabs.Panel value="fields">
          <CustomFields isAdmin={isAdmin} />
        </Tabs.Panel>
        {isAdmin && (
          <Tabs.Panel value="users">
            <Users currentId={auth!.user!.id} />
          </Tabs.Panel>
        )}
        <Tabs.Panel value="integrations">
          <Integrations isAdmin={isAdmin} />
        </Tabs.Panel>
      </Tabs>
    </>
  );
}

function Account({ user }: { user: S["UserRead"] }) {
  const form = useForm({
    initialValues: { display_name: user.display_name ?? "", password: "", confirm: "" },
    validate: {
      password: (v: string) => (v && v.length < 8 ? "At least 8 characters" : null),
      confirm: (v: string, values: { password: string }) => (values.password && v !== values.password ? "Passwords do not match" : null),
    },
  });
  const save = useApiMutation(
    (v: typeof form.values) =>
      unwrap(
        api.PATCH("/api/v1/users/{user_id}", {
          params: { path: { user_id: user.id } },
          body: { display_name: v.display_name || null, ...(v.password ? { password: v.password } : {}) },
        }),
      ),
    { invalidate: [["auth"]], success: "Saved", onSuccess: () => form.setValues({ password: "", confirm: "" }) },
  );
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack maw={400}>
        <TextInput label="Username" value={user.username} disabled />
        <TextInput label="Display name" {...form.getInputProps("display_name")} />
        <PasswordInput label="New password" autoComplete="new-password" {...form.getInputProps("password")} />
        <PasswordInput label="Confirm new password" {...form.getInputProps("confirm")} />
        <Group>
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function Tokens() {
  const [name, setName] = useState("");
  const [created, setCreated] = useState<S["ApiTokenCreated"] | null>(null);
  const { data: tokens = [] } = useQuery({ queryKey: ["tokens"], queryFn: () => unwrap(api.GET("/api/v1/tokens")) });
  const create = useApiMutation(() => unwrap(api.POST("/api/v1/tokens", { body: { name: name.trim() } })), {
    invalidate: [["tokens"]],
    onSuccess: (t) => {
      setCreated(t);
      setName("");
    },
  });
  const revoke = useApiMutation(
    (id: number) => unwrap(api.DELETE("/api/v1/tokens/{token_id}", { params: { path: { token_id: id } } })),
    { invalidate: [["tokens"]], success: "Token revoked" },
  );
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        API tokens let other systems (Home Assistant, MCP clients, scripts) use the API. Send them as{" "}
        <Code>Authorization: Bearer &lt;token&gt;</Code>.
      </Text>
      <Group>
        <TextInput placeholder="Token name, e.g. Home Assistant" value={name} onChange={(e) => setName(e.currentTarget.value)} w={320} />
        <Button disabled={!name.trim()} loading={create.isPending} onClick={() => create.mutate(undefined)}>
          Create token
        </Button>
      </Group>
      {tokens.length ? (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>Token</Table.Th>
              <Table.Th>Created</Table.Th>
              <Table.Th>Last used</Table.Th>
              <Table.Th></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {tokens.map((t) => (
              <Table.Tr key={t.id} opacity={t.revoked_at ? 0.5 : 1}>
                <Table.Td>{t.name}</Table.Td>
                <Table.Td>
                  <Code>{t.prefix}…</Code>
                </Table.Td>
                <Table.Td>{fmtDateTime(t.created_at)}</Table.Td>
                <Table.Td>{t.last_used_at ? fromNow(t.last_used_at) : "never"}</Table.Td>
                <Table.Td>
                  {t.revoked_at ? (
                    <Badge color="gray">revoked</Badge>
                  ) : (
                    <Button size="xs" variant="subtle" color="red" onClick={() => revoke.mutate(t.id)}>
                      Revoke
                    </Button>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : (
        <Empty>No tokens</Empty>
      )}
      <Modal opened={!!created} onClose={() => setCreated(null)} title="Token created">
        <Stack>
          <Alert color="yellow">Copy this token now. It won't be shown again.</Alert>
          <Group wrap="nowrap">
            <Code block style={{ flex: 1, wordBreak: "break-all" }}>
              {created?.token}
            </Code>
            <CopyButton value={created?.token ?? ""}>
              {({ copied, copy }) => (
                <ActionIcon variant="light" onClick={copy} color={copied ? "green" : undefined}>
                  {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                </ActionIcon>
              )}
            </CopyButton>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

const ENTITIES = [
  { value: "plant", label: "Plant" },
  { value: "instance", label: "My plant (instance)" },
  { value: "area", label: "Area" },
  { value: "spot", label: "Spot" },
];
const TYPES = [
  { value: "text", label: "Text" },
  { value: "number", label: "Number" },
  { value: "bool", label: "Yes / no" },
  { value: "date", label: "Date" },
  { value: "select", label: "Choice list" },
];

function CustomFields({ isAdmin }: { isAdmin: boolean }) {
  const [editing, setEditing] = useState<S["CustomFieldRead"] | "new" | null>(null);
  const { data: fields = [] } = useQuery({ queryKey: ["custom-fields"], queryFn: () => unwrap(api.GET("/api/v1/custom-fields")) });
  const remove = useApiMutation(
    (id: number) => unwrap(api.DELETE("/api/v1/custom-fields/{field_id}", { params: { path: { field_id: id } } })),
    { invalidate: [["custom-fields"]], success: "Field deleted" },
  );
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Add your own fields to plants, instances, areas and spots. They appear on the edit forms.
      </Text>
      {isAdmin && (
        <Group>
          <Button onClick={() => setEditing("new")}>Add field</Button>
        </Group>
      )}
      {fields.length ? (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Applies to</Table.Th>
              <Table.Th>Label</Table.Th>
              <Table.Th>Key</Table.Th>
              <Table.Th>Type</Table.Th>
              <Table.Th></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {fields.map((f) => (
              <Table.Tr key={f.id}>
                <Table.Td>{ENTITIES.find((e) => e.value === f.entity)?.label}</Table.Td>
                <Table.Td>{f.label}</Table.Td>
                <Table.Td>
                  <Code>{f.key}</Code>
                </Table.Td>
                <Table.Td>
                  {TYPES.find((t) => t.value === f.type)?.label}
                  {f.options?.length ? ` (${f.options.join(", ")})` : ""}
                </Table.Td>
                <Table.Td>
                  {isAdmin && (
                    <Group gap={4} justify="flex-end">
                      <ActionIcon variant="subtle" onClick={() => setEditing(f)}>
                        <IconPencil size={16} />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        onClick={() =>
                          modals.openConfirmModal({
                            title: `Delete “${f.label}”?`,
                            children: <Text size="sm">Existing values are kept in the database but no longer shown.</Text>,
                            labels: { confirm: "Delete", cancel: "Cancel" },
                            confirmProps: { color: "red" },
                            onConfirm: () => remove.mutate(f.id),
                          })
                        }
                      >
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Group>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : (
        <Empty>No custom fields</Empty>
      )}
      <Modal opened={!!editing} onClose={() => setEditing(null)} title={editing === "new" ? "New field" : "Edit field"}>
        {editing && <FieldForm field={editing === "new" ? undefined : editing} onDone={() => setEditing(null)} />}
      </Modal>
    </Stack>
  );
}

function FieldForm({ field, onDone }: { field?: S["CustomFieldRead"]; onDone: () => void }) {
  const form = useForm({
    initialValues: {
      entity: field?.entity ?? "plant",
      label: field?.label ?? "",
      key: field?.key ?? "",
      type: field?.type ?? "text",
      options: field?.options ?? [],
      help_text: field?.help_text ?? "",
      sort_order: field?.sort_order ?? 0,
    },
    validate: {
      label: (v: string) => (v.trim() ? null : "Required"),
      key: (v: string) => (/^[a-z][a-z0-9_]*$/.test(v) ? null : "Lowercase letters, numbers and _"),
      options: (v: string[], values: { type: string }) => (values.type === "select" && !v.length ? "Add at least one option" : null),
    },
  });
  const save = useApiMutation(
    (v: typeof form.values) =>
      field
        ? unwrap(
            api.PATCH("/api/v1/custom-fields/{field_id}", {
              params: { path: { field_id: field.id } },
              body: { label: v.label, options: v.type === "select" ? v.options : null, help_text: v.help_text || null, sort_order: v.sort_order },
            }),
          )
        : unwrap(
            api.POST("/api/v1/custom-fields", {
              body: {
                entity: v.entity as S["CustomFieldCreate"]["entity"],
                key: v.key,
                label: v.label,
                type: v.type as S["CustomFieldCreate"]["type"],
                options: v.type === "select" ? v.options : null,
                help_text: v.help_text || null,
                sort_order: v.sort_order,
              },
            }),
          ),
    { invalidate: [["custom-fields"]], success: "Saved", onSuccess: onDone },
  );
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        <Select label="Applies to" data={ENTITIES} disabled={!!field} allowDeselect={false} {...form.getInputProps("entity")} />
        <TextInput
          label="Label"
          {...form.getInputProps("label")}
          onChange={(e) => {
            const value = e.currentTarget.value;
            form.setFieldValue("label", value);
            if (!field) form.setFieldValue("key", value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/^(\d)/, "f_$1"));
          }}
        />
        <TextInput label="Key" description="Used in the API" disabled={!!field} {...form.getInputProps("key")} />
        <Select label="Type" data={TYPES} disabled={!!field} allowDeselect={false} {...form.getInputProps("type")} />
        {form.values.type === "select" && <TagsInput label="Options" placeholder="Type and press Enter" {...form.getInputProps("options")} />}
        <TextInput label="Help text" {...form.getInputProps("help_text")} />
        <NumberInput label="Sort order" {...form.getInputProps("sort_order")} />
        <Group justify="flex-end">
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function Users({ currentId }: { currentId: number }) {
  const [adding, setAdding] = useState(false);
  const { data: users = [] } = useQuery({ queryKey: ["users"], queryFn: () => unwrap(api.GET("/api/v1/users")) });
  const update = useApiMutation(
    ({ id, body }: { id: number; body: S["UserUpdate"] }) =>
      unwrap(api.PATCH("/api/v1/users/{user_id}", { params: { path: { user_id: id } }, body })),
    { invalidate: [["users"]], success: "Saved" },
  );
  const remove = useApiMutation(
    (id: number) => unwrap(api.DELETE("/api/v1/users/{user_id}", { params: { path: { user_id: id } } })),
    { invalidate: [["users"]], success: "User deleted" },
  );
  const form = useForm({
    initialValues: { username: "", display_name: "", password: "", is_admin: false },
    validate: { username: (v: string) => (v.trim() ? null : "Required"), password: (v: string) => (v.length >= 8 ? null : "At least 8 characters") },
  });
  const create = useApiMutation(
    (v: typeof form.values) => unwrap(api.POST("/api/v1/users", { body: { ...v, display_name: v.display_name || null } })),
    {
      invalidate: [["users"]],
      success: "User created",
      onSuccess: () => {
        form.reset();
        setAdding(false);
      },
    },
  );
  return (
    <Stack>
      <Group>
        <Button onClick={() => setAdding(true)}>Add user</Button>
      </Group>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Username</Table.Th>
            <Table.Th>Name</Table.Th>
            <Table.Th>Admin</Table.Th>
            <Table.Th>Active</Table.Th>
            <Table.Th></Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {users.map((u) => (
            <Table.Tr key={u.id}>
              <Table.Td>{u.username}</Table.Td>
              <Table.Td>{u.display_name}</Table.Td>
              <Table.Td>
                <Checkbox checked={u.is_admin} disabled={u.id === currentId} onChange={(e) => update.mutate({ id: u.id, body: { is_admin: e.currentTarget.checked } })} />
              </Table.Td>
              <Table.Td>
                <Checkbox checked={u.is_active} disabled={u.id === currentId} onChange={(e) => update.mutate({ id: u.id, body: { is_active: e.currentTarget.checked } })} />
              </Table.Td>
              <Table.Td>
                {u.id !== currentId && (
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    onClick={() =>
                      modals.openConfirmModal({
                        title: `Delete ${u.username}?`,
                        labels: { confirm: "Delete", cancel: "Cancel" },
                        confirmProps: { color: "red" },
                        onConfirm: () => remove.mutate(u.id),
                      })
                    }
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Modal opened={adding} onClose={() => setAdding(false)} title="New user">
        <form onSubmit={form.onSubmit((v) => create.mutate(v))}>
          <Stack>
            <TextInput label="Username" {...form.getInputProps("username")} />
            <TextInput label="Display name" {...form.getInputProps("display_name")} />
            <PasswordInput label="Password" autoComplete="new-password" {...form.getInputProps("password")} />
            <Checkbox label="Admin" {...form.getInputProps("is_admin", { type: "checkbox" })} />
            <Group justify="flex-end">
              <Button type="submit" loading={create.isPending}>
                Create
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}

function Integrations({ isAdmin }: { isAdmin: boolean }) {
  return (
    <Stack maw={640}>
      <HomeAssistantSettings isAdmin={isAdmin} />
      <OpenPlantbookSettings isAdmin={isAdmin} />
      <Text fw={600} mt="md">
        REST API
      </Text>
      <Text size="sm">
        Interactive documentation is at{" "}
        <Anchor href={`${BASE_PATH}api/docs`} target="_blank">
          /api/docs
        </Anchor>{" "}
        and the OpenAPI spec at{" "}
        <Anchor href={`${BASE_PATH}api/openapi.json`} target="_blank">
          /api/openapi.json
        </Anchor>
        .
      </Text>
    </Stack>
  );
}

const SOURCE_LABELS = { settings: "saved here", environment: "from environment variables", supervisor: "via the add-on supervisor" };

function HomeAssistantSettings({ isAdmin }: { isAdmin: boolean }) {
  const { data: status } = useHAStatus();
  if (!status) return null;
  return (
    <Stack gap="xs" mb="md">
      <Group>
        <Text fw={600}>Home Assistant</Text>
        <Badge color={!status.configured ? "gray" : status.last_sync_error ? "red" : "green"}>
          {!status.configured ? "Not connected" : status.last_sync_error ? "Error" : "Connected"}
        </Badge>
        {status.issue_count > 0 && <Badge color="orange">{status.issue_count} device issue{status.issue_count === 1 ? "" : "s"}</Badge>}
      </Group>
      <Text size="sm" c="dimmed">
        Assign Home Assistant irrigation zones and plant monitors to spots. Plantasaurus lists devices that carry the labels below,
        and checks {status.sync_interval_seconds > 0 ? `every ${Math.round(status.sync_interval_seconds / 60)} min` : "on demand"} that
        assigned devices still exist.
      </Text>
      {status.configured && (
        <Text size="sm">
          {status.url} ({SOURCE_LABELS[status.source!]}) · last checked {status.last_sync_at ? fromNow(status.last_sync_at) : "never"}
        </Text>
      )}
      {status.last_sync_error && <Alert color="red">{status.last_sync_error}</Alert>}
      {isAdmin ? (
        <HAConfigForm status={status} />
      ) : (
        <Text size="sm" c="dimmed">
          Ask an admin to change the connection.
        </Text>
      )}
    </Stack>
  );
}

function HAConfigForm({ status }: { status: S["HAStatus"] }) {
  const fromEnv = status.source === "environment" || status.source === "supervisor";
  const form = useForm({
    initialValues: {
      url: status.source === "settings" ? (status.url ?? "") : "",
      token: "",
      irrigation_label: status.irrigation_label,
      monitor_label: status.monitor_label,
      notify_in_ha: status.notify_in_ha,
    },
    validate: {
      url: (v: string) => (!v || /^https?:\/\//.test(v) ? null : "Must start with http:// or https://"),
      irrigation_label: (v: string) => (v.trim() ? null : "Required"),
      monitor_label: (v: string) => (v.trim() ? null : "Required"),
    },
  });
  const save = useApiMutation(
    (v: typeof form.values) => unwrap(api.PUT("/api/v1/homeassistant/config", { body: { ...v, url: v.url || null, token: v.token || null } })),
    { invalidate: INVALIDATE_HA, success: "Home Assistant settings saved", onSuccess: () => form.setFieldValue("token", "") },
  );
  const sync = useApiMutation(() => unwrap(api.POST("/api/v1/homeassistant/sync")), {
    invalidate: INVALIDATE_HA,
    success: (s) => (s.issue_count ? `Checked: ${s.issue_count} device issue(s)` : "Checked: all devices present"),
  });
  const disconnect = () =>
    modals.openConfirmModal({
      title: "Disconnect Home Assistant?",
      children: <Text size="sm">Device assignments on spots are kept, but they won't be checked until you reconnect.</Text>,
      labels: { confirm: "Disconnect", cancel: "Cancel" },
      confirmProps: { color: "red" },
      onConfirm: () => save.mutate({ ...form.values, url: "", token: "" }),
    });
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        {fromEnv && !form.values.url && (
          <Text size="sm" c="dimmed">
            Connected {SOURCE_LABELS[status.source!]}. Enter a URL and token to override it.
          </Text>
        )}
        <TextInput label="Home Assistant URL" placeholder="http://homeassistant.local:8123" {...form.getInputProps("url")} />
        <PasswordInput
          label="Long-lived access token"
          description="Create one in HA under your profile → Security. It must belong to an administrator."
          placeholder={status.source === "settings" && status.token_set ? "Saved; leave blank to keep" : undefined}
          autoComplete="off"
          {...form.getInputProps("token")}
        />
        <SimpleGrid cols={2}>
          <TextInput label="Irrigation zone label" {...form.getInputProps("irrigation_label")} />
          <TextInput label="Plant monitor label" {...form.getInputProps("monitor_label")} />
        </SimpleGrid>
        <Switch
          label="Also raise a Home Assistant notification when assigned devices go missing"
          {...form.getInputProps("notify_in_ha", { type: "checkbox" })}
        />
        <Group>
          <Button type="submit" loading={save.isPending}>
            Test & save
          </Button>
          {status.configured && (
            <Button variant="default" loading={sync.isPending} onClick={() => sync.mutate(undefined)}>
              Check devices now
            </Button>
          )}
          {status.source === "settings" && (
            <Button variant="subtle" color="red" onClick={disconnect}>
              Disconnect
            </Button>
          )}
        </Group>
      </Stack>
    </form>
  );
}

const OPB_SOURCE_LABELS = { settings: "saved here", environment: "from environment variables" };

function OpenPlantbookSettings({ isAdmin }: { isAdmin: boolean }) {
  const { data: status } = useOPBStatus();
  if (!status) return null;
  return (
    <Stack gap="xs" mb="md">
      <Group>
        <Text fw={600}>Open Plantbook</Text>
        <Badge color={status.configured ? "green" : "gray"}>{status.configured ? "Connected" : "Not configured"}</Badge>
      </Group>
      <Text size="sm" c="dimmed">
        Search{" "}
        <Anchor href="https://open.plantbook.io" target="_blank" size="sm">
          open.plantbook.io
        </Anchor>{" "}
        when adding plants and import their care ranges and image. Sign up there and create API credentials under API
        credentials.
      </Text>
      {status.configured && (
        <Text size="sm">
          Client ID <Code>{status.client_id}</Code> ({OPB_SOURCE_LABELS[status.source!]})
        </Text>
      )}
      {isAdmin ? (
        <OPBConfigForm status={status} />
      ) : (
        <Text size="sm" c="dimmed">
          Ask an admin to change the credentials.
        </Text>
      )}
    </Stack>
  );
}

function OPBConfigForm({ status }: { status: S["OPBStatus"] }) {
  const saved = status.source === "settings";
  const form = useForm({
    initialValues: { client_id: saved ? (status.client_id ?? "") : "", client_secret: "" },
    validate: {
      client_secret: (v: string, values: { client_id: string }) =>
        values.client_id.trim() && !v && !(saved && values.client_id.trim() === status.client_id) ? "Required" : null,
    },
  });
  const save = useApiMutation(
    (v: typeof form.values) =>
      unwrap(api.PUT("/api/v1/openplantbook/config", { body: { client_id: v.client_id.trim() || null, client_secret: v.client_secret || null } })),
    { invalidate: [["opb"]], success: "Open Plantbook settings saved", onSuccess: () => form.setFieldValue("client_secret", "") },
  );
  const disconnect = () =>
    modals.openConfirmModal({
      title: "Remove Open Plantbook credentials?",
      children: (
        <Text size="sm">
          Imported plants are kept.{" "}
          {status.source === "settings" ? "Credentials from environment variables, if set, will be used instead." : ""}
        </Text>
      ),
      labels: { confirm: "Remove", cancel: "Cancel" },
      confirmProps: { color: "red" },
      onConfirm: () => save.mutate({ client_id: "", client_secret: "" }),
    });
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        {status.source === "environment" && !form.values.client_id && (
          <Text size="sm" c="dimmed">
            Connected {OPB_SOURCE_LABELS.environment}. Enter a client ID and secret to override them.
          </Text>
        )}
        <SimpleGrid cols={2}>
          <TextInput label="Client ID" autoComplete="off" {...form.getInputProps("client_id")} />
          <PasswordInput
            label="Client secret"
            placeholder={saved && form.values.client_id.trim() === status.client_id ? "Saved; leave blank to keep" : undefined}
            autoComplete="off"
            {...form.getInputProps("client_secret")}
          />
        </SimpleGrid>
        <Group>
          <Button type="submit" loading={save.isPending}>
            Test & save
          </Button>
          {saved && (
            <Button variant="subtle" color="red" onClick={disconnect}>
              Remove
            </Button>
          )}
        </Group>
      </Stack>
    </form>
  );
}
