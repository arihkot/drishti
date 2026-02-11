import { useState } from "react";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import MapView from "./components/MapView";
import Toast from "./components/Toast";
import { useStore } from "./stores/useStore";

function App() {
  const sidebarOpen = useStore((s) => s.sidebarOpen);
  const [promptMode, setPromptMode] = useState(false);

  return (
    <div className="flex flex-col w-full h-full">
      <Header />
      <div className="flex flex-1 overflow-hidden pt-14">
        {sidebarOpen && <Sidebar />}
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
