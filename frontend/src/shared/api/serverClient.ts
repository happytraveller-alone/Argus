import axios from "axios";

// API base URL - points to /api/v1 on the backend
const baseURL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export const apiClient = axios.create({
    baseURL,
    headers: {
        "Content-Type": "application/json",
    },
    maxRedirects: 5,
});
