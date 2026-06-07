/**
 * Multi-account resolver
 *
 * A single deployed MCP server can serve more than one GoHighLevel sub-account
 * (location). Because Claude/ChatGPT connectors only let you enter a URL — not
 * custom headers — the account has to be selectable from the URL itself:
 *
 *   https://<host>/mcp              -> default account (GHL_API_KEY / GHL_LOCATION_ID)
 *   https://<host>/mcp/command      -> the "command" account
 *   https://<host>/mcp?account=cmd  -> same, via query string
 *
 * Accounts are configured with env vars (see .env.example):
 *
 *   GHL_API_KEY / GHL_LOCATION_ID            -> the default account
 *   GHL_DEFAULT_ACCOUNT=frontline            -> optional friendly name for the default
 *   GHL_ACCOUNTS={"command":{"apiKey":"..","locationId":".."}}
 *   GHL_API_KEY_COMMAND / GHL_LOCATION_ID_COMMAND   -> flat per-account vars
 */

import { GHLConfig } from './types/ghl-types.js';

export interface AccountDef {
  key: string;
  label: string;
  config: GHLConfig;
  isDefault: boolean;
}

function normalizeKey(key: string): string {
  return key.trim().toLowerCase().replace(/[\s-]+/g, '_');
}

export class AccountResolver {
  private accounts = new Map<string, AccountDef>();
  private defaultKey: string;

  constructor(private base: GHLConfig, env: NodeJS.ProcessEnv = process.env) {
    this.defaultKey = normalizeKey(env.GHL_DEFAULT_ACCOUNT || 'default');

    // 1. Register the default account from the primary env vars.
    this.register({
      key: this.defaultKey,
      label: env.GHL_DEFAULT_ACCOUNT || 'default',
      config: { ...base },
      isDefault: true,
    });

    // 2. Register accounts from the GHL_ACCOUNTS JSON map.
    this.loadJsonAccounts(env);

    // 3. Register accounts from flat GHL_API_KEY_<NAME> / GHL_LOCATION_ID_<NAME> vars.
    this.loadFlatAccounts(env);
  }

  private register(def: AccountDef): void {
    this.accounts.set(normalizeKey(def.key), def);
  }

  private loadJsonAccounts(env: NodeJS.ProcessEnv): void {
    const raw = env.GHL_ACCOUNTS;
    if (!raw) return;
    let parsed: Record<string, any>;
    try {
      parsed = JSON.parse(raw);
    } catch (err: any) {
      throw new Error(`GHL_ACCOUNTS is not valid JSON: ${err.message}`);
    }
    for (const [key, value] of Object.entries(parsed)) {
      const apiKey = value.apiKey ?? value.api_key ?? value.accessToken ?? value.access_token;
      const locationId = value.locationId ?? value.location_id;
      if (!apiKey || !locationId) {
        throw new Error(`GHL_ACCOUNTS["${key}"] needs both apiKey and locationId`);
      }
      this.register({
        key,
        label: value.label || key,
        isDefault: false,
        config: {
          accessToken: apiKey,
          locationId,
          baseUrl: value.baseUrl ?? value.base_url ?? this.base.baseUrl,
          version: value.version ?? this.base.version,
        },
      });
    }
  }

  private loadFlatAccounts(env: NodeJS.ProcessEnv): void {
    for (const name of Object.keys(env)) {
      const match = name.match(/^GHL_API_KEY_(.+)$/);
      if (!match) continue;
      const suffix = match[1];
      const apiKey = env[name];
      const locationId = env[`GHL_LOCATION_ID_${suffix}`];
      if (!apiKey || !locationId) continue;
      const key = normalizeKey(suffix);
      // Do not let flat vars clobber an explicit JSON-defined account.
      if (this.accounts.has(key) && !this.accounts.get(key)!.isDefault) continue;
      this.register({
        key,
        label: suffix.toLowerCase(),
        isDefault: false,
        config: {
          accessToken: apiKey,
          locationId,
          baseUrl: env[`GHL_BASE_URL_${suffix}`] || this.base.baseUrl,
          version: env[`GHL_API_VERSION_${suffix}`] || this.base.version,
        },
      });
    }
  }

  /**
   * Resolve a requested account key to a GHLConfig.
   * An empty/missing key returns the default account.
   * An unknown key throws with the list of valid keys.
   */
  resolve(requested?: string | null): GHLConfig {
    if (!requested || !requested.trim()) {
      return this.accounts.get(this.defaultKey)!.config;
    }
    const key = normalizeKey(requested);
    const def = this.accounts.get(key);
    if (!def) {
      throw new Error(
        `Unknown GHL account "${requested}". Configured accounts: ${this.listKeys().join(', ')}`
      );
    }
    return def.config;
  }

  has(requested?: string | null): boolean {
    if (!requested || !requested.trim()) return true;
    return this.accounts.has(normalizeKey(requested));
  }

  listKeys(): string[] {
    return [...this.accounts.keys()];
  }

  /** Public summary safe to expose over HTTP (no secrets). */
  list(): Array<{ key: string; label: string; locationId: string; default: boolean }> {
    return [...this.accounts.values()].map((a) => ({
      key: a.key,
      label: a.label,
      locationId: a.config.locationId,
      default: a.isDefault,
    }));
  }

  /** Number of distinct accounts configured. */
  get size(): number {
    return this.accounts.size;
  }
}
