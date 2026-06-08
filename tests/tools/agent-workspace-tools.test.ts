import { describe, it, expect } from '@jest/globals';
import { ToolRegistry } from '../../src/tool-registry.js';

type RecordedCall = { method: string; path: string; body?: Record<string, unknown> };

function makeRecordingClient() {
  const calls: RecordedCall[] = [];
  const client = {
    getConfig: () => ({
      accessToken: 'test',
      baseUrl: 'https://test.leadconnectorhq.com',
      version: '2021-07-28',
      locationId: 'loc_123',
    }),
    makeRequest: async (method: string, path: string, body?: Record<string, unknown>) => {
      calls.push({ method, path, body });
      return { success: true, data: {} };
    },
  };
  return { client, calls };
}

describe('crm_find_unworked_leads read plan', () => {
  it('searches contacts via POST with a body and bounds form submissions with a numeric limit', async () => {
    const { client, calls } = makeRecordingClient();
    const registry = new ToolRegistry(client as any);

    const result = await registry.callTool('crm_find_unworked_leads', {});
    expect(result).toBeDefined();

    const contactSearch = calls.find((call) => call.path === '/contacts/search');
    expect(contactSearch).toBeDefined();
    // GHL's contact search endpoint is POST, not GET.
    expect(contactSearch?.method).toBe('POST');
    expect(contactSearch?.body).toMatchObject({ locationId: 'loc_123', pageLimit: 20 });

    const formSubmissions = calls.find((call) => call.path.startsWith('/forms/submissions'));
    expect(formSubmissions).toBeDefined();
    expect(formSubmissions?.method).toBe('GET');
    // GHL rejects the request unless limit is a number <= 100.
    expect(formSubmissions?.path).toContain('limit=20');
  });
});
