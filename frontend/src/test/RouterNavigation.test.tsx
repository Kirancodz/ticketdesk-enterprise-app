import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Outlet, useParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { RoleType } from "../types";

const auth = vi.hoisted(() => ({
  user: null as { role: RoleType; must_change_password: boolean } | null,
  login: vi.fn(),
}));

vi.mock("../contexts/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    user: auth.user,
    login: auth.login,
    isLoading: false,
    isAuthenticated: auth.user !== null,
  }),
}));

vi.mock("../layouts/AppLayout", () => ({
  AppLayout: () => <main aria-label="Workspace"><Outlet /></main>,
}));

vi.mock("../pages/DashboardPage", () => ({ DashboardPage: () => <h1>Workspace dashboard</h1> }));
vi.mock("../pages/UserManagementPage", () => ({
  UserManagementPage: () => <h1>Administrator users</h1>,
}));
vi.mock("../pages/TicketDetailPage", () => ({
  TicketDetailPage: () => <h1>Ticket {useParams().ticketId}</h1>,
}));

function startAt(pathname: string, state: unknown = null) {
  window.history.replaceState({ usr: state, key: "test", idx: 0 }, "", pathname);
  return render(<App />);
}

async function signIn() {
  await screen.findByText("Sign in to your workspace");
  fireEvent.change(screen.getByLabelText("Corporate Email"), {
    target: { value: "employee@example.com" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "fixture-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign In to TicketDesk" }));
}

beforeEach(() => {
  auth.user = null;
  auth.login.mockReset().mockImplementation(async () => {
    auth.user = { role: "employee", must_change_password: false };
    return auth.user;
  });
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

describe("BrowserRouter navigation", () => {
  it("returns an authenticated visitor to the protected ticket and restores the nested route on remount", async () => {
    const path = "/tickets/TKT-2026-0042";
    const app = startAt(path);
    await screen.findByText("Sign in to your workspace");
    expect(window.location.pathname).toBe("/login");
    expect(window.history.state.usr.from.pathname).toBe(path);

    await signIn();
    expect(await screen.findByRole("heading", { name: "Ticket TKT-2026-0042" })).toBeInTheDocument();
    expect(window.location.pathname).toBe(path);

    app.unmount();
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Ticket TKT-2026-0042" })).toBeInTheDocument();
    expect(screen.getByRole("main", { name: "Workspace" })).toBeInTheDocument();
  });

  it.each([
    ["absolute URL", "https://external.example/"],
    ["protocol-relative URL", "//external.example/"],
    ["backslash path", "/\\external.example/"],
    ["control characters", "/\n/external.example/"],
    ["malformed state", 42],
  ])("uses the dashboard when the post-login return is an untrusted %s", async (_label, pathname) => {
    startAt("/login", { from: { pathname } });
    await signIn();
    expect(await screen.findByRole("heading", { name: "Workspace dashboard" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/dashboard");
  });

  it.each(["employee", "agent"] as const)("redirects a signed-in %s away from the administrator route", async (role) => {
    auth.user = { role, must_change_password: false };
    startAt("/admin/users");
    expect(await screen.findByRole("heading", { name: "Workspace dashboard" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Administrator users" })).not.toBeInTheDocument();
  });

  it("renders the administrator nested route for an administrator", async () => {
    auth.user = { role: "admin", must_change_password: false };
    startAt("/admin/users");
    expect(await screen.findByRole("heading", { name: "Administrator users" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/admin/users");
  });

  it("routes an unknown authenticated path to the dashboard", async () => {
    auth.user = { role: "employee", must_change_password: false };
    startAt("/unknown-route");
    expect(await screen.findByRole("heading", { name: "Workspace dashboard" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/dashboard");
  });
});
