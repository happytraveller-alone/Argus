export interface RefreshOptions {
    silent?: boolean;
}

export async function runWithRefreshMode<T>(
    request: () => Promise<T>,
    options?: RefreshOptions & {
        setLoading?: (value: boolean) => void;
    },
): Promise<T> {
    const silent = options?.silent ?? false;
    const setLoading = options?.setLoading;

    if (!silent && setLoading) {
        setLoading(true);
    }

    try {
        return await request();
    } finally {
        if (!silent && setLoading) {
            setLoading(false);
        }
    }
}
