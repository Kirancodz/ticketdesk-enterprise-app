import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CreateTicketPage } from "../pages/CreateTicketPage";
import { LoginPage } from "../pages/LoginPage";
import { apiRequest } from "../services/api";

const { login } = vi.hoisted(() => ({ login: vi.fn() }));
vi.mock("../contexts/AuthContext", () => ({ useAuth: () => ({ login, user: null }) }));
vi.mock("../services/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("../services/api")>(),
  apiRequest: vi.fn(),
}));

function renderTicketForm() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/tickets/new"]}>
        <Routes>
          <Route path="/tickets/new" element={<CreateTicketPage />} />
          <Route path="/tickets/:ticketId" element={<h1>Ticket opened</h1>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(apiRequest).mockImplementation(async (path) => {
    if (path === "/tickets/categories") return [{ id: 11, name: "Network", subcategories: ["VPN"] }];
    if (path === "/users/departments") return [{ id: 22, name: "Operations", code: "OPS" }];
    if (path === "/users/support-teams") return [{ id: 33, name: "Support", code: "IT" }];
    if (path === "/tickets") return { ticket_number: "TKT-2026-0042" };
    return [];
  });
});

afterEach(cleanup);

it("shows the existing login validation messages without submitting invalid credentials", async () => {
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Corporate Email"), { target: { value: "invalid-email" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign In to TicketDesk" }));
  expect(await screen.findByText("Please enter a valid corporate email address")).toBeInTheDocument();
  expect(screen.getByText("Password is required")).toBeInTheDocument();
  expect(login).not.toHaveBeenCalled();
});

it("keeps the required ticket field messages and blocks an invalid submission", async () => {
  renderTicketForm();
  await screen.findByRole("option", { name: "Network" });
  fireEvent.click(screen.getByRole("button", { name: "Submit Support Ticket" }));
  expect(await screen.findByText("Please select an IT category")).toBeInTheDocument();
  expect(screen.getByText("Please select the responsible support team")).toBeInTheDocument();
  expect(screen.getByText("Subject must be at least 5 characters")).toBeInTheDocument();
  expect(vi.mocked(apiRequest).mock.calls.some(([path]) => path === "/tickets")).toBe(false);
});

it.each([["", null], ["22", 22]] as const)(
  "coerces ticket select values and submits department %s correctly",
  async (departmentValue, expectedDepartment) => {
    renderTicketForm();
    const category = await screen.findByRole("option", { name: "Network" });
    const department = await screen.findByRole("option", { name: "Operations (OPS)" });
    await screen.findByRole("option", { name: "Support (IT)" });
    fireEvent.change(category.closest("select")!, { target: { value: "11" } });
    fireEvent.change(department.closest("select")!, { target: { value: departmentValue } });
    fireEvent.change(screen.getByRole("combobox", { name: "Support Team" }), { target: { value: "33" } });
    fireEvent.change(screen.getByPlaceholderText(/GlobalProtect VPN/), { target: { value: "VPN unavailable" } });
    fireEvent.change(screen.getByPlaceholderText(/Include exact error messages/), {
      target: { value: "VPN fails during initial connection." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit Support Ticket" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/tickets", {
      method: "POST",
      body: JSON.stringify({
        subject: "VPN unavailable",
        category_id: 11,
        subcategory: null,
        priority: "medium",
        department_id: expectedDepartment,
        support_team_id: 33,
        affected_service: null,
        description: "VPN fails during initial connection.",
      }),
    }));
    expect(await screen.findByRole("heading", { name: "Ticket opened" })).toBeInTheDocument();
  },
);
