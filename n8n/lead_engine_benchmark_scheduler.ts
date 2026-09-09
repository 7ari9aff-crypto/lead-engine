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
          { id: 'a1', name: 'engineBaseUrl', value: 'http://localhost:8000', type: 'string' },
          { id: 'a2', name: 'icpName', value: 'v0_saudi_dental', type: 'string' },
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
      jsonBody: '={ "icp": "{{ $json.icpName }}", "dry_run": true }',
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
    },
  },
});

export default workflow('lead-engine-v0-benchmark', 'Lead Engine — V0 Benchmark Scheduler')
  .add(dailyTrigger)
  .to(config)
  .to(run)
  .to(completed.onTrue(sync.to(report)));
