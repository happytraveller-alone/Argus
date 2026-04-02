import axios from "axios";
import { getApiBaseUrl } from "./apiBase";

export const apiClient = axios.create({
    baseURL: getApiBaseUrl(),
    headers: {
        "Content-Type": "application/json",
    },
    maxRedirects: 5,
});
