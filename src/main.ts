/**
 * GoHighLevel MCP Server
 *
 * Streamable HTTP transport with optional legacy SSE support.
 */

import express from 'express';
import cors from 'cors';
import * as dotenv from 'dotenv';

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';

import { EnhancedGHLClient } from './enhanced-ghl-client.js';
import { ToolRegistry } from './tool-registry.js';
import { GHLConfig } from './types/ghl-types.js';
import { registerExecuteRoutes } from './execute-route.js';
import { AccountResolver } from './account-resolver.js';

dotenv.config();

const LOG_LEVELS = { debug: 0, info: 1, warn: 2, error: 3 } as const;
type LogLevel = keyof typeof LOG_LEVELS;
const MIN_LEVEL: LogLevel = (process.env.LOG_LEVEL as LogLevel) || 'info';

function log(level: LogLevel, msg: string, data?: Record<string, unknown>) {
  if (LOG_LEVELS[level] < LOG_LEVELS[MIN_LEVEL]) return;
  const out = level === 'error' ? process.stderr : process.stderr;
  out.write(JSON.stringify({ ts: new Date().toISOString(), level, msg, ...(data || {}) }) + '\n');
}

function readConfig(): GHLConfig {
  const config: GHLConfig = {
    accessToken: process.env.GHL_API_KEY || '',
    baseUrl: process.env.GHL_BASE_URL || 'https://services.leadconnectorhq.com',
    version: process.env.GHL_API_VERSION || '2021-07-28',
    locationId: process.env.GHL_LOCATION_ID || '',
  };

  if (!config.accessToken) throw new Error('GHL_API_KEY is required');
  if (!config.locationId) throw new Error('GHL_LOCATION_ID is required');
  return config;
}

function createMcpServer(client: EnhancedGHLClient): McpServer {
  const server = new McpServer(
    { name: 'ghl-mcp-server', version: '2.0.0' },
    { capabilities: { tools: {} } }
  );
  new ToolRegistry(client).registerAll(server);
  return server;
}

async function main() {
  const port = parseInt(process.env.PORT || process.env.MCP_SERVER_PORT || '8000', 10);
  const config = readConfig();
  const ghlClient = new EnhancedGHLClient(config);
  const registry = new ToolRegistry(ghlClient);
  const toolCount = registry.getToolCount();
  const startTime = Date.now();

  const accounts = new AccountResolver(config);

  // Reuse a client per resolved location so each account keeps its own cache.
  const clientCache = new Map<string, EnhancedGHLClient>();
  clientCache.set(`${config.locationId}:${config.accessToken}`, ghlClient);
  const clientFor = (cfg: GHLConfig): EnhancedGHLClient => {
    const key = `${cfg.locationId}:${cfg.accessToken}`;
    let c = clientCache.get(key);
    if (!c) {
      c = new EnhancedGHLClient(cfg);
      clientCache.set(key, c);
    }
    return c;
  };

  // Resolve which account a request targets, in priority order:
  //   1. full per-request override headers (x-ghl-access-token + x-ghl-location-id)
  //   2. account key from the URL path (/mcp/:account) or ?account= / x-ghl-account header
  //   3. the default account from env
  const resolveClient = (
    accountKey: string | undefined,
    headerToken: string | undefined,
    headerLoc: string | undefined
  ): EnhancedGHLClient => {
    if (headerToken && headerLoc) {
      return clientFor({ ...config, accessToken: headerToken, locationId: headerLoc });
    }
    return clientFor(accounts.resolve(accountKey));
  };

  log('info', 'Initializing GHL MCP server', {
    baseUrl: config.baseUrl,
    version: config.version,
    locationId: config.locationId,
    tools: toolCount,
    accounts: accounts.list().map((a) => a.key),
  });

  await ghlClient.testConnection();

  const app = express();
  app.use(cors({
    origin: (origin, callback) => {
      if (!origin) return callback(null, true);
      if (/^https?:\/\/localhost(:\d+)?$/.test(origin) ||
          origin === 'https://chatgpt.com' ||
          origin === 'https://chat.openai.com') {
        return callback(null, true);
      }
      callback(new Error('CORS not allowed'));
    },
    methods: ['GET', 'POST', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'Accept', 'mcp-session-id', 'x-ghl-access-token', 'x-ghl-location-id', 'x-ghl-account'],
    credentials: true,
  }));
  app.use(express.json());
  app.use((req, _res, next) => {
    log('debug', `${req.method} ${req.path}`, { ip: req.ip });
    next();
  });

  app.all(['/mcp', '/mcp/:account'], async (req, res) => {
    try {
      const reqAccessToken = req.headers['x-ghl-access-token'] as string | undefined;
      const reqLocationId = req.headers['x-ghl-location-id'] as string | undefined;
      const accountKey =
        (req.params.account as string | undefined) ||
        (req.query.account as string | undefined) ||
        (req.headers['x-ghl-account'] as string | undefined);
      const client = resolveClient(accountKey, reqAccessToken, reqLocationId);
      const requestServer = createMcpServer(client);
      const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
      await requestServer.connect(transport);
      await transport.handleRequest(req, res, req.body);
      res.on('close', () => {
        requestServer.close().catch(() => {});
      });
    } catch (err: any) {
      log('error', 'Streamable HTTP error', { error: err.message });
      if (!res.headersSent) {
        const unknownAccount = /Unknown GHL account/.test(err.message || '');
        res.status(unknownAccount ? 400 : 500).json({
          error: unknownAccount ? err.message : 'Internal server error',
        });
      }
    }
  });

  const handleSSE = async (req: express.Request, res: express.Response) => {
    const sessionId = String(req.query.sessionId || 'unknown');
    const accountKey =
      (req.params.account as string | undefined) ||
      (req.query.account as string | undefined) ||
      (req.headers['x-ghl-account'] as string | undefined);
    log('info', 'SSE connection', { sessionId, account: accountKey });

    try {
      const client = resolveClient(
        accountKey,
        req.headers['x-ghl-access-token'] as string | undefined,
        req.headers['x-ghl-location-id'] as string | undefined
      );
      const sseServer = createMcpServer(client);
      const transport = new SSEServerTransport('/sse', res);
      await sseServer.connect(transport);
      req.on('close', () => {
        log('info', 'SSE connection closed', { sessionId });
        sseServer.close().catch(() => {});
      });
    } catch (err: any) {
      log('error', 'SSE error', { error: err.message, sessionId });
      if (!res.headersSent) {
        const unknownAccount = /Unknown GHL account/.test(err.message || '');
        res
          .status(unknownAccount ? 400 : 500)
          .json({ error: unknownAccount ? err.message : 'Failed to establish SSE connection' });
      } else res.end();
    }
  };

  app.get(['/sse', '/sse/:account'], handleSSE);
  app.post(['/sse', '/sse/:account'], handleSSE);

  app.get('/accounts', (_req, res) => {
    res.json({ accounts: accounts.list(), count: accounts.size });
  });

  app.get('/', (_req, res) => {
    res.json({
      name: 'GoHighLevel MCP Server',
      version: '2.0.0',
      status: 'running',
      uptime: Math.floor((Date.now() - startTime) / 1000),
      endpoints: {
        health: '/health',
        capabilities: '/capabilities',
        tools: '/tools',
        execute: '/execute',
        mcp: '/mcp',
        'mcp (per account)': '/mcp/:account',
        sse: '/sse',
        accounts: '/accounts',
      },
      accounts: accounts.list(),
      tools: registry.getToolCounts(),
      cache: ghlClient.getCacheStats(),
    });
  });

  app.get('/health', (_req, res) => {
    const mem = process.memoryUsage();
    res.json({
      status: 'healthy',
      server: 'ghl-mcp-server',
      version: '2.0.0',
      uptime: Math.floor((Date.now() - startTime) / 1000),
      timestamp: new Date().toISOString(),
      tools: toolCount,
      memory: {
        rss: `${Math.round(mem.rss / 1024 / 1024)}MB`,
        heapUsed: `${Math.round(mem.heapUsed / 1024 / 1024)}MB`,
        heapTotal: `${Math.round(mem.heapTotal / 1024 / 1024)}MB`,
      },
      cache: ghlClient.getCacheStats(),
    });
  });

  app.get('/capabilities', (_req, res) => {
    res.json({
      capabilities: { tools: {} },
      server: { name: 'ghl-mcp-server', version: '2.0.0' },
      transport: ['streamable-http', 'sse'],
    });
  });

  registerExecuteRoutes(app, registry, config, accounts);

  app.get('/tool-inventory', (_req, res) => {
    res.json({
      tools: registry.getToolInventory(),
      count: registry.getToolCount(),
      generatedAt: new Date().toISOString(),
    });
  });

  app.post('/tools/call', async (req, res) => {
    const { name, arguments: args } = req.body;
    if (!name) {
      res.status(400).json({ error: 'Missing tool name' });
      return;
    }

    const accountKey =
      (req.query.account as string | undefined) ||
      (req.headers['x-ghl-account'] as string | undefined);
    let callRegistry: ToolRegistry = registry;
    if (accountKey) {
      try {
        callRegistry = new ToolRegistry(clientFor(accounts.resolve(accountKey)));
      } catch (err: any) {
        res.status(400).json({ error: err.message });
        return;
      }
    }

    try {
      const result = await callRegistry.callTool(name, args || {});
      if (result === undefined) {
        res.status(404).json({ error: `Unknown tool: ${name}` });
        return;
      }
      res.json({ result });
    } catch (err: any) {
      log('error', `REST tool error: ${name}`, { error: err.message });
      res.status(500).json({ error: `Tool execution failed: ${err.message}` });
    }
  });

  app.listen(port, '0.0.0.0', () => {
    console.log('GoHighLevel MCP Server v2.0');
    console.log(`Server: http://0.0.0.0:${port}`);
    console.log(`Streamable HTTP: http://0.0.0.0:${port}/mcp`);
    console.log(`Legacy SSE: http://0.0.0.0:${port}/sse`);
    console.log(`Tools: ${toolCount}`);
  });

}

process.on('SIGINT', () => { log('info', 'Shutting down (SIGINT)'); process.exit(0); });
process.on('SIGTERM', () => { log('info', 'Shutting down (SIGTERM)'); process.exit(0); });

main().catch((err) => {
  log('error', 'Fatal error', { error: err.message, stack: err.stack });
  process.exit(1);
});
