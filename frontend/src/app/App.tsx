import { Suspense } from "react";
import { BrowserRouter, Routes, Route, Outlet } from "react-router-dom";
import { Toaster } from "sonner";
import TopNavigation from "@/components/layout/TopNavigation";
import routes from "./routes";
import NotFound from "@/pages/NotFound";
import TaskRouteFallback from "@/components/performance/TaskRouteFallback";

function AppLayout() {
    return (
        <div className="flex min-h-screen flex-col gradient-bg">
            <TopNavigation />
            <main className="flex-1">
                <Outlet />
            </main>
        </div>
    );
}

function App() {
    return (
        <BrowserRouter>
            <Toaster position="top-right" />
            <Suspense fallback={<TaskRouteFallback />}>
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
            </Suspense>
        </BrowserRouter>
    );
}

export default App;
