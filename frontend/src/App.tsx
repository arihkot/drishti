import { useState, useCallback } from "react";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import MapView from "./components/MapView";
import Toast from "./components/Toast";
import LoginPage from "./components/LoginPage";
import Dashboard from "./components/Dashboard";
import AreaDashboard from "./components/AreaDashboard";
import { useStore } from "./stores/useStore";
import { type DashboardStats, getMockDashboardStats } from "./data/mockData";

// ─── User type from auth ────────────────────────────────────────────────────
interface AuthUser {
  username: string;
  name: string;
  role: string;
  department: string;
  designation: string;
  employee_id: string;
}

type CurrentView = "dashboard" | "area_dashboard" | "map";

const AUTH_KEY = "drishti_auth_user";

function loadSavedUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function App() {
  const sidebarOpen = useStore((s) => s.sidebarOpen);

  // ── Auth state (persisted to localStorage) ─────────────────────────────────
  const [authUser, setAuthUser] = useState<AuthUser | null>(() => loadSavedUser());

  // ── View routing state ──────────────────────────────────────────────────────
  const [currentView, setCurrentView] = useState<CurrentView>("map");
  const [selectedArea, setSelectedArea] = useState<string>("");

  // ── Dashboard stats (shared so PDF upload persists across navigations) ─────
  const [dashboardStats, setDashboardStats] = useState<DashboardStats>(() =>
    getMockDashboardStats()
  );

  // ── Map prompt mode ─────────────────────────────────────────────────────────
  const [promptMode, setPromptMode] = useState(false);

  // ── Auth handlers ──────────────────────────────────────────────────────────
  const handleLogin = useCallback((user: AuthUser) => {
    localStorage.setItem(AUTH_KEY, JSON.stringify(user));
    setAuthUser(user);
  }, []);

  const handleLogout = useCallback(() => {
    localStorage.removeItem(AUTH_KEY);
    setAuthUser(null);
    setCurrentView("dashboard");
    setPromptMode(false);
  }, []);

  // ── View navigation (resets promptMode when leaving map) ──────────────────
  const navigateTo = useCallback((view: CurrentView) => {
    setPromptMode(false);
    setCurrentView(view);
  }, []);

  // ── Not logged in → Login page ──────────────────────────────────────────────
  if (!authUser) {
    return (
      <>
        <LoginPage onLogin={handleLogin} />
        <Toast />
      </>
    );
  }

  // ── Dashboard view ──────────────────────────────────────────────────────────
  if (currentView === "dashboard") {
    return (
      <>
        <Dashboard
          user={authUser}
          onEnterMap={() => navigateTo("map")}
          onViewArea={(areaName) => {
            setSelectedArea(areaName);
            navigateTo("area_dashboard");
          }}
          onLogout={handleLogout}
          stats={dashboardStats}
          setStats={setDashboardStats}
        />
        <Toast />
      </>
    );
  }

  // ── Area dashboard view ─────────────────────────────────────────────────────
  if (currentView === "area_dashboard") {
    return (
      <>
        <AreaDashboard
          areaName={selectedArea}
          onBack={() => navigateTo("dashboard")}
          onEnterMap={() => navigateTo("map")}
        />
        <Toast />
      </>
    );
  }

  // ── Map view (existing layout) ──────────────────────────────────────────────
  return (
    <div className="flex flex-col w-full h-full overflow-hidden">
      <Header
        onDashboard={() => navigateTo("dashboard")}
        onLogout={handleLogout}
      />
      <div className="flex flex-1 overflow-hidden pt-14">
        {sidebarOpen && (
          <Sidebar
            onViewArea={(areaName) => {
              setSelectedArea(areaName);
              navigateTo("area_dashboard");
            }}
          />
        )}
        <div className="flex-1 relative">
          <MapView promptMode={promptMode} />
          {promptMode && (
            <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-blue-600 text-white px-4 py-2 rounded-full shadow-lg text-sm font-medium z-10">
              Click on the map to detect boundaries at that point.{" "}
              <button
                onClick={() => setPromptMode(false)}
                className="ml-2 underline hover:no-underline"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>
      <Toast />
    </div>
  );
}

export default App;
