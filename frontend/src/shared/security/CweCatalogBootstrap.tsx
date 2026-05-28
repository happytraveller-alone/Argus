import { useEffect } from "react";
import { fetchCweCatalog } from "@/shared/api/cweCatalog";
import { hydrateCweCatalog } from "@/shared/security/cweCatalog";

export function CweCatalogBootstrap() {
  useEffect(() => {
    let cancelled = false;
    void fetchCweCatalog({ limit: 1000 })
      .then((payload) => {
        if (!cancelled) {
          hydrateCweCatalog(payload);
        }
      })
      .catch(() => {
        // Keep the bundled static catalog when the backend DB/API is unavailable.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}
