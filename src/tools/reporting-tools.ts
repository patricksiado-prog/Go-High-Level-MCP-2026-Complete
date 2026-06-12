/**
 * GoHighLevel Reporting/Analytics Tools
 * Tools for accessing reports and analytics
 */

import { GHLApiClient } from '../clients/ghl-api-client.js';

export class ReportingTools {
  constructor(private ghlClient: GHLApiClient) {}

  getToolDefinitions() {
    return [
      // Attribution Reports
      {
        name: 'get_attribution_report',
        description: 'Get attribution/source tracking report showing where leads came from',
        inputSchema: {
          type: 'object',
          properties: {
            locationId: { type: 'string', description: 'Location ID' },
            startDate: { type: 'string', description: 'Start date (YYYY-MM-DD)' },
            endDate: { type: 'string', description: 'End date (YYYY-MM-DD)' },
          },
          required: ['startDate', 'endDate']
        },
        _meta: {
          labels: {
            category: "analytics",
            access: "read",
            complexity: "simple"
          }
        }
      },

      // Call Reports
      {
        name: 'get_call_reports',
        description: 'Get call activity (conversation-level counts aggregated from conversation data, with Houston/Oklahoma region split). Optionally filter by assigned user.',
        inputSchema: {
          type: 'object',
          properties: {
            locationId: { type: 'string', description: 'Location ID' },
            startDate: { type: 'string', description: 'Start date (YYYY-MM-DD)' },
            endDate: { type: 'string', description: 'End date (YYYY-MM-DD)' },
            userId: { type: 'string', description: 'Filter by user ID' },
            type: { type: 'string', enum: ['inbound', 'outbound', 'all'], description: 'Call type filter' },
          },
          required: ['startDate', 'endDate']
        },
        _meta: {
          labels: {
            category: "analytics",
            access: "read",
            complexity: "batch"
          }
        }
      },

      // Appointment Reports
      {
        name: 'get_appointment_reports',
        description: 'Get appointment activity reports',
        inputSchema: {
          type: 'object',
          properties: {
            locationId: { type: 'string', description: 'Location ID' },
            startDate: { type: 'string', description: 'Start date (YYYY-MM-DD)' },
            endDate: { type: 'string', description: 'End date (YYYY-MM-DD)' },
            calendarId: { type: 'string', description: 'Filter by calendar ID' },
            status: { type: 'string', enum: ['booked', 'confirmed', 'showed', 'noshow', 'cancelled'], description: 'Appointment status filter' },
          },
          required: ['startDate', 'endDate']
        },
        _meta: {
          labels: {
            category: "analytics",
            access: "read",
            complexity: "simple"
          }
        }
      },

      // Pipeline/Opportunity Reports
      {
        name: 'get_pipeline_reports',
        description: 'Get pipeline/opportunity performance reports',
        inputSchema: {
          type: 'object',
          properties: {
            locationId: { type: 'string', description: 'Location ID' },
            pipelineId: { type: 'string', description: 'Filter by pipeline ID' },
            startDate: { type: 'string', description: 'Start date (YYYY-MM-DD)' },
            endDate: { type: 'string', description: 'End date (YYYY-MM-DD)' },
            userId: { type: 'string', description: 'Filter by assigned user' },
          },
          required: ['startDate', 'endDate']
        },
        _meta: {
          labels: {
            category: "analytics",
            access: "read",
            complexity: "simple"
          }
        }
      },

      // Email/SMS Reports
      {
        name: 'get_email_reports',
        description: 'Get email performance reports (deliverability, opens, clicks)',
        inputSchema: {
          type: 'object',
          properties: {
            locationId: { type: 'string', description: 'Location ID' },
            startDate: { type: 'string', description: 'Start date (YYYY-MM-DD)' },
            endDate: { type: 'string', description: 'End date (YYYY-MM-DD)' },
          },
          required: ['startDate', 'endDate']
        },
        _meta: {
          labels: {
            category: "analytics",
            access: "read",
            complexity: "simple"
          }
        }
      },
      {
        name: 'get_sms_reports',
        description: 'Get SMS activity (conversation-level counts aggregated from conversation data, with Houston/Oklahoma region split). Optionally filter by assigned user.',
        inputSchema: {
          type: 'object',
          properties: {
            locationId: { type: 'string', description: 'Location ID' },
            startDate: { type: 'string', description: 'Start date (YYYY-MM-DD)' },
            endDate: { type: 'string', description: 'End date (YYYY-MM-DD)' },
            userId: { type: 'string', description: 'Filter to conversations assigned to this user ID' },
          },
          required: ['startDate', 'endDate']
        },
        _meta: {
          labels: {
            category: "analytics",
            access: "read",
            complexity: "simple"
          }
        }
      },

      // Funnel Reports
      {
        name: 'get_funnel_reports',
        description: 'Get funnel performance reports (page views, conversions)',
        inputSchema: {
          type: 'object',
          properties: {
            locationId: { type: 'string', description: 'Location ID' },
            funnelId: { type: 'string', description: 'Filter by funnel ID' },
            startDate: { type: 'string', description: 'Start date (YYYY-MM-DD)' },
            endDate: { type: 'string', description: 'End date (YYYY-MM-DD)' },
          },
          required: ['startDate', 'endDate']
        },
        _meta: {
          labels: {
            category: "analytics",
            access: "read",
            complexity: "simple"
          }
        }
      },

      // Google/Facebook Ad Reports
      {
        name: 'get_ad_reports',
        description: 'Get advertising performance reports (Google/Facebook ads)',
        inputSchema: {
          type: 'object',
          properties: {
            locationId: { type: 'string', description: 'Location ID' },
            platform: { type: 'string', enum: ['google', 'facebook', 'all'], description: 'Ad platform' },
            startDate: { type: 'string', description: 'Start date (YYYY-MM-DD)' },
            endDate: { type: 'string', description: 'End date (YYYY-MM-DD)' },
          },
          required: ['startDate', 'endDate']
        },
        _meta: {
          labels: {
            category: "analytics",
            access: "read",
            complexity: "simple"
          }
        }
      },

      // Agent Performance
      {
        name: 'get_agent_reports',
        description: 'Get agent/user performance reports',
        inputSchema: {
          type: 'object',
          properties: {
            locationId: { type: 'string', description: 'Location ID' },
            userId: { type: 'string', description: 'Filter by user ID' },
            startDate: { type: 'string', description: 'Start date (YYYY-MM-DD)' },
            endDate: { type: 'string', description: 'End date (YYYY-MM-DD)' },
          },
          required: ['startDate', 'endDate']
        },
        _meta: {
          labels: {
            category: "analytics",
            access: "read",
            complexity: "simple"
          }
        }
      },

      // Dashboard Stats
      {
        name: 'get_dashboard_stats',
        description: 'Get main dashboard statistics overview',
        inputSchema: {
          type: 'object',
          properties: {
            locationId: { type: 'string', description: 'Location ID' },
            dateRange: { type: 'string', enum: ['today', 'yesterday', 'last7days', 'last30days', 'thisMonth', 'lastMonth', 'custom'], description: 'Date range preset' },
            startDate: { type: 'string', description: 'Start date for custom range' },
            endDate: { type: 'string', description: 'End date for custom range' }
          }
        },
        _meta: {
          labels: {
            category: "analytics",
            access: "read",
            complexity: "simple"
          }
        }
      },

      // Conversion Reports
      {
        name: 'get_conversion_reports',
        description: 'Get conversion tracking reports',
        inputSchema: {
          type: 'object',
          properties: {
            locationId: { type: 'string', description: 'Location ID' },
            startDate: { type: 'string', description: 'Start date (YYYY-MM-DD)' },
            endDate: { type: 'string', description: 'End date (YYYY-MM-DD)' },
            source: { type: 'string', description: 'Filter by source' },
          },
          required: ['startDate', 'endDate']
        },
        _meta: {
          labels: {
            category: "analytics",
            access: "read",
            complexity: "simple"
          }
        }
      },

      // Revenue Reports
      {
        name: 'get_revenue_reports',
        description: 'Get revenue/payment reports',
        inputSchema: {
          type: 'object',
          properties: {
            locationId: { type: 'string', description: 'Location ID' },
            startDate: { type: 'string', description: 'Start date (YYYY-MM-DD)' },
            endDate: { type: 'string', description: 'End date (YYYY-MM-DD)' },
            groupBy: { type: 'string', enum: ['day', 'week', 'month'], description: 'Group results by' },
          },
          required: ['startDate', 'endDate']
        },
        _meta: {
          labels: {
            category: "analytics",
            access: "read",
            complexity: "simple"
          }
        }
      }
    ];
  }

  async handleToolCall(toolName: string, args: Record<string, unknown>): Promise<unknown> {
    const config = this.ghlClient.getConfig();
    const locationId = (args.locationId as string) || config.locationId;

    switch (toolName) {
      case 'get_attribution_report': {
        const params = new URLSearchParams();
        params.append('locationId', locationId);
        params.append('startDate', String(args.startDate));
        params.append('endDate', String(args.endDate));
        return this.ghlClient.makeRequest('GET', `/reporting/attribution?${params.toString()}`);
      }
      case 'get_call_reports': {
        // GHL's public API has no call-report endpoint; aggregate from conversation data instead.
        const convos = await this.fetchConversationsInRange(
          locationId, args.startDate as string, args.endDate as string,
          args.userId ? { assignedTo: args.userId as string } : {}
        );
        const sum = this.summarizeConversations(convos);
        return {
          success: true,
          source: 'conversation-aggregation',
          note: 'GHL has no public call-report endpoint. This counts CONVERSATIONS whose most-recent message is a call (TYPE_CALL/IVR/campaign/custom) within the date range — a conversation-level approximation of call activity, not a per-message total. byRegion is by contact area code (Houston vs Oklahoma). For exact per-message inbound/outbound counts use the GHL Call Reporting UI.',
          period: { startDate: args.startDate, endDate: args.endDate },
          userId: args.userId || null,
          calls: sum.calls,
          byRegion: sum.byRegion,
          conversationsScanned: convos.length
        };
      }
      case 'get_appointment_reports': {
        const params = new URLSearchParams();
        params.append('locationId', locationId);
        params.append('startDate', String(args.startDate));
        params.append('endDate', String(args.endDate));
        if (args.calendarId) params.append('calendarId', String(args.calendarId));
        if (args.status) params.append('status', String(args.status));
        return this.ghlClient.makeRequest('GET', `/reporting/appointments?${params.toString()}`);
      }
      case 'get_pipeline_reports': {
        const params = new URLSearchParams();
        params.append('locationId', locationId);
        params.append('startDate', String(args.startDate));
        params.append('endDate', String(args.endDate));
        if (args.pipelineId) params.append('pipelineId', String(args.pipelineId));
        if (args.userId) params.append('userId', String(args.userId));
        return this.ghlClient.makeRequest('GET', `/reporting/pipelines?${params.toString()}`);
      }
      case 'get_email_reports': {
        const params = new URLSearchParams();
        params.append('locationId', locationId);
        params.append('startDate', String(args.startDate));
        params.append('endDate', String(args.endDate));
        return this.ghlClient.makeRequest('GET', `/reporting/emails?${params.toString()}`);
      }
      case 'get_sms_reports': {
        // GHL's public API has no SMS-report endpoint; aggregate from conversation data instead.
        const convos = await this.fetchConversationsInRange(
          locationId, args.startDate as string, args.endDate as string,
          args.userId ? { assignedTo: args.userId as string } : {}
        );
        const sum = this.summarizeConversations(convos);
        return {
          success: true,
          source: 'conversation-aggregation',
          note: 'GHL has no public SMS-report endpoint. This counts CONVERSATIONS whose most-recent message is an SMS (TYPE_SMS/campaign/custom) within the date range — a conversation-level approximation of texting activity, not a per-message total. byRegion is by contact area code (Houston vs Oklahoma). For exact per-message sent/delivered counts use the GHL SMS Reporting UI.',
          period: { startDate: args.startDate, endDate: args.endDate },
          userId: args.userId || null,
          sms: sum.sms,
          byRegion: sum.byRegion,
          conversationsScanned: convos.length
        };
      }
      case 'get_funnel_reports': {
        const params = new URLSearchParams();
        params.append('locationId', locationId);
        params.append('startDate', String(args.startDate));
        params.append('endDate', String(args.endDate));
        if (args.funnelId) params.append('funnelId', String(args.funnelId));
        return this.ghlClient.makeRequest('GET', `/reporting/funnels?${params.toString()}`);
      }
      case 'get_ad_reports': {
        const params = new URLSearchParams();
        params.append('locationId', locationId);
        params.append('startDate', String(args.startDate));
        params.append('endDate', String(args.endDate));
        if (args.platform) params.append('platform', String(args.platform));
        return this.ghlClient.makeRequest('GET', `/reporting/ads?${params.toString()}`);
      }
      case 'get_agent_reports': {
        // GHL's public API has no agent-report endpoint; aggregate conversations assigned to the user.
        const convos = await this.fetchConversationsInRange(
          locationId, args.startDate as string, args.endDate as string,
          args.userId ? { assignedTo: args.userId as string } : {}
        );
        const sum = this.summarizeConversations(convos);
        return {
          success: true,
          source: 'conversation-aggregation',
          note: args.userId
            ? 'GHL has no public agent-report endpoint. This counts CONVERSATIONS assigned to this user whose most-recent message falls in the date range, bucketed by channel (calls/sms/emails) and contact region. It is a conversation-level activity proxy, not a per-message productivity count. Note: agency-level users not present in the location user list cannot be filtered by assignedTo here.'
            : 'No userId supplied — returning location-wide conversation activity bucketed by channel and region. Pass userId to scope to one agent.',
          period: { startDate: args.startDate, endDate: args.endDate },
          userId: args.userId || null,
          activity: { calls: sum.calls, sms: sum.sms, emails: sum.emails, other: sum.other, total: sum.total },
          byRegion: sum.byRegion,
          conversationsScanned: convos.length
        };
      }
      case 'get_dashboard_stats': {
        // GHL's public API has no dashboard endpoint; build an overview from conversation data.
        const range = this.resolveDateRange(
          args.dateRange as string | undefined,
          args.startDate as string | undefined,
          args.endDate as string | undefined
        );
        const convos = await this.fetchConversationsInRange(locationId, range.startDate, range.endDate, {});
        const sum = this.summarizeConversations(convos);
        return {
          success: true,
          source: 'conversation-aggregation',
          note: 'GHL has no public dashboard endpoint. This overview is built from conversation data: counts of conversations active in the window bucketed by channel (calls/sms/emails) and by contact region (Houston vs Oklahoma). For revenue/appointment/pipeline KPIs use the dedicated report tools or the GHL dashboard UI.',
          period: { startDate: range.startDate, endDate: range.endDate, preset: args.dateRange || 'custom' },
          conversations: { calls: sum.calls, sms: sum.sms, emails: sum.emails, other: sum.other, total: sum.total },
          byRegion: sum.byRegion,
          conversationsScanned: convos.length
        };
      }
      case 'get_conversion_reports': {
        const params = new URLSearchParams();
        params.append('locationId', locationId);
        params.append('startDate', String(args.startDate));
        params.append('endDate', String(args.endDate));
        if (args.source) params.append('source', String(args.source));
        return this.ghlClient.makeRequest('GET', `/reporting/conversions?${params.toString()}`);
      }
      case 'get_revenue_reports': {
        const params = new URLSearchParams();
        params.append('locationId', locationId);
        params.append('startDate', String(args.startDate));
        params.append('endDate', String(args.endDate));
        if (args.groupBy) params.append('groupBy', String(args.groupBy));
        return this.ghlClient.makeRequest('GET', `/reporting/revenue?${params.toString()}`);
      }

      default:
        throw new Error(`Unknown tool: ${toolName}`);
    }
  }

  // ---- Conversation-aggregation helpers (GHL public API has no /reporting/* call/sms/agent/dashboard endpoints) ----

  private static readonly CALL_TYPES = [
    'TYPE_CALL', 'TYPE_CAMPAIGN_CALL', 'TYPE_CAMPAIGN_MANUAL_CALL', 'TYPE_IVR_CALL', 'TYPE_CUSTOM_CALL'
  ];
  private static readonly SMS_TYPES = [
    'TYPE_SMS', 'TYPE_CAMPAIGN_SMS', 'TYPE_CAMPAIGN_MANUAL_SMS', 'TYPE_CUSTOM_SMS',
    'TYPE_CUSTOM_PROVIDER_SMS', 'TYPE_SMS_REVIEW_REQUEST', 'TYPE_SMS_NO_SHOW_REQUEST'
  ];
  private static readonly EMAIL_TYPES = [
    'TYPE_EMAIL', 'TYPE_CAMPAIGN_EMAIL', 'TYPE_CUSTOM_EMAIL', 'TYPE_CUSTOM_PROVIDER_EMAIL'
  ];

  /** Classify a phone number into a sending region by US area code. Houston-metro vs Oklahoma vs other. */
  private regionOf(phone?: string): string {
    if (!phone) return 'unknown';
    const digits = String(phone).replace(/\D/g, '');
    const ten = digits.length > 10 ? digits.slice(-10) : digits;
    if (ten.length < 10) return 'unknown';
    const area = ten.slice(0, 3);
    const HOUSTON = new Set(['713', '281', '832', '346', '409', '936', '979']);
    const OKLAHOMA = new Set(['405', '580', '918', '539', '572']);
    if (HOUSTON.has(area)) return 'houston';
    if (OKLAHOMA.has(area)) return 'oklahoma';
    return 'other';
  }

  /** Bucket a list of conversations by channel (call/sms/email) and by contact region. */
  private summarizeConversations(convos: Array<Record<string, unknown>>): {
    calls: number; sms: number; emails: number; other: number; total: number; byRegion: Record<string, number>;
  } {
    let calls = 0, sms = 0, emails = 0, other = 0;
    const byRegion: Record<string, number> = {};
    for (const c of convos) {
      const t = c.lastMessageType as string;
      if (ReportingTools.CALL_TYPES.includes(t)) calls++;
      else if (ReportingTools.SMS_TYPES.includes(t)) sms++;
      else if (ReportingTools.EMAIL_TYPES.includes(t)) emails++;
      else other++;
      const r = this.regionOf(c.phone as string | undefined);
      byRegion[r] = (byRegion[r] || 0) + 1;
    }
    return { calls, sms, emails, other, total: convos.length, byRegion };
  }

  /** Resolve a dateRange preset (or custom start/end) into concrete YYYY-MM-DD bounds. */
  private resolveDateRange(preset?: string, startDate?: string, endDate?: string): { startDate?: string; endDate?: string } {
    if (startDate || endDate) return { startDate, endDate };
    const fmt = (d: Date) => d.toISOString().slice(0, 10);
    const now = new Date();
    const end = fmt(now);
    const daysAgo = (n: number) => { const d = new Date(now); d.setDate(d.getDate() - n); return fmt(d); };
    switch (preset) {
      case 'today': return { startDate: end, endDate: end };
      case 'yesterday': return { startDate: daysAgo(1), endDate: daysAgo(1) };
      case 'last7days': return { startDate: daysAgo(7), endDate: end };
      case 'last30days': return { startDate: daysAgo(30), endDate: end };
      case 'thisMonth': return { startDate: fmt(new Date(now.getFullYear(), now.getMonth(), 1)), endDate: end };
      case 'lastMonth': return {
        startDate: fmt(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
        endDate: fmt(new Date(now.getFullYear(), now.getMonth(), 0))
      };
      default: return { startDate: daysAgo(30), endDate: end };
    }
  }

  /**
   * Paginate the conversation-search endpoint and return conversations whose lastMessageDate
   * falls within [startDate, endDate]. Sorted newest-first; stops once it pages past the window.
   * Bounded by maxPages and a seen-id guard so it can never loop indefinitely.
   */
  private async fetchConversationsInRange(
    locationId: string,
    startDate?: string,
    endDate?: string,
    filter: { assignedTo?: string } = {},
    maxPages = 25
  ): Promise<Array<Record<string, unknown>>> {
    const startMs = startDate ? Date.parse(startDate) : undefined;
    const endMs = endDate ? Date.parse(endDate) + 24 * 60 * 60 * 1000 : undefined; // end-inclusive
    const out: Array<Record<string, unknown>> = [];
    const seen = new Set<string>();
    let startAfterDate: number | undefined;

    for (let page = 0; page < maxPages; page++) {
      const req: Record<string, unknown> = {
        locationId,
        limit: 100,
        sortBy: 'last_message_date',
        sort: 'desc'
      };
      if (filter.assignedTo) req.assignedTo = filter.assignedTo;
      if (startAfterDate !== undefined) req.startAfterDate = startAfterDate;

      const resp = await this.ghlClient.searchConversations(req as unknown as Parameters<typeof this.ghlClient.searchConversations>[0]);
      const convos = ((resp?.data?.conversations) || []) as unknown as Array<Record<string, unknown>>;
      if (convos.length === 0) break;

      let newThisPage = 0;
      let pagedPastStart = false;
      for (const c of convos) {
        const id = c.id as string;
        if (id && seen.has(id)) continue;
        if (id) seen.add(id);
        newThisPage++;
        const dms = c.lastMessageDate ? Date.parse(c.lastMessageDate as string) : undefined;
        if (dms !== undefined && endMs !== undefined && dms >= endMs) continue;      // newer than window
        if (dms !== undefined && startMs !== undefined && dms < startMs) { pagedPastStart = true; continue; } // older than window
        out.push(c);
      }

      if (pagedPastStart) break;       // sorted desc → once we cross the start bound we're done
      if (newThisPage === 0) break;    // no progress (cursor not advancing) → stop
      if (convos.length < 100) break;  // last page

      const oldest = convos[convos.length - 1];
      const oldestMs = oldest?.lastMessageDate ? Date.parse(oldest.lastMessageDate as string) : undefined;
      if (oldestMs === undefined) break;
      startAfterDate = oldestMs;
    }
    return out;
  }
}
