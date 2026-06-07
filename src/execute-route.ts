/**
 * REST bridge endpoints:
 *   GET  /tools
 *   POST /execute
 */

import type { Application } from 'express';
import type { Tool } from '@modelcontextprotocol/sdk/types.js';
import type { ToolRegistry } from './tool-registry.js';
import type { GHLConfig } from './types/ghl-types.js';
import type { AccountResolver } from './account-resolver.js';
import { EnhancedGHLClient } from './enhanced-ghl-client.js';
import { ToolRegistry as ToolRegistryClass } from './tool-registry.js';

function toAnthropicTool(tool: Tool) {
  const schema: Record<string, unknown> =
    (tool as any).inputSchema ?? (tool as any).input_schema ?? {};

  return {
    name: tool.name,
    description: tool.description ?? '',
    input_schema: {
      type: 'object' as const,
      properties: (schema.properties as Record<string, unknown>) ?? {},
      ...(Array.isArray(schema.required) ? { required: schema.required as string[] } : {}),
    },
  };
}

export function registerExecuteRoutes(
  app: Application,
  defaultRegistry: ToolRegistry,
  baseConfig?: GHLConfig,
  accounts?: AccountResolver
): void {
  // Cache one registry per resolved location so each account keeps its cache.
  const registryCache = new Map<string, ToolRegistry>();
  const registryForConfig = (cfg: GHLConfig): ToolRegistry => {
    const key = `${cfg.locationId}:${cfg.accessToken}`;
    let r = registryCache.get(key);
    if (!r) {
      r = new ToolRegistryClass(new EnhancedGHLClient(cfg)) as unknown as ToolRegistry;
      registryCache.set(key, r);
    }
    return r;
  };

  app.get('/tools', (_req, res) => {
    try {
      const anthropicTools = defaultRegistry.getAllToolDefinitions().map(toAnthropicTool);
      res.json({ tools: anthropicTools, count: anthropicTools.length });
    } catch (err: any) {
      console.error('[execute-route] GET /tools error:', err.message);
      res.status(500).json({ error: 'Failed to list tools' });
    }
  });

  app.post('/execute', async (req, res) => {
    const body = req.body ?? {};
    const toolName: string | undefined = body.name;
    const toolArgs: Record<string, unknown> = body.arguments ?? {};

    if (!toolName || typeof toolName !== 'string') {
      res.status(400).json({ error: 'Body must include a non-empty string "name"' });
      return;
    }

    const perReqToken = req.headers['x-ghl-access-token'] as string | undefined;
    const perReqLoc = req.headers['x-ghl-location-id'] as string | undefined;
    const accountKey =
      (req.query.account as string | undefined) ||
      (req.headers['x-ghl-account'] as string | undefined);

    let registry = defaultRegistry;
    try {
      if (perReqToken && perReqLoc && baseConfig) {
        registry = registryForConfig({
          ...baseConfig,
          accessToken: perReqToken,
          locationId: perReqLoc,
        });
      } else if (accountKey && accounts) {
        registry = registryForConfig(accounts.resolve(accountKey));
      }
    } catch (err: any) {
      res.status(400).json({ error: err.message });
      return;
    }

    try {
      const result = await registry.callTool(toolName, toolArgs);
      if (result === undefined) {
        res.status(404).json({ error: `Unknown tool: ${toolName}` });
        return;
      }
      res.json({ result });
    } catch (err: any) {
      console.error(`[execute-route] POST /execute tool=${toolName} error:`, err.message);
      res.status(500).json({ error: `Tool execution failed: ${err.message}` });
    }
  });
}
