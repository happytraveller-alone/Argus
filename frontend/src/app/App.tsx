import { useState } from "react";
import { BrowserRouter, Routes, Route, Outlet } from "react-router-dom";
import { Toaster } from "sonner";
import Sidebar from "@/components/layout/Sidebar";
import routes from "./routes";
import NotFound from "@/pages/NotFound";

function AppLayout() {
    const [collapsed, setCollapsed] = useState(false);

    return (
        <div className="min-h-screen gradient-bg">
            <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} />
            <main
                className={`transition-all duration-300 min-h-screen ${
                    collapsed ? "md:ml-20" : "md:ml-64"
                }`}
            >
                <Outlet />
            </main>
        </div>
    );
}

function App() {
    return (
        <BrowserRouter>
            <Toaster position="top-right" />
            <Routes>
                <Route element={<AppLayout />}>
                    {routes.map((route) => (
                        <Route
                            key={route.path}
                            path={route.path}
                            element={route.element}
                        />
                    ))}
                </Route>

                <Route path="*" element={<NotFound />} />
            </Routes>
        </BrowserRouter>
    );
}

export default App;
