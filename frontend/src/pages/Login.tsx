import { Alert, Button, Center, Paper, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconLeaf } from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";

export default function Login({ setup }: { setup: boolean }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const form = useForm({
    initialValues: { username: "", display_name: "", password: "", confirm: "" },
    validate: {
      username: (v: string) => (v.trim() ? null : "Required"),
      password: (v: string) => (setup && v.length < 8 ? "At least 8 characters" : v ? null : "Required"),
      confirm: (v: string, values: { password: string }) => (setup && v !== values.password ? "Passwords do not match" : null),
    },
  });

  const submit = form.onSubmit(async (values) => {
    setBusy(true);
    setError(null);
    try {
      if (setup) {
        await unwrap(
          api.POST("/api/v1/auth/setup", {
            body: { username: values.username.trim(), password: values.password, display_name: values.display_name || null },
          }),
        );
      } else {
        await unwrap(api.POST("/api/v1/auth/login", { body: { username: values.username.trim(), password: values.password } }));
      }
      await qc.invalidateQueries({ queryKey: ["auth"] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  });

  return (
    <Center mih="100vh" p="md">
      <Paper withBorder shadow="sm" p="xl" w={380}>
        <form onSubmit={submit}>
          <Stack>
            <Stack gap={4} align="center">
              <IconLeaf size={40} color="var(--mantine-color-green-6)" />
              <Title order={2}>Plantasaurus</Title>
              <Text c="dimmed" size="sm">
                {setup ? "Create the first admin account" : "Sign in"}
              </Text>
            </Stack>
            {error && <Alert color="red">{error}</Alert>}
            <TextInput label="Username" autoComplete="username" {...form.getInputProps("username")} />
            {setup && <TextInput label="Display name" {...form.getInputProps("display_name")} />}
            <PasswordInput
              label="Password"
              autoComplete={setup ? "new-password" : "current-password"}
              {...form.getInputProps("password")}
            />
            {setup && <PasswordInput label="Confirm password" {...form.getInputProps("confirm")} />}
            <Button type="submit" loading={busy}>
              {setup ? "Create account" : "Sign in"}
            </Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
