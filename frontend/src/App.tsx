import { AppShell, Badge, Burger, Center, Group, Loader, Menu, NavLink, Text, Title, UnstyledButton } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconDashboard,
  IconLeaf,
  IconLogout,
  IconMapPin,
  IconPlant2,
  IconSettings,
  IconUser,
} from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api/client";
import { useAuthStatus, useHAStatus } from "./lib/queries";
import Dashboard from "./pages/Dashboard";
import InstanceDetail from "./pages/InstanceDetail";
import Instances from "./pages/Instances";
import Locations from "./pages/Locations";
import Login from "./pages/Login";
import PlantDetail from "./pages/PlantDetail";
import Plants from "./pages/Plants";
import Settings from "./pages/Settings";
import SpotDetail from "./pages/SpotDetail";

const NAV = [
  { to: "/", label: "Dashboard", icon: IconDashboard },
  { to: "/plants", label: "Plants", icon: IconLeaf },
  { to: "/instances", label: "My plants", icon: IconPlant2 },
  { to: "/locations", label: "Locations", icon: IconMapPin },
  { to: "/settings", label: "Settings", icon: IconSettings },
];

export default function App() {
  const { data: auth, isLoading } = useAuthStatus();
  if (isLoading || !auth) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  }
  if (auth.setup_required || !auth.user) return <Login setup={auth.setup_required} />;
  return <Shell username={auth.user.display_name ?? auth.user.username} ingress={auth.ingress} />;
}

function Shell({ username, ingress }: { username: string; ingress: boolean }) {
  const [opened, { toggle, close }] = useDisclosure();
  const location = useLocation();
  const qc = useQueryClient();
  const { data: ha } = useHAStatus();
  const issueCount = ha?.issue_count ?? 0;

  const logout = async () => {
    await api.POST("/api/v1/auth/logout");
    qc.clear();
    await qc.invalidateQueries({ queryKey: ["auth"] });
  };

  const isActive = (to: string) => (to === "/" ? location.pathname === "/" : location.pathname.startsWith(to));

  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 220, breakpoint: "sm", collapsed: { mobile: !opened } }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="xs">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <IconLeaf color="var(--mantine-color-green-6)" />
            <Title order={3}>Plantasaurus</Title>
          </Group>
          <Menu position="bottom-end">
            <Menu.Target>
              <UnstyledButton>
                <Group gap={6}>
                  <IconUser size={18} />
                  <Text size="sm">{username}</Text>
                </Group>
              </UnstyledButton>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item component={Link} to="/settings" leftSection={<IconSettings size={16} />}>
                Settings
              </Menu.Item>
              {!ingress && (
                <Menu.Item leftSection={<IconLogout size={16} />} onClick={logout}>
                  Log out
                </Menu.Item>
              )}
            </Menu.Dropdown>
          </Menu>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            component={Link}
            to={item.to}
            label={item.label}
            leftSection={<item.icon size={18} />}
            active={isActive(item.to)}
            onClick={close}
            rightSection={
              item.to === "/locations" && issueCount > 0 ? (
                <Badge size="sm" color="orange" circle title="Spots with Home Assistant devices that need attention">
                  {issueCount}
                </Badge>
              ) : undefined
            }
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/plants" element={<Plants />} />
          <Route path="/plants/:id" element={<PlantDetail />} />
          <Route path="/instances" element={<Instances />} />
          <Route path="/instances/:id" element={<InstanceDetail />} />
          <Route path="/locations" element={<Locations />} />
          <Route path="/spots/:id" element={<SpotDetail />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}
