import { describe, it, expect } from '@jest/globals';
import { AccountResolver } from '../src/account-resolver.js';

const base = {
  accessToken: 'FRONTLINE_KEY',
  baseUrl: 'https://services.leadconnectorhq.com',
  version: '2021-07-28',
  locationId: 'loc_frontline',
};

describe('AccountResolver', () => {
  it('resolves the default account when no key is given', () => {
    const r = new AccountResolver(base, {} as NodeJS.ProcessEnv);
    expect(r.resolve().locationId).toBe('loc_frontline');
    expect(r.resolve('').locationId).toBe('loc_frontline');
    expect(r.size).toBe(1);
  });

  it('names the default account via GHL_DEFAULT_ACCOUNT', () => {
    const r = new AccountResolver(base, { GHL_DEFAULT_ACCOUNT: 'frontline' } as any);
    expect(r.resolve('frontline').accessToken).toBe('FRONTLINE_KEY');
    expect(r.list()[0]).toMatchObject({ key: 'frontline', default: true });
  });

  it('loads accounts from the GHL_ACCOUNTS JSON map', () => {
    const r = new AccountResolver(base, {
      GHL_ACCOUNTS: JSON.stringify({
        command: { apiKey: 'CMD_KEY', locationId: 'loc_command', label: 'Connect & Comm' },
      }),
    } as any);
    const cfg = r.resolve('command');
    expect(cfg.accessToken).toBe('CMD_KEY');
    expect(cfg.locationId).toBe('loc_command');
  });

  it('loads accounts from flat GHL_API_KEY_<NAME> vars', () => {
    const r = new AccountResolver(base, {
      GHL_API_KEY_COMMAND: 'CMD_KEY',
      GHL_LOCATION_ID_COMMAND: 'loc_command',
    } as any);
    expect(r.resolve('command').locationId).toBe('loc_command');
  });

  it('treats account keys as case- and separator-insensitive', () => {
    const r = new AccountResolver(base, {
      GHL_ACCOUNTS: JSON.stringify({ 'connect-comm': { apiKey: 'K', locationId: 'loc_cc' } }),
    } as any);
    expect(r.resolve('Connect Comm').locationId).toBe('loc_cc');
    expect(r.resolve('connect_comm').locationId).toBe('loc_cc');
  });

  it('throws a helpful error for an unknown account', () => {
    const r = new AccountResolver(base, { GHL_DEFAULT_ACCOUNT: 'frontline' } as any);
    expect(() => r.resolve('nope')).toThrow(/Unknown GHL account "nope"/);
    expect(() => r.resolve('nope')).toThrow(/frontline/);
  });

  it('rejects malformed GHL_ACCOUNTS JSON', () => {
    expect(() => new AccountResolver(base, { GHL_ACCOUNTS: '{bad json' } as any)).toThrow(
      /GHL_ACCOUNTS is not valid JSON/
    );
  });

  it('never leaks secrets from list()', () => {
    const r = new AccountResolver(base, {
      GHL_ACCOUNTS: JSON.stringify({ command: { apiKey: 'CMD_KEY', locationId: 'loc_command' } }),
    } as any);
    const json = JSON.stringify(r.list());
    expect(json).not.toContain('CMD_KEY');
    expect(json).not.toContain('FRONTLINE_KEY');
  });
});
