// n8n scheduler for the Lead Engine benchmark.
// Auth: every HTTP node sends LEAD_ENGINE_MCP_TOKEN as a Bearer header
// (configure it as an n8n env variable / credential). The engine runs the
// benchmark SYNCHRONOUSLY; against Vercel (60s cap) poll /jobs/{id} from a
// second workflow, or drive jobs via /api/v1/events/dispatch on a cron.
const dailyTrigger = node({
  type: 'n8n-nodes-base.scheduleTrigger',
  version: 1.4,
  config: {
    name: 'Daily 06:00 Trigger',
    parameters: {
      rule: {
        interval: [{ field: 'days', daysInterval: 1, triggerAtHour: 6, triggerAtMinute: 0 }],
      },
    },
  },
});

const config = node({
  type: 'n8n-nodes-base.set',
  version: 3.5,
  config: {
    name: 'Config',
    parameters: {
      mode: 'manual',
      assignments: {
        assignments: [
          { id: 'a1', name: 'engineBaseUrl', value: 'https://lead-engine-gamma-silk.vercel.app', type: 'string' },
          { id: 'a2', name: 'icpName', value: 'v0', type: 'string' },
          { id: 'a3', name: 'mcpToken', value: '={{ $env.LEAD_ENGINE_MCP_TOKEN }}', type: 'string' },
        ],
      },
    },
  },
});

const run = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.5,
  config: {
    name: 'Run V0 Benchmark',
    parameters: {
      method: 'POST',
      url: '={{ $json.engineBaseUrl + "/benchmark/run" }}',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: '={ "icp": "{{ $json.icpName }}" }',
      sendHeaders: true,
      headerParameters: {
        parameters: [{ name: 'Authorization', value: "={{ 'Bearer ' + $json.mcpToken }}" }],
      },
      options: { timeout: 600000 },
    },
  },
});

const completed = ifElse({
  version: 2.3,
  config: {
    name: 'Completed?',
    parameters: {
      conditions: {
        combinator: 'and',
        options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' },
        conditions: [
          {
            leftValue: expr('{{ $json.state }}'),
            rightValue: 'COMPLETED',
            operator: { type: 'string', operation: 'equals' },
          },
        ],
      },
    },
  },
});

const sync = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.5,
  config: {
    name: 'Sync Leads to Supabase',
    parameters: {
      method: 'POST',
      url: "={{ $('Config').item.json.engineBaseUrl + '/sync-supabase' }}",
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: '={ "job_id": "{{ $json.job_id }}" }',
      sendHeaders: true,
      headerParameters: {
        parameters: [{ name: 'Authorization', value: "={{ 'Bearer ' + $('Config').item.json.mcpToken }}" }],
      },
      options: { timeout: 300000 },
    },
  },
});

const report = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.5,
  config: {
    name: 'Get Report',
    parameters: {
      method: 'GET',
      url: "={{ $('Config').item.json.engineBaseUrl + '/report/' + $('Run V0 Benchmark').item.json.job_id }}",
      sendHeaders: true,
      headerParameters: {
        parameters: [{ name: 'Authorization', value: "={{ 'Bearer ' + $('Config').item.json.mcpToken }}" }],
      },
    },
  },
});

export default workflow('lead-engine-v0-benchmark', 'Lead Engine — V0 Benchmark Scheduler')
  .add(dailyTrigger)
  .to(config)
  .to(run)
  .to(completed.onTrue(sync.to(report)));
