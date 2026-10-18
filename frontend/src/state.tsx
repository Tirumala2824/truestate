import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { api, type Workspace, type Page, type RecordData } from './core';
type Modal = null | { type: 'upload'; purpose?: 'evidence' | 'policy'; transaction?: string } | { type: 'import' | 'policy' | 'search' | 'guide' } | { type: 'document'; id: string } | { type: 'agent'; id: string };
function useWorkspaceState() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true); const [connectionError, setConnectionError] = useState('');
  const [error, setError] = useState(''); const [toast, setToast] = useState('');
  const [page, setPage] = useState<Page>('overview'); const [caseId, setCaseId] = useState<string | null>(null);
  const [modal, setModal] = useState<Modal>(null); const [events, setEvents] = useState<RecordData[]>([]);
  const [live, setLive] = useState(false); const [busy, setBusy] = useState(''); const [lastSync, setLastSync] = useState('');
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(timer); }, []);
  const cursor = useRef(0); const refreshing = useRef(false);
  const connected = !!workspace && !connectionError;
  const refresh = useCallback(async () => {
    if (refreshing.current) return; refreshing.current = true;
    try { const data = await api<Workspace>('/api/workspace'); setWorkspace(data); setConnectionError(''); setLastSync(new Date().toISOString()); }
    catch (e) { setConnectionError((e as Error).message); }
    finally { setLoading(false); refreshing.current = false; }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (!workspace) return;
    const stream = new EventSource(`/api/events?after=${cursor.current}`); let timer: ReturnType<typeof setTimeout> | undefined;
    stream.onopen = () => { setLive(true); refresh(); }; stream.onerror = () => setLive(false);
    stream.addEventListener('activity', (message: MessageEvent) => {
      const event = JSON.parse(message.data); cursor.current = event.seq;
      setEvents(old => [...old.filter(item => item.seq !== event.seq), event].slice(-200));
      clearTimeout(timer); timer = setTimeout(refresh, 400);
    });
    return () => { stream.close(); clearTimeout(timer); };
  }, [!!workspace, refresh]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(''), 6000); return () => clearTimeout(timer); }, [toast]);
  const navigate = (next: Page) => { setPage(next); setCaseId(null); setModal(null); window.scrollTo({ top: 0 }); };
  const selectCase = (id: string) => { setCaseId(id); setModal(null); window.scrollTo({ top: 0 }); };
  const action = async (key: string, task: () => Promise<unknown>, message: string) => {
    setBusy(key); setError('');
    try { await task(); setToast(message); await refresh(); return true; }
    catch (e) { setError((e as Error).message); return false; }
    finally { setBusy(''); }
  };
  return { now, workspace, connected, loading, connectionError, error, setError, toast, setToast, page, navigate, caseId, selectCase, modal, setModal, events, live, busy, action, refresh, lastSync };
}
type State = ReturnType<typeof useWorkspaceState>;
const Context = createContext<State | null>(null);
export function WorkspaceProvider({ children }: { children: React.ReactNode }) { return <Context.Provider value={useWorkspaceState()}>{children}</Context.Provider>; }
export function useWorkspace() { const value = useContext(Context); if (!value) throw new Error('Workspace provider is required'); return value; }
