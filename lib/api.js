// Client for the app's own library service (/api/apps/<id>/service/...).
// The token ref always holds the newest app token the shell handed us.

export class ApiError extends Error {
  constructor(kind, message, status) {
    super(message)
    this.kind = kind
    this.status = status
  }
}

export function createApi(appId, tokenRef) {
  async function call(path, { params, method = 'GET', body, signal } = {}) {
    const query = params
      ? new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString()
      : ''
    let response
    try {
      response = await fetch(`/api/apps/${appId}/service/${path}${query ? `?${query}` : ''}`, {
        method,
        signal,
        headers: {
          Authorization: `Bearer ${tokenRef.current}`,
          ...(body ? { 'Content-Type': 'application/json' } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
      })
    } catch (err) {
      if (err?.name === 'AbortError') throw err
      throw new ApiError('offline', 'Could not reach your Möbius. Check the connection and try again.')
    }
    let data = null
    try { data = await response.json() } catch { data = null }
    if (!response.ok) {
      const message = data?.error || data?.detail || `The library answered ${response.status}.`
      const kind = [401, 403, 404, 503].includes(response.status) && !data?.error ? 'no-service' : 'http'
      throw new ApiError(kind, typeof message === 'string' ? message : 'The library could not answer.', response.status)
    }
    return data
  }
  // The Freesound key goes straight from this frame to Möbius's encrypted
  // per-app store. The frame can save or delete it but never read it back;
  // only the app's own service reads it, to call Freesound.
  async function secret(method, name, value) {
    let response
    try {
      response = await fetch(`/api/apps/${appId}/secrets/${name}`, {
        method,
        headers: {
          Authorization: `Bearer ${tokenRef.current}`,
          ...(value !== undefined ? { 'Content-Type': 'application/json' } : {}),
        },
        body: value !== undefined ? JSON.stringify({ value }) : undefined,
      })
    } catch {
      throw new ApiError('offline', 'Could not reach your Möbius. Check the connection and try again.')
    }
    if (!response.ok && !(method === 'DELETE' && response.status === 404)) {
      let detail = ''
      try { detail = (await response.json())?.detail || '' } catch { /* no body */ }
      throw new ApiError('http', typeof detail === 'string' && detail ? detail : `Möbius answered ${response.status}.`, response.status)
    }
  }
  return {
    overview: () => call('overview'),
    sources: () => call('sources'),
    checkFreesound: () => call('sources/freesound/check', { method: 'POST', body: {} }),
    forgetFreesound: () => call('sources/freesound/forget', { method: 'POST', body: {} }),
    saveFreesoundKey: (value) => secret('PUT', 'freesound-key', value),
    removeFreesoundKey: () => secret('DELETE', 'freesound-key'),
    search: (params, signal) => call('search', { params, signal }),
    tools: (params) => call('directory', { params }),
    addTool: (record) => call('directory/add', { method: 'POST', body: record }),
    setToolStatus: (id, change) => call('directory/status', { method: 'POST', body: { id, ...change } }),
    addNote: (id, text, outcome) => call('note', { method: 'POST', body: { id, text, outcome } }),
    removeNote: (id) => call('note/remove', { method: 'POST', body: { id } }),
    asset: (id) => call('asset', { params: { id } }),
    credits: (ids) => call('credits', { params: { ids: ids.join(',') } }),
    setStatus: (id, status, note) => call('asset/status', { method: 'POST', body: { id, status, note } }),
  }
}
