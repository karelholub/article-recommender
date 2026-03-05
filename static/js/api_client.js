(function initApiClient(globalScope) {
    function getErrorMessage(payload, fallback) {
        if (payload && typeof payload === 'object') {
            return payload.error || payload.message || fallback;
        }
        if (typeof payload === 'string' && payload.trim()) {
            return payload.trim();
        }
        return fallback;
    }

    async function parseResponse(response) {
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            return await response.json();
        }
        return await response.text();
    }

    async function request(path, options = {}) {
        const {
            method = 'GET',
            query = null,
            headers = {},
            body = undefined,
            timeoutMs = 20000,
            signal = undefined
        } = options;

        const url = new URL(path, window.location.origin);
        if (query && typeof query === 'object') {
            Object.entries(query).forEach(([key, value]) => {
                if (value === undefined || value === null || value === '') return;
                url.searchParams.set(key, String(value));
            });
        }

        const controller = signal ? null : new AbortController();
        const timeoutId = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
        try {
            const response = await fetch(url.toString(), {
                method,
                headers,
                body,
                signal: signal || controller.signal
            });
            const payload = await parseResponse(response);
            if (!response.ok) {
                const error = new Error(getErrorMessage(payload, `Request failed (${response.status})`));
                error.status = response.status;
                error.payload = payload;
                throw error;
            }
            return payload;
        } finally {
            if (timeoutId) clearTimeout(timeoutId);
        }
    }

    function withJsonHeaders(headers = {}) {
        return { 'Content-Type': 'application/json', ...headers };
    }

    const apiClient = {
        request,
        get(path, options = {}) {
            return request(path, { ...options, method: 'GET' });
        },
        post(path, jsonBody, options = {}) {
            return request(path, {
                ...options,
                method: 'POST',
                headers: withJsonHeaders(options.headers),
                body: JSON.stringify(jsonBody ?? {})
            });
        },
        put(path, jsonBody, options = {}) {
            return request(path, {
                ...options,
                method: 'PUT',
                headers: withJsonHeaders(options.headers),
                body: JSON.stringify(jsonBody ?? {})
            });
        },
        del(path, options = {}) {
            return request(path, { ...options, method: 'DELETE' });
        }
    };

    globalScope.ApiClient = apiClient;
})(window);
