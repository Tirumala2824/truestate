export type RecordData = Record<string, any>;
export type Page = 'overview' | 'queue' | 'agents' | 'evidence' | 'policies' | 'analytics' | 'audit' | 'connections';
export type Workspace = {
  user: { email: string; reviewer: boolean; read_only?: boolean };
  transactions: RecordData[]; documents: RecordData[]; decisions: RecordData[];
  runs: RecordData[]; jobs: RecordData[]; knowledge: RecordData[]; receipts: RecordData[];
  sandbox?: { enabled: boolean; assessment_limit: number; upload_limit: number; sample_records: number };
  synthetic_dataset?: RecordData | null; policy: RecordData | null; configuration: RecordData; limits: RecordData;
};
export const pageNames: Record<Page, string> = { overview: 'Overview', queue: 'Work queue', agents: 'Agents', evidence: 'Evidence', policies: 'Policies', analytics: 'Analytics', audit: 'Audit trail', connections: 'Connections' };
export const statusNames: Record<string, string> = { not_assessed: 'Not assessed', ready: 'Ready', hold: 'On hold', needs_evidence: 'Evidence needed', review: 'Needs review', stale: 'Reassessment needed', queued: 'Queued', running: 'In progress', failed: 'Failed', processed: 'Processed', not_configured: 'Not configured', configured_not_invoked: 'Configured', reachable: 'Verified', error: 'Connection error', submitted: 'Indexing', searchable: 'Searchable', executed: 'Executed', rejected: 'Rejected', unknown: 'Inconclusive' };
export function title(value: string) { return statusNames[value] || value.replaceAll('_', ' ').replaceAll('.', ' ').replace(/^./, c => c.toUpperCase()); }
export function caseStatus(tx: RecordData, workspace: Workspace | null, now = Date.now()): string {
  const decision = workspace?.decisions.find(d => d.id === tx.id);
  if (decision) {
    const expiry = new Date(decision.expires_at).getTime();
    return decision.invalidated_at || !Number.isFinite(expiry) || expiry <= now ? 'stale' : decision.disposition;
  }
  const job = workspace?.jobs.find(j => j.target === tx.id && j.kind === 'investigate');
  return job?.status === 'failed' ? 'failed' : job?.status === 'running' ? 'running' : job ? 'queued' : tx.synthetic ? 'not_assessed' : 'queued';
}
export const needsAttention = (status: string) => ['review', 'needs_evidence', 'stale', 'failed'].includes(status);
export function money(value: string | number, currency = 'USD') {
  try { return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 2 }).format(Number(value)); }
  catch { return `${currency} ${value}`; }
}
export function date(value?: string, time = true) {
  if (!value || !Number.isFinite(new Date(value).getTime())) return 'Not available';
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', ...(time ? { hour: '2-digit', minute: '2-digit' } : {}) }).format(new Date(value));
}
export function bytes(value: number) { return value >= 1048576 ? `${(value / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`; }
export function initials(value: string) { return value.split(/\s+/).slice(0, 2).map(v => v[0]).join('').toUpperCase(); }
export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...options, headers: { 'X-Truestate-Client': 'operations', ...options.headers } });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((e: RecordData) => `${e.loc?.slice(1).join('.')}: ${e.msg}`).join('; ') : response.status === 401 ? 'Sign in through your Google Cloud workspace to continue.' : `The request could not complete (${response.status}). Try again.`);
  }
  if (!body) throw new Error('The workspace API is unavailable at this address.');
  return body;
}
export function download(content: string, filename: string, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const csvHeaders = ['id', 'supplier_id', 'supplier_name', 'amount', 'currency', 'occurred_at', 'reference', 'account_fingerprint', 'previous_account_fingerprint', 'document_ids'];
export function parseCsv(input: string): string[][] {
  const text = input.replace(/^\uFEFF/, ''); const rows: string[][] = []; let row: string[] = []; let field = ''; let quoted = false; let afterQuote = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) { if (ch === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else { quoted = false; afterQuote = true; } } else field += ch; }
    else if (ch === '"') { if (field || afterQuote) throw new Error('A quotation mark must start a CSV field.'); quoted = true; }
    else if (ch === ',') { row.push(field); field = ''; afterQuote = false; }
    else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(field); if (row.some(v => v.trim())) rows.push(row); row = []; field = ''; afterQuote = false; }
    else { if (afterQuote) throw new Error('Unexpected text after a closing quote.'); field += ch; }
  }
  if (quoted) throw new Error('A quoted CSV field is not closed.');
  row.push(field); if (row.some(v => v.trim())) rows.push(row);
  return rows;
}
export function inspectCsv(input: string) {
  const [headers = [], ...data] = parseCsv(input);
  const required = ['id', 'supplier_id', 'supplier_name', 'amount', 'currency', 'occurred_at', 'account_fingerprint'];
  if (new Set(headers).size !== headers.length) throw new Error('The CSV has duplicate column names.');
  const missing = required.filter(h => !headers.includes(h));
  if (missing.length) throw new Error('Missing columns: ' + missing.join(', '));
  const extra = headers.filter(h => !csvHeaders.includes(h));
  if (extra.length) throw new Error('Unrecognized columns: ' + extra.join(', '));
  if (!data.length || data.length > 1000) throw new Error('Include between 1 and 1,000 transactions.');
  const ids = new Set<string>();
  const rows = data.map((fields, index) => {
    if (fields.length !== headers.length) throw new Error(`Row ${index + 2} has ${fields.length} values; expected ${headers.length}.`);
    const row = Object.fromEntries(headers.map((header, i) => [header, fields[i]]));
    const problems = [];
    if (!/^[A-Za-z0-9_-]{1,100}$/.test(row.id) || ids.has(row.id)) problems.push('unique transaction ID');
    ids.add(row.id);
    if (!row.supplier_id || !row.supplier_name) problems.push('supplier name and ID');
    if (!/^\d+(\.\d{1,2})?$/.test(row.amount) || Number(row.amount) <= 0) problems.push('positive amount with up to 2 decimal places');
    if (!/^[A-Z]{3}$/.test(row.currency)) problems.push('three-letter currency');
    if (!Number.isFinite(Date.parse(row.occurred_at)) || !/(Z|[+-]\d{2}:\d{2})$/.test(row.occurred_at)) problems.push('date with timezone');
    if (row.account_fingerprint.length < 8) problems.push('account fingerprint of at least 8 characters');
    if (problems.length) throw new Error(`Row ${index + 2}: check ${problems.join(', ')}.`);
    return row;
  });
  return { headers, rows };
}
export function sseFrames(buffer: string) {
  const frames: { event: string; data: RecordData }[] = []; let end;
  while ((end = buffer.indexOf('\n\n')) !== -1) {
    const frame = buffer.slice(0, end); buffer = buffer.slice(end + 2);
    const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    if (data) frames.push({ event: frame.split('\n').find(line => line.startsWith('event:'))?.slice(6).trim() || 'message', data: JSON.parse(data) });
  }
  return { frames, remainder: buffer };
}
