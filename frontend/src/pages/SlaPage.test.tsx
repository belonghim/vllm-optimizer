import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import SlaPage from "./SlaPage";

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
  vi.stubGlobal("location", { href: "" });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const EMPTY_EVAL = {
  profile: { id: 1, name: "", thresholds: { availability_min: null, p95_latency_max_ms: null, error_rate_max_pct: null, min_tps: null }, created_at: 0 },
  results: [],
  warnings: [],
};

function makeDefaultFetch(overrides?: (url: string, init?: RequestInit) => unknown) {
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (overrides) {
      const result = overrides(url, init);
      if (result !== undefined) return result;
    }
    if (url.includes("/sla/evaluate")) {
      return Promise.resolve({ ok: true, status: 200, json: async () => EMPTY_EVAL });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => [] });
  });
}

describe("SlaPage", () => {
  describe("TC1: form submit does not refresh the page", () => {
    it("window.location.href remains empty after profile creation", async () => {
      const user = userEvent.setup();
      const fetchMock = makeDefaultFetch();
      vi.stubGlobal("fetch", fetchMock);

      render(<SlaPage isActive={true} />);
      await waitFor(() => screen.getByRole("button", { name: "프로필 생성" }));

      await user.type(screen.getByPlaceholderText(/Llama3/), "My SLA");
      await user.type(screen.getByPlaceholderText("99.9"), "99");
      await user.click(screen.getByRole("button", { name: "프로필 생성" }));

      await waitFor(() => {
        const postCall = fetchMock.mock.calls.find(
          ([, init]) => (init as RequestInit)?.method === "POST"
        );
        expect(postCall).toBeDefined();
      });

      expect(window.location.href).toBe("");
    });
  });

  describe("TC2: successful profile creation sends POST with correct body", () => {
    it("POSTs to /api/sla/profiles with name and availability_min", async () => {
      const user = userEvent.setup();
      const fetchMock = makeDefaultFetch((url, init) => {
        if ((init as RequestInit)?.method === "POST") {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({
              id: 1,
              name: "Test Profile",
              thresholds: { availability_min: 99, p95_latency_max_ms: null, error_rate_max_pct: null, min_tps: null },
              created_at: 0,
            }),
          });
        }
      });
      vi.stubGlobal("fetch", fetchMock);

      render(<SlaPage isActive={true} />);
      await waitFor(() => screen.getByRole("button", { name: "프로필 생성" }));

      await user.type(screen.getByPlaceholderText(/Llama3/), "Test Profile");
      await user.type(screen.getByPlaceholderText("99.9"), "99");
      await user.click(screen.getByRole("button", { name: "프로필 생성" }));

      await waitFor(() => {
        const postCall = fetchMock.mock.calls.find(
          ([, init]) => (init as RequestInit)?.method === "POST"
        );
        expect(postCall).toBeDefined();
        const body = JSON.parse((postCall![1] as RequestInit).body as string);
        expect(body.name).toBe("Test Profile");
        expect(body.thresholds.availability_min).toBe(99);
      });
    });
  });

  describe("TC3: client validation when no threshold is provided", () => {
    it("shows error and does not call fetch POST", async () => {
      const user = userEvent.setup();
      const fetchMock = makeDefaultFetch();
      vi.stubGlobal("fetch", fetchMock);

      render(<SlaPage isActive={true} />);
      await waitFor(() => screen.getByRole("button", { name: "프로필 생성" }));

      await user.type(screen.getByPlaceholderText(/Llama3/), "No Thresholds");
      await user.click(screen.getByRole("button", { name: "프로필 생성" }));

      expect(screen.getByRole("alert")).toHaveTextContent("최소 1개의 임계값을 입력해야 합니다.");

      const postCalls = fetchMock.mock.calls.filter(
        ([, init]) => (init as RequestInit)?.method === "POST"
      );
      expect(postCalls).toHaveLength(0);
    });
  });

  describe("TC4: server error shows error message without redirect", () => {
    it("displays SLA 프로필 저장 실패 and location.href stays empty", async () => {
      const user = userEvent.setup();
      const fetchMock = makeDefaultFetch((url, init) => {
        if ((init as RequestInit)?.method === "POST") {
          return Promise.resolve({
            ok: false,
            status: 500,
            json: async () => ({ detail: "Internal error" }),
          });
        }
      });
      vi.stubGlobal("fetch", fetchMock);

      render(<SlaPage isActive={true} />);
      await waitFor(() => screen.getByRole("button", { name: "프로필 생성" }));

      await user.type(screen.getByPlaceholderText(/Llama3/), "Test");
      await user.type(screen.getByPlaceholderText("99.9"), "99");
      await user.click(screen.getByRole("button", { name: "프로필 생성" }));

      await waitFor(() =>
        expect(screen.getByText(/SLA 프로필 저장 실패/)).toBeInTheDocument()
      );
      expect(window.location.href).toBe("");
    });
  });

  describe("TC5: 403 response triggers oauth redirect (documents current behavior)", () => {
    it("sets window.location.href to /oauth/sign_out on 403 — this is what looks like a page refresh", async () => {
      const user = userEvent.setup();
      const fetchMock = makeDefaultFetch((url, init) => {
        if ((init as RequestInit)?.method === "POST") {
          return Promise.resolve({ ok: false, status: 403, json: async () => ({}) });
        }
      });
      vi.stubGlobal("fetch", fetchMock);

      render(<SlaPage isActive={true} />);
      await waitFor(() => screen.getByRole("button", { name: "프로필 생성" }));

      await user.type(screen.getByPlaceholderText(/Llama3/), "Test");
      await user.type(screen.getByPlaceholderText("99.9"), "99");
      await user.click(screen.getByRole("button", { name: "프로필 생성" }));

      await waitFor(() => {
        expect(window.location.href).toBe("/oauth/sign_out");
      });
    });
  });

  describe("TC6: initial profile list loading", () => {
     it("renders empty state messages when no profiles exist", async () => {
       const fetchMock = vi.fn().mockImplementation((url: string) => {
         if (url.includes("/sla/profiles")) {
           return Promise.resolve({ ok: true, status: 200, json: async () => [] });
         }
         return Promise.resolve({ ok: true, status: 200, json: async () => [] });
       });
       vi.stubGlobal("fetch", fetchMock);

      render(<SlaPage isActive={true} />);

      await waitFor(() => {
        const cardEmpty = screen.queryByText("SLA 프로필을 생성하세요");
        const tableEmpty = screen.queryByText("등록된 프로필이 없습니다.");
        expect(cardEmpty || tableEmpty).toBeTruthy();
      });
    });
  });

  describe("TC7: profile deletion", () => {
    it("calls DELETE /api/sla/profiles/:id when user confirms", async () => {
      const user = userEvent.setup();
      vi.stubGlobal("confirm", vi.fn(() => true));

       const profile = {
         id: 42,
         name: "Delete Me",
         thresholds: { availability_min: 99, p95_latency_max_ms: null, error_rate_max_pct: null, min_tps: null },
         created_at: 0,
       };

      const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if ((init as RequestInit)?.method === "DELETE") {
          return Promise.resolve({ ok: true, status: 200, json: async () => ({ deleted: true }) });
        }
        if (url.includes("/sla/evaluate")) {
          return Promise.resolve({
            ok: true, status: 200,
            json: async () => ({ profile, results: [], warnings: [] }),
          });
        }
        if (url.includes("/sla/profiles")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => [profile] });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => [] });
      });
      vi.stubGlobal("fetch", fetchMock);

      render(<SlaPage isActive={true} />);

      await waitFor(() => expect(screen.getAllByText("Delete Me").length).toBeGreaterThan(0));

      const deleteBtn = screen.getByRole("button", { name: "삭제" });
      await user.click(deleteBtn);

      await waitFor(() => {
        const deleteCall = fetchMock.mock.calls.find(
          ([url, init]) =>
            (init as RequestInit)?.method === "DELETE" &&
            (url as string).includes("/sla/profiles/42")
        );
        expect(deleteCall).toBeDefined();
      });
    });
  });
});
