import {
  StrictMode,
  createContext,
  useContext,
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { createRoot } from "react-dom/client";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronRight,
  FileText,
  FolderOpen,
  History,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  MessageSquare,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import { download, post, request, setToken } from "./api";
import type {
  Config,
  Engagement,
  Evidence,
  Job,
  Payload,
  Revision,
  Workspace,
} from "./types";
import "./style.css";

const STAGES = ["onboarding", "mapping", "planning", "sampling", "testing"];
const ErrorContext = createContext("");
const LABELS: Record<string, string> = {
  onboarding: "Engagement & requests",
  mapping: "Account mapping",
  planning: "Materiality & scope",
  sampling: "Expense sample",
  testing: "Expense testing",
  evidence: "Evidence library",
  requests: "Client requests",
  history: "Review history",
};
const FSLIS = [
  "Cash",
  "Accounts Receivable",
  "Inventory",
  "Prepaid Expenses",
  "Property & Equipment",
  "Accounts Payable",
  "Accrued Liabilities",
  "Debt",
  "Equity",
  "Revenue",
  "Cost of Goods Sold",
  "Operating Expenses",
];
const money = (value: unknown) =>
  value == null
    ? "—"
    : Number(value).toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
      });
const label = (value: string) => value.replaceAll("_", " ");
// Server amounts are canonical two-decimal strings; sum integer cents for display.
const totalAmount = (values: string[]) => {
  const cents = values.reduce(
    (sum, value) => sum + BigInt(value.replace(".", "")),
    0n,
  );
  const absolute = cents < 0n ? -cents : cents;
  return `${cents < 0n ? "-" : ""}${absolute / 100n}.${String(absolute % 100n).padStart(2, "0")}`;
};
const dateTime = (value?: string) =>
  value ? new Date(value).toLocaleString() : "Pending";
function Status({ value }: { value: string }) {
  return <span className={`status ${value}`}>{label(value)}</span>;
}
function Spinner() {
  return <LoaderCircle size={17} className="spin" aria-label="Working" />;
}
function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <FolderOpen size={30} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function DataTable({
  headers,
  rows,
  footer,
}: {
  headers: string[];
  rows: ReactNode[][];
  footer?: ReactNode[];
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j}>{c ?? "—"}</td>
              ))}
            </tr>
          ))}
        </tbody>
        {footer && (
          <tfoot>
            <tr>
              {footer.map((cell, index) => (
                <td key={index}>{cell}</td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
function Modal({
  title,
  children,
  close,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const error = useContext(ErrorContext);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog ref={ref} className={wide ? "wide" : ""} onCancel={close}>
      <div className="modal-head">
        <h2>{title}</h2>
        <button className="icon" aria-label="Close dialog" onClick={close}>
          <X size={20} />
        </button>
      </div>
      {error && (
        <div className="banner error" role="alert">
          {error}
        </div>
      )}
      {children}
    </dialog>
  );
}

function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [auth, setAuth] = useState<SupabaseClient | null>(null);
  const [signedIn, setSignedIn] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    let cleanup = () => {};
    request<Config>("/api/config")
      .then((c) => {
        if (cancelled) return;
        setConfig(c);
        if (c.local_auth) {
          setSignedIn(true);
          return;
        }
        if (!c.supabase_url || !c.publishable_key) {
          setError(
            "Authentication is not configured. Complete the server settings.",
          );
          return;
        }
        const client = createClient(c.supabase_url, c.publishable_key);
        setAuth(client);
        client.auth.getSession().then(({ data }) => {
          if (cancelled) return;
          setToken(data.session?.access_token || "");
          setSignedIn(!!data.session);
        });
        const {
          data: { subscription },
        } = client.auth.onAuthStateChange((_event, session) => {
          if (cancelled) return;
          setToken(session?.access_token || "");
          setSignedIn(!!session);
        });
        cleanup = () => {
          subscription.unsubscribe();
          void client.auth.stopAutoRefresh();
        };
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
      cleanup();
    };
  }, []);
  const portal = new URLSearchParams(location.hash.slice(1)).get("upload");
  if (portal) return <ClientPortal token={portal} />;
  if (!config)
    return (
      <div className="boot">
        <ShieldCheck size={36} />
        <h1>AI Auditor</h1>
        {error ? (
          <>
            <p role="alert">{error}</p>
            <button onClick={() => location.reload()}>Retry</button>
          </>
        ) : (
          <p>
            <Spinner /> Opening your workspace…
          </p>
        )}
      </div>
    );
  if (!signedIn) return <Login auth={auth} setupError={error} />;
  return (
    <AuditorWorkspace
      config={config}
      signOut={() => {
        if (auth) void auth.auth.signOut();
      }}
    />
  );
}

function Login({
  auth,
  setupError,
}: {
  auth: SupabaseClient | null;
  setupError: string;
}) {
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function login(e: FormEvent) {
    e.preventDefault();
    if (!auth) return;
    setBusy(true);
    setError("");
    const { error } = await auth.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) setError(error.message);
  }
  return (
    <div className="login-page">
      <div className="login-brand">
        <ShieldCheck size={28} />
        <span>AI AUDITOR</span>
      </div>
      <main className="login-card">
        <span className="eyebrow">PRIVATE REVIEW WORKSPACE</span>
        <h1>
          Sign in to your
          <br />
          audit workspace.
        </h1>
        <p>Use the account your workspace administrator created for you.</p>
        <form onSubmit={login}>
          <label>
            Email address
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {(error || setupError) && (
            <p className="error" role="alert">
              {error || setupError}
            </p>
          )}
          <button className="primary full" disabled={busy || !auth}>
            {busy ? (
              <Spinner />
            ) : (
              <>
                Sign in <ArrowRight size={17} />
              </>
            )}
          </button>
        </form>
        <div className="private-note">
          <LockKeyhole size={14} /> Access is limited to approved accounts.
        </div>
      </main>
      <p className="login-footer">Evidence. Judgment. Review.</p>
    </div>
  );
}

function AuditorWorkspace({
  config,
  signOut,
}: {
  config: Config;
  signOut: () => void;
}) {
  const [engagements, setEngagements] = useState<Engagement[]>([]),
    [selected, setSelected] = useState(""),
    [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [view, setView] = useState(() => {
      const saved = sessionStorage.getItem("auditor-view");
      return saved && Object.hasOwn(LABELS, saved) ? saved : "onboarding";
    }),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [newClient, setNewClient] = useState(false);
  const [user, setUser] = useState("Reviewer"),
    [chatText, setChatText] = useState(""),
    [evidence, setEvidence] = useState<Evidence | null>(null);
  const [edit, setEdit] = useState<{
      type: string;
      data: Payload;
      version: number;
    } | null>(null),
    [portalLink, setPortalLink] = useState("");
  const uploader = useRef<HTMLInputElement>(null),
    chatEnd = useRef<HTMLDivElement>(null);
  const previousSelected = useRef("");
  const activeSelected = useRef(selected);
  activeSelected.current = selected;
  const refresh = useCallback(async () => {
    if (selected) {
      const result = await request<Workspace>(`/api/engagements/${selected}`);
      if (activeSelected.current === selected) setWorkspace(result);
    }
  }, [selected]);
  useEffect(() => {
    request<Engagement[]>("/api/engagements")
      .then((list) => {
        setEngagements(list);
        const saved = sessionStorage.getItem("auditor-engagement");
        const restored = list.find((e) => e.id === saved);
        if (list.length) setSelected((restored || list[0]).id);
        if (!restored) setView("onboarding");
      })
      .catch((e) => setError(e.message));
    request<{ name: string }>("/api/me")
      .then((u) => setUser(u.name))
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    setWorkspace(null);
    setEvidence(null);
    if (previousSelected.current && previousSelected.current !== selected)
      setView("onboarding");
    previousSelected.current = selected;
    if (selected) void refresh().catch((e) => setError(e.message));
  }, [selected, refresh]);
  useEffect(() => {
    if (selected) {
      sessionStorage.setItem("auditor-engagement", selected);
      sessionStorage.setItem("auditor-view", view);
    }
  }, [selected, view]);
  useEffect(() => {
    if (!selected) return;
    const timer = setInterval(() => void refresh().catch(() => {}), 4000);
    return () => clearInterval(timer);
  }, [selected, refresh]);
  useEffect(() => {
    chatEnd.current?.scrollIntoView({ block: "nearest" });
  }, [workspace?.messages.length]);
  async function action(fn: () => Promise<unknown>, success = "") {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
      if (success) setNotice(success);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const base = `/api/engagements/${selected}`,
    version = workspace?.engagement.version || 1;
  const latest = (stage: string) =>
    workspace?.revisions.find((r) => r.stage === stage);
  const revision = latest(view),
    running =
      workspace?.jobs.filter((j) => ["queued", "running"].includes(j.status)) ||
      [];
  const failures =
    workspace?.jobs.filter(
      (j) =>
        ["failed", "interrupted"].includes(j.status) &&
        !workspace.jobs.some((n) => n.detail.retry_of === j.id),
    ) || [];
  const jobLabel = (job: Job) =>
    job.stage === "document"
      ? workspace?.documents.find((d) => d.id === job.detail.document_id)
          ?.filename || "Document processing"
      : LABELS[job.stage] || label(job.stage);
  const activeJob = running.find((j) => j.status === "running");
  const blockers =
    revision?.payload.findings?.filter(
      (f: Payload) => f.severity === "blocking",
    ).length || 0;
  async function upload(files: FileList | null) {
    if (!files) return;
    await action(async () => {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        await request(base + "/documents", { method: "POST", body: form });
      }
    }, "Files received. Extraction runs in the background.");
    if (uploader.current) uploader.current.value = "";
  }
  function openEdit(type: string, data: Payload = {}) {
    setEdit({ type, data, version });
  }
  async function openEvidence(id: string) {
    await action(async () =>
      setEvidence(await request<Evidence>(base + "/documents/" + id)),
    );
  }
  async function sendChat(e: FormEvent) {
    e.preventDefault();
    const message = chatText.trim();
    if (!message) return;
    await action(async () => {
      await post(base + "/chat", { message, version });
      setChatText("");
    });
  }
  const approvedCount = STAGES.filter(
    (s) => latest(s)?.status === "approved",
  ).length;
  return (
    <ErrorContext.Provider value={error}>
      <div className="shell">
        <aside className="rail">
          <div className="brand">
            <ShieldCheck size={25} />
            <strong>AI AUDITOR</strong>
          </div>
          <span className="rail-caption">WORKSPACE</span>
          <label className="sr-only" htmlFor="engagement">
            Select engagement
          </label>
          <select
            id="engagement"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="" disabled>
              Select engagement
            </option>
            {engagements.map((e) => (
              <option value={e.id} key={e.id}>
                {e.name}
              </option>
            ))}
          </select>
          <button className="new-engagement" onClick={() => setNewClient(true)}>
            <Plus size={15} /> New engagement
          </button>
          <span className="rail-caption">AUDIT PREPARATION</span>
          <nav>
            {STAGES.map((stage, index) => (
              <button
                disabled={!selected}
                key={stage}
                className={view === stage ? "active" : ""}
                onClick={() => setView(stage)}
              >
                <span
                  className={`step ${latest(stage)?.status === "approved" ? "complete" : ""}`}
                >
                  {latest(stage)?.status === "approved" ? (
                    <Check size={13} />
                  ) : (
                    String(index + 1).padStart(2, "0")
                  )}
                </span>
                {LABELS[stage]}
              </button>
            ))}
          </nav>
          <span className="rail-caption">ENGAGEMENT FILE</span>
          <nav>
            {[
              ["evidence", FileText],
              ["requests", FolderOpen],
              ["history", History],
            ].map(([key, Icon]) => {
              const id = key as string,
                Symbol = Icon as typeof FileText;
              return (
                <button
                  key={id}
                  disabled={!selected}
                  className={view === id ? "active" : ""}
                  onClick={() => setView(id)}
                >
                  <Symbol size={17} />
                  {LABELS[id]}
                </button>
              );
            })}
          </nav>
          <div className="rail-bottom">
            <div className="avatar">{user[0]}</div>
            <span>
              {user}
              <small>
                {config.local_auth
                  ? "Local development access"
                  : "Signed-in reviewer"}
              </small>
            </span>
            {!config.local_auth && (
              <button className="icon" aria-label="Sign out" onClick={signOut}>
                <LogOut size={16} />
              </button>
            )}
          </div>
        </aside>
        <div className="workspace">
          <header className="topbar">
            <div>
              <span className="breadcrumb">
                Engagements <ChevronRight size={13} />{" "}
                {workspace?.engagement.name || "Your workspace"}
              </span>
              <h1>{workspace ? LABELS[view] : "Your engagements"}</h1>
            </div>
            {workspace && (
              <div className="top-actions">
                <span className="fiscal">
                  YEAR END<strong>{workspace.engagement.period_end}</strong>
                </span>
                <button
                  disabled={busy}
                  onClick={() => uploader.current?.click()}
                >
                  <Upload size={16} /> Upload evidence
                </button>
                <input
                  ref={uploader}
                  type="file"
                  className="sr-only"
                  multiple
                  accept=".pdf,.xlsx,.csv,.png,.jpg,.jpeg"
                  onChange={(e) => void upload(e.target.files)}
                />
              </div>
            )}
          </header>
          {error && (
            <div className="banner error" role="alert">
              {error}
              <button
                className="icon"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={17} />
              </button>
            </div>
          )}
          {notice && (
            <div className="banner success" role="status">
              {notice}
              <button
                className="icon"
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                <X size={17} />
              </button>
            </div>
          )}
          {!workspace ? (
            <div className="welcome">
              {selected ? (
                <>
                  <Spinner />
                  <p>Loading engagement…</p>
                </>
              ) : (
                <>
                  <span className="eyebrow">YOUR ENGAGEMENT FILE</span>
                  <h2>Start with the evidence.</h2>
                  <p>
                    Create an engagement, upload its letter and financial
                    records, then review each prepared stage.
                  </p>
                  <button
                    className="primary"
                    onClick={() => setNewClient(true)}
                  >
                    <Plus size={17} /> Create engagement
                  </button>
                </>
              )}
            </div>
          ) : (
            <div className="work-grid">
              <main className="main-panel">
                <div className="progress-strip">
                  <span>
                    <i />
                    {approvedCount} of 5 stages approved
                  </span>
                  <span>{workspace.documents.length} source documents</span>
                  <span>
                    {
                      workspace.requests.filter((r) => r.status !== "satisfied")
                        .length
                    }{" "}
                    open requests
                  </span>
                </div>
                {!config.ai_configured && (
                  <div className="banner warning">
                    AI processing is not configured. Add the server's Groq key
                    before preparing documents.
                  </div>
                )}
                {running.length > 0 && (
                  <div className="job-bar">
                    <Spinner />
                    <div>
                      <strong>
                        {running.length} run{running.length > 1 ? "s" : ""} in
                        progress
                      </strong>
                      <p>
                        {activeJob && <strong>{jobLabel(activeJob)}: </strong>}
                        {activeJob?.message ||
                          "Waiting to process. You can continue reviewing saved work."}
                      </p>
                    </div>
                  </div>
                )}
                {failures.slice(0, 2).map((job) => (
                  <div className="banner warning" key={job.id}>
                    <div>
                      <strong>{jobLabel(job)} needs attention</strong>
                      <p>{job.message}</p>
                    </div>
                    <button
                      aria-label={`Retry ${jobLabel(job)}`}
                      disabled={busy || !!running.length}
                      onClick={() =>
                        void action(() =>
                          post(base + `/jobs/${job.id}/retry`, { version }),
                        )
                      }
                    >
                      Retry
                    </button>
                  </div>
                ))}
                {STAGES.includes(view) && (
                  <>
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">
                          STAGE {STAGES.indexOf(view) + 1} / 5
                        </span>
                        <h2>{LABELS[view]}</h2>
                      </div>
                      <div className="actions">
                        {revision && (
                          <>
                            <Status value={revision.status} />
                            <button
                              className="icon"
                              title="Download workpaper PDF"
                              aria-label="Download workpaper PDF"
                              onClick={() =>
                                void action(() =>
                                  download(
                                    base + `/revisions/${revision.id}/pdf`,
                                    `${view}.pdf`,
                                  ),
                                )
                              }
                            >
                              <ArrowDownToLine size={17} />
                            </button>
                          </>
                        )}
                        <button
                          className="primary"
                          disabled={
                            busy ||
                            !!running.length ||
                            (view !== "onboarding" &&
                              latest(STAGES[STAGES.indexOf(view) - 1])
                                ?.status !== "approved")
                          }
                          onClick={() =>
                            void action(() =>
                              post(base + `/stages/${view}/prepare`, {
                                version,
                              }),
                            )
                          }
                        >
                          {busy ? <Spinner /> : <RefreshCw size={15} />}{" "}
                          {revision ? "Prepare new draft" : "Prepare draft"}
                        </button>
                      </div>
                    </div>
                    {!revision ? (
                      <Empty title="No preparation yet">
                        {view === "onboarding"
                          ? "Upload and review the engagement letter, then prepare the client profile and evidence requests."
                          : "Approve the preceding stage and provide the required evidence to prepare this workpaper."}
                      </Empty>
                    ) : (
                      <>
                        {revision.status === "stale" && (
                          <div className="banner warning">
                            <div>
                              <strong>
                                This result needs to be prepared again.
                              </strong>
                              <p>{revision.stale_reason}</p>
                            </div>
                          </div>
                        )}
                        <StageContent
                          stage={view}
                          revision={revision}
                          workspace={workspace}
                          edit={openEdit}
                          openEvidence={openEvidence}
                        />
                        {!!revision.payload.findings?.length && (
                          <section className="card findings">
                            <div className="card-title">
                              <h3>Review findings</h3>
                              <span>{blockers} blocking</span>
                            </div>
                            {revision.payload.findings.map(
                              (f: Payload, i: number) => (
                                <div className="finding" key={i}>
                                  <Status value={f.severity} />
                                  <div>
                                    <p>{f.message}</p>
                                    <small>{f.source}</small>
                                    {f.document_id && (
                                      <button
                                        className="text-button"
                                        onClick={() =>
                                          void openEvidence(f.document_id)
                                        }
                                      >
                                        Open source
                                      </button>
                                    )}
                                  </div>
                                </div>
                              ),
                            )}
                          </section>
                        )}
                        <div className="approval-bar">
                          <div>
                            <strong>
                              {revision.status === "approved"
                                ? `Approved by ${revision.approved_by}`
                                : "Reviewer sign-off"}
                            </strong>
                            <p>
                              {revision.status === "approved"
                                ? dateTime(revision.approved_at)
                                : "Review the source, judgments, and open findings before relying on this stage."}
                            </p>
                          </div>
                          <button
                            className="primary"
                            disabled={
                              busy ||
                              !!running.length ||
                              revision.status !== "draft" ||
                              blockers > 0
                            }
                            onClick={() =>
                              void action(
                                () =>
                                  post(
                                    base + `/revisions/${revision.id}/approve`,
                                    { version },
                                  ),
                                "Approval recorded with your name and timestamp.",
                              )
                            }
                          >
                            <Check size={17} /> Approve stage
                          </button>
                        </div>
                        <p className="source-line">
                          Prepared {dateTime(revision.created_at)} · Revision{" "}
                          {revision.id.slice(0, 8)} ·{" "}
                          {revision.payload.sources
                            ?.map((s: unknown) =>
                              typeof s === "string"
                                ? s
                                : "Uploaded engagement evidence",
                            )
                            .join(" · ")}
                        </p>
                      </>
                    )}
                  </>
                )}
                {view === "evidence" && (
                  <>
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">ORIGINALS & EXTRACTION</span>
                        <h2>Evidence library</h2>
                      </div>
                      <span className="muted">
                        PDF, XLSX, CSV, images · {config.max_upload_mb} MB each
                      </span>
                    </div>
                    {workspace.documents.length ? (
                      <DataTable
                        headers={["Document", "Type", "Status", "Findings", ""]}
                        rows={workspace.documents.map((d) => [
                          <button
                            className="document-link"
                            onClick={() => void openEvidence(d.id)}
                          >
                            <FileText size={17} />
                            {d.filename}
                          </button>,
                          label(d.kind),
                          <Status value={d.status} />,
                          d.findings.length || "—",
                          <button
                            className="text-button"
                            onClick={() => void openEvidence(d.id)}
                          >
                            Review <ArrowRight size={14} />
                          </button>,
                        ])}
                      />
                    ) : (
                      <Empty title="Add your first source document">
                        Use Upload evidence to add the engagement letter and
                        financial records. Originals are preserved privately.
                      </Empty>
                    )}
                  </>
                )}
                {view === "requests" && (
                  <>
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">CLIENT COLLABORATION</span>
                        <h2>Client evidence requests</h2>
                      </div>
                      <button
                        onClick={() =>
                          void action(async () => {
                            const result = await post<{ token: string }>(
                              base + "/portal",
                              { version },
                            );
                            setPortalLink(
                              location.origin +
                                "/#upload=" +
                                encodeURIComponent(result.token),
                            );
                          })
                        }
                      >
                        <Plus size={16} /> Create upload link
                      </button>
                    </div>
                    <p className="muted">
                      Requests update with the client profile and account
                      mappings. Link and accept the relevant evidence before a
                      request is satisfied.
                    </p>
                    <DataTable
                      headers={["Request", "Status", "Why it is needed"]}
                      rows={workspace.requests.map((r) => [
                        <>
                          <strong>{r.title}</strong>
                          <small>{r.source}</small>
                        </>,
                        <Status value={r.status} />,
                        r.why,
                      ])}
                    />
                  </>
                )}
                {view === "history" && (
                  <>
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">SAVED DECISIONS</span>
                        <h2>Review history</h2>
                      </div>
                    </div>
                    <section className="card">
                      <h3>Workpaper revisions</h3>
                      <DataTable
                        headers={[
                          "Stage / revision",
                          "Prepared",
                          "Status",
                          "Reviewer",
                          "",
                        ]}
                        rows={workspace.revisions.map((r) => [
                          <>
                            {LABELS[r.stage]}
                            <small>{r.id.slice(0, 8)}</small>
                          </>,
                          dateTime(r.created_at),
                          <Status value={r.status} />,
                          r.approved_by || "Pending",
                          <button
                            className="text-button"
                            onClick={() =>
                              void action(() =>
                                download(
                                  base + `/revisions/${r.id}/pdf`,
                                  `${r.stage}-${r.id.slice(0, 8)}.pdf`,
                                ),
                              )
                            }
                          >
                            Download
                          </button>,
                        ])}
                      />
                    </section>
                    <section className="card">
                      <h3>Activity trail</h3>
                      {workspace.events.map((e) => (
                        <details className="event" key={e.id}>
                          <summary>
                            <strong>{label(e.action)}</strong>
                            <span>
                              {e.actor} · {dateTime(e.created_at)}
                            </span>
                          </summary>
                          <pre>{JSON.stringify(e.detail, null, 2)}</pre>
                        </details>
                      ))}
                    </section>
                  </>
                )}
              </main>
              <aside className="chat-panel">
                <div className="chat-head">
                  <MessageSquare size={18} />
                  <strong>Audit assistant</strong>
                  <span className="ai-dot" />
                </div>
                <p className="chat-intro">
                  Ask about evidence or request a correction. Approvals stay
                  with you.
                </p>
                <div className="chat-messages">
                  {!workspace.messages.length && (
                    <div className="chat-starter">
                      <span className="eyebrow">TRY ASKING</span>
                      {[
                        "Explain the active materiality rules.",
                        "Which documents still need attention?",
                      ].map((s) => (
                        <button key={s} onClick={() => setChatText(s)}>
                          {s}
                          <ArrowRight size={14} />
                        </button>
                      ))}
                      <p>
                        For changes, include your reason: “Set engagement risk
                        to high because…”
                      </p>
                    </div>
                  )}
                  {workspace.messages.map((m) => (
                    <div key={m.id} className={`message ${m.role}`}>
                      <span>
                        {m.role === "user" ? "YOU" : "AUDIT ASSISTANT"}
                      </span>
                      <p>{m.content}</p>
                      {m.detail?.applied && (
                        <small>
                          Draft correction recorded · approvals invalidated
                        </small>
                      )}
                    </div>
                  ))}
                  {busy && chatText && (
                    <div className="message">
                      <Spinner /> Preparing response…
                    </div>
                  )}
                  <div ref={chatEnd} />
                </div>
                <form className="chat-form" onSubmit={sendChat}>
                  <label htmlFor="chat-message" className="sr-only">
                    Ask the audit assistant
                  </label>
                  <textarea
                    id="chat-message"
                    placeholder="Ask a question or explain a correction…"
                    value={chatText}
                    onChange={(e) => setChatText(e.target.value)}
                    rows={3}
                  />
                  <div>
                    <small>Evidence-based drafts · human review required</small>
                    <button
                      className="primary icon"
                      aria-label="Send message"
                      disabled={busy || !chatText.trim()}
                    >
                      <Send size={16} />
                    </button>
                  </div>
                </form>
              </aside>
            </div>
          )}
        </div>
        {newClient && (
          <NewClient
            close={() => setNewClient(false)}
            submit={async (name, period_end) => {
              await action(async () => {
                const result = await post<Engagement>("/api/engagements", {
                  name,
                  period_end,
                });
                setEngagements((old) => [result, ...old]);
                setSelected(result.id);
                setNewClient(false);
              });
            }}
            busy={busy}
          />
        )}
        {evidence && workspace && (
          <EvidenceDialog
            document={evidence}
            workspace={workspace}
            busy={busy}
            close={() => setEvidence(null)}
            act={action}
            base={base}
            reload={async () =>
              setEvidence(
                await request<Evidence>(base + "/documents/" + evidence.id),
              )
            }
          />
        )}
        {edit && (
          <EditDialog
            edit={edit}
            close={() => setEdit(null)}
            busy={busy}
            submit={async (operation) => {
              await action(async () => {
                await post(base + "/corrections", {
                  version: edit.version,
                  operation,
                });
                setEdit(null);
              }, "Correction saved. Prepare the affected stage again.");
            }}
            workspace={workspace!}
          />
        )}
        {portalLink && (
          <Modal title="Client upload link" close={() => setPortalLink("")}>
            <p>
              This link expires in three days. It lets its holder view request
              titles and upload files for this engagement.
            </p>
            <label>
              Private upload link
              <input
                readOnly
                value={portalLink}
                onFocus={(e) => e.target.select()}
              />
            </label>
            <button
              className="primary"
              onClick={() =>
                void navigator.clipboard
                  .writeText(portalLink)
                  .then(() => setNotice("Upload link copied."))
                  .catch(() =>
                    setError("Select the link and copy it manually."),
                  )
              }
            >
              Copy link
            </button>
          </Modal>
        )}
      </div>
    </ErrorContext.Provider>
  );
}

function NewClient({
  close,
  submit,
  busy,
}: {
  close: () => void;
  submit: (name: string, end: string) => Promise<void>;
  busy: boolean;
}) {
  const [name, setName] = useState(""),
    [end, setEnd] = useState("2025-12-31");
  return (
    <Modal title="New engagement" close={close}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit(name, end);
        }}
      >
        <label>
          Client legal name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            minLength={2}
            placeholder="As stated in the engagement letter"
            autoFocus
          />
        </label>
        <label>
          Fiscal year end
          <input
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            required
          />
        </label>
        <p className="muted">
          The uploaded letter establishes the engagement profile. Missing facts
          remain open for review.
        </p>
        <button className="primary" disabled={busy}>
          {busy ? <Spinner /> : "Create engagement"}
        </button>
      </form>
    </Modal>
  );
}

function StageContent({
  stage,
  revision,
  workspace,
  edit,
  openEvidence,
}: {
  stage: string;
  revision: Revision;
  workspace: Workspace;
  edit: (type: string, data?: Payload) => void;
  openEvidence: (id: string) => Promise<void>;
}) {
  const p = revision.payload;
  if (stage === "onboarding")
    return (
      <>
        <section className="card">
          <div className="card-title">
            <h3>Client profile</h3>
            <button onClick={() => edit("profile")}>Correct profile</button>
          </div>
          <div className="profile-grid">
            {Object.entries(p.profile || {}).map(([key, value]) => (
              <div key={key}>
                <span>{label(key)}</span>
                <strong>
                  {value === null
                    ? "Not established"
                    : Array.isArray(value)
                      ? value.map(String).map(label).join(", ") ||
                        "None identified"
                      : typeof value === "boolean"
                        ? value
                          ? "Yes"
                          : "No"
                        : label(String(value))}
                </strong>
              </div>
            ))}
          </div>
          <p className="muted">{p.review_scope}</p>
        </section>
        <section className="card">
          <h3>Applicable methodology</h3>
          <div className="tags">
            {p.policy?.active?.map((s: string) => (
              <span key={s}>{s}</span>
            ))}
          </div>
          <details>
            <summary>Excluded or superseded guidance</summary>
            <ul>
              {p.policy?.excluded?.map((s: string) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </details>
        </section>
      </>
    );
  if (stage === "mapping")
    return (
      <section className="card">
        <div className="card-title">
          <h3>Trial balance mapping</h3>
          <span
            className={Number(p.net_balance) ? "error-text" : "success-text"}
          >
            Net balance {money(p.net_balance)}
          </span>
        </div>
        <DataTable
          headers={["Account", "Balance", "Proposed FSLI", "Basis", ""]}
          rows={(p.accounts || []).map((r: Payload) => [
            <>
              <strong>{r.number}</strong> {r.name}
              <small>{r.source}</small>
            </>,
            money(r.balance),
            r.fsli || <Status value="unresolved" />,
            <>
              {r.reason}
              <small>{r.method}</small>
            </>,
            <button className="text-button" onClick={() => edit("mapping", r)}>
              Edit
            </button>,
          ])}
        />
      </section>
    );
  if (stage === "planning")
    return (
      <>
        <div className="metric-grid">
          {[
            ["Overall materiality", p.materiality],
            ["Performance materiality", p.pm],
            ["Clearly trivial threshold", p.ctt],
          ].map(([key, value]) => (
            <div className="metric" key={key}>
              <span>{key}</span>
              <strong>{money(value)}</strong>
            </div>
          ))}
        </div>
        <section className="card">
          <div className="card-title">
            <h3>Planning judgment</h3>
            <div className="actions">
              <button onClick={() => edit("benchmark", p)}>
                Edit benchmark
              </button>
              <button onClick={() => edit("risk", p)}>Edit risk</button>
            </div>
          </div>
          <p className="formula">
            {p.benchmark} {money(p.benchmark_value)} <span>×</span>{" "}
            {(Number(p.rate) * 100).toFixed(2)}% <span>=</span>{" "}
            {money(p.materiality)}
          </p>
          <p>{p.rationale}</p>
          <p>{p.risk_rationale}</p>
          <Status value={p.engagement_risk} />
        </section>
        <section className="card">
          <h3>Account scope and risk</h3>
          <DataTable
            headers={["Account", "FSLI", "In scope", "Risk", "Basis"]}
            rows={(p.accounts || []).map((r: Payload) => [
              <>
                {r.number} {r.name}
              </>,
              r.fsli,
              r.in_scope ? "Yes" : "No",
              <button
                className="text-button"
                onClick={() => edit("risk", { ...r, account_number: r.number })}
              >
                {r.risk}
              </button>,
              r.scope_reason,
            ])}
          />
        </section>
      </>
    );
  if (stage === "sampling")
    return (
      <>
        <div className="metric-grid">
          <div className="metric">
            <span>Provided population</span>
            <strong>{money(p.population_value)}</strong>
          </div>
          <div className="metric">
            <span>Selected transactions</span>
            <strong>{p.selections?.length || 0}</strong>
          </div>
          <div className="metric">
            <span>Total operating expenses</span>
            <strong>{money(p.total_opex)}</strong>
          </div>
        </div>
        <section className="card">
          <h3>Reconcile before selecting</h3>
          <DataTable
            headers={["Account", "GL amount", "TB amount", "Difference"]}
            rows={(p.reconciliation || []).map((r: Payload) => [
              r.account_number,
              money(r.gl),
              money(r.tb),
              <span className={r.ties ? "success-text" : "error-text"}>
                {money(r.difference)}
              </span>,
            ])}
          />
          {p.groups?.map((g: Payload) => (
            <p className="formula small" key={g.risk}>
              {label(g.risk)} risk · {g.certain_count} individually significant
              + min(available, ceil({money(g.remaining_value)} / {money(g.pm)} ×{" "}
              {g.factor})) = {g.remainder_count} remainder selections, plus
              mandatory items.
            </p>
          ))}
        </section>
        <section className="card">
          <h3>Selected items</h3>
          <DataTable
            headers={["Transaction", "Amount", "Why selected"]}
            footer={[
              "Selected total",
              money(
                totalAmount((p.selections || []).map((r: Payload) => r.amount)),
              ),
              `${p.selections?.length || 0} transactions`,
            ]}
            rows={(p.selections || []).map((r: Payload) => [
              <>
                <strong>{r.ref || "No reference"}</strong>
                <small>
                  {r.date} · {r.counterparty} · {r.account_number}
                </small>
              </>,
              money(r.amount),
              <>
                {r.selection_reasons.join("; ")}
                <small>{r.source}</small>
              </>,
            ])}
          />
        </section>
      </>
    );
  return (
    <>
      <div className="metric-grid">
        <div className="metric">
          <span>Exceptions</span>
          <strong className={p.exception_count ? "error-text" : ""}>
            {p.exception_count || 0}
          </strong>
        </div>
        <div className="metric">
          <span>Unresolved</span>
          <strong>{p.unresolved_count || 0}</strong>
        </div>
        <div className="metric">
          <span>Known absolute difference</span>
          <strong>{money(p.known_absolute_error)}</strong>
        </div>
      </div>
      <section className="card">
        <h3>Proposed conclusion</h3>
        <p>{p.conclusion}</p>
      </section>
      {(p.results || []).map((r: Payload) => (
        <section className="card result" key={r.transaction.id}>
          <div className="card-title">
            <div>
              <h3>
                {r.transaction.ref || "Unreferenced item"}{" "}
                <span className="muted">· {money(r.transaction.amount)}</span>
              </h3>
              <small>
                {r.transaction.counterparty} · {r.transaction.account_number} ·{" "}
                {r.transaction.date}
              </small>
            </div>
            <Status value={r.status} />
          </div>
          {r.match_issue && <p className="error-text">{r.match_issue}</p>}
          <DataTable
            headers={["Assertion", "Result", "Evidence / reasoning"]}
            rows={Object.entries(r.checks || {}).map(([key, value]) => {
              const c = value as Payload;
              return [label(key), <Status value={c.status} />, c.reason];
            })}
          />
          <div className="result-actions">
            {r.document_id && (
              <button onClick={() => void openEvidence(r.document_id)}>
                Open invoice
              </button>
            )}
            <button
              onClick={() =>
                edit("invoice_link", { selection_id: r.transaction.id })
              }
            >
              Link invoice
            </button>
            {r.status !== "clean" && (
              <button
                onClick={() =>
                  edit("disposition", { selection_id: r.transaction.id })
                }
              >
                Record follow-up
              </button>
            )}
          </div>
          {r.disposition_note && (
            <p className="muted">
              Reviewer disposition:{" "}
              {r.disposition_note.follow_up || String(r.disposition_note)}
            </p>
          )}
        </section>
      ))}
      {!p.results?.length && (
        <Empty title="No test results">
          Provide the selected invoices and prepare this stage.
        </Empty>
      )}
    </>
  );
}

function EvidenceDialog({
  document: doc,
  workspace,
  close,
  busy,
  act,
  base,
  reload,
}: {
  document: Evidence;
  workspace: Workspace;
  close: () => void;
  busy: boolean;
  act: (fn: () => Promise<unknown>, success?: string) => Promise<void>;
  base: string;
  reload: () => Promise<void>;
}) {
  const [note, setNote] = useState(""),
    [field, setField] = useState("entity"),
    [value, setValue] = useState(""),
    [source, setSource] = useState(""),
    [snapshot] = useState(workspace.engagement.version);
  const [requestIds, setRequestIds] = useState<string[]>(
    doc.extracted?.request_ids || [],
  );
  const facts = doc.extracted?.facts || {},
    editable = doc.status !== "processing" && !!doc.extracted;
  const allowedRequests = workspace.requests.filter((r) => r.kind === doc.kind);
  async function review(action: string) {
    await act(async () => {
      await post(base + `/documents/${doc.id}/review`, {
        action,
        note,
        version: snapshot,
      });
      close();
    }, "Document review recorded.");
  }
  async function correct(e: FormEvent) {
    e.preventDefault();
    let parsed: unknown = value;
    if (
      [
        "issuer",
        "first_year",
        "professional_services",
        "detailed_matter",
        "full_period_explicit",
        "signed",
        "computational_support",
        "lot_expiry_present",
      ].includes(field)
    )
      parsed = value === "true" ? true : value === "false" ? false : null;
    if (["industries", "related_parties"].includes(field))
      parsed = value
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean);
    if (value.trim() === "null") parsed = null;
    await act(async () => {
      await post(base + `/documents/${doc.id}/facts`, {
        version: snapshot,
        changes: { [field]: parsed },
        reason: note,
        source_reference: source,
      });
      close();
    }, "Extracted fact corrected. Review the updated document again.");
  }
  return (
    <Modal title={doc.filename} close={close} wide>
      <div className="evidence-toolbar">
        <Status value={doc.status} />
        <span>{label(doc.kind)}</span>
        <button
          onClick={() =>
            void act(() =>
              download(base + `/documents/${doc.id}/source`, doc.filename),
            )
          }
        >
          <ArrowDownToLine size={16} /> Original file
        </button>
      </div>
      <div className="evidence-columns">
        <section>
          <h3>Extracted facts</h3>
          <DataTable
            headers={["Field", "Value"]}
            rows={Object.entries(facts)
              .filter(([k]) => !["source_quotes", "uncertainties"].includes(k))
              .map(([key, value]) => [
                label(key),
                value === null
                  ? "Not established"
                  : ["amount", "detail_total"].includes(key) &&
                      Number.isFinite(Number(value))
                    ? money(value)
                    : typeof value === "object"
                      ? JSON.stringify(value)
                      : String(value),
              ])}
          />
          <details>
            <summary>Quotes and page transcription</summary>
            {Object.entries(facts.source_quotes || {})
              .filter(([, v]) => v)
              .map(([k, v]) => (
                <p key={k}>
                  <strong>{label(k)}:</strong> {String(v)}
                </p>
              ))}
            {doc.extracted?.pages?.map((p: Payload) => (
              <div key={p.page}>
                <h4>
                  Page {p.page} · {p.method}
                </h4>
                <pre>{p.text}</pre>
              </div>
            ))}
          </details>
          {doc.extracted?.source_rows?.map((sheet: Payload) => (
            <details key={sheet.sheet}>
              <summary>{sheet.sheet} · source rows (first 300)</summary>
              <div className="table-wrap">
                <table>
                  <tbody>
                    {sheet.rows.map((row: unknown[], i: number) => (
                      <tr key={i}>
                        <th>{i + 1}</th>
                        {row.map((v, j) => (
                          <td key={j}>{String(v ?? "")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          ))}
        </section>
        <section className="evidence-review">
          <h3>Acceptance review</h3>
          {doc.findings.map((f, i) => (
            <div className="finding" key={i}>
              <Status value={f.severity} />
              <div>
                <p>{f.message}</p>
                <small>{f.source}</small>
              </div>
            </div>
          ))}
          {!doc.findings.length && (
            <p className="success-text">
              No automated acceptance findings. Review the original before
              accepting.
            </p>
          )}
          <label>
            Reviewer note
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder="What you checked, or why you are returning this document…"
            />
          </label>
          <div className="actions">
            <button
              className="primary"
              disabled={
                busy ||
                !editable ||
                note.length < 8 ||
                doc.findings.some((f) => f.severity === "blocking") ||
                ["accepted", "superseded"].includes(doc.status)
              }
              onClick={() => void review("accept")}
            >
              Accept evidence
            </button>
            <button
              disabled={
                busy ||
                !editable ||
                note.length < 8 ||
                doc.status === "superseded"
              }
              onClick={() => void review("return")}
            >
              Return
            </button>
            <button
              disabled={
                busy ||
                !editable ||
                note.length < 8 ||
                doc.status === "superseded"
              }
              onClick={() => void review("supersede")}
            >
              Supersede
            </button>
          </div>
          <small>
            Reviewed by {doc.reviewed_by || "—"} · {dateTime(doc.reviewed_at)}
          </small>
          {editable && (
            <details>
              <summary>Correct an extracted fact</summary>
              <p className="muted">
                Use this only when the source supports a different value.
                Missing evidence needs a corrected source document.
              </p>
              <form onSubmit={correct}>
                <label>
                  Field
                  <select
                    value={field}
                    onChange={(e) => setField(e.target.value)}
                  >
                    {Object.keys(facts)
                      .filter(
                        (k) => !["source_quotes", "uncertainties"].includes(k),
                      )
                      .map((k) => (
                        <option key={k} value={k}>
                          {label(k)}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Correct value
                  <input
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    required
                    placeholder="Unknown: null; booleans: true / false; lists: comma-separated"
                  />
                </label>
                <label>
                  Source page / cell and supporting quote
                  <input
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                    required
                    minLength={3}
                  />
                </label>
                <button disabled={busy || note.length < 8}>
                  Save fact correction
                </button>
              </form>
            </details>
          )}
          {!!allowedRequests.length && (
            <details>
              <summary>Link to client requests</summary>
              <p className="muted">
                Choose only requests this document actually supports. Record the
                matching basis in the reviewer note.
              </p>
              {allowedRequests.map((r) => (
                <label className="checkbox" key={r.id}>
                  <input
                    type="checkbox"
                    checked={requestIds.includes(r.id)}
                    onChange={(e) =>
                      setRequestIds((ids) =>
                        e.target.checked
                          ? [...ids, r.id]
                          : ids.filter((id) => id !== r.id),
                      )
                    }
                  />
                  {r.title}
                </label>
              ))}
              <button
                disabled={busy || note.length < 8}
                onClick={() =>
                  void act(async () => {
                    await post(base + `/documents/${doc.id}/requests`, {
                      version: snapshot,
                      request_ids: requestIds,
                      note,
                    });
                    await reload();
                    close();
                  }, "Request links recorded.")
                }
              >
                Save request links
              </button>
            </details>
          )}
        </section>
      </div>
    </Modal>
  );
}

function EditDialog({
  edit,
  close,
  busy,
  submit,
  workspace,
}: {
  edit: { type: string; data: Payload };
  close: () => void;
  busy: boolean;
  submit: (operation: Payload) => Promise<void>;
  workspace: Workspace;
}) {
  const [reason, setReason] = useState(""),
    [value, setValue] = useState<string>(
      edit.data.fsli ||
        edit.data.risk ||
        edit.data.engagement_risk ||
        edit.data.benchmark ||
        "",
    ),
    [rate, setRate] = useState(
      edit.data.rate ? String(Number(edit.data.rate) * 100) : "",
    ),
    [field, setField] = useState("stage"),
    [followUp, setFollowUp] = useState(""),
    [doc, setDoc] = useState("");
  async function save(e: FormEvent) {
    e.preventDefault();
    let operation: Payload = { type: edit.type, reason };
    if (edit.type === "mapping")
      operation = {
        ...operation,
        account_number: edit.data.number,
        fsli: value,
      };
    if (edit.type === "risk")
      operation = {
        ...operation,
        risk: value,
        account_number: edit.data.account_number || null,
      };
    if (edit.type === "benchmark")
      operation = {
        ...operation,
        benchmark: value,
        rate: rate ? Number(rate) / 100 : null,
      };
    if (edit.type === "profile") {
      let result: unknown = value;
      if (["issuer", "first_year"].includes(field)) result = value === "true";
      if (["industries", "related_parties"].includes(field))
        result = value
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
      operation = { ...operation, field, value: result };
    }
    if (edit.type === "invoice_link")
      operation = {
        ...operation,
        selection_id: edit.data.selection_id,
        document_id: doc,
      };
    if (edit.type === "disposition")
      operation = {
        ...operation,
        selection_id: edit.data.selection_id,
        disposition: value,
        follow_up: followUp,
        evidence_document_ids: doc ? [doc] : [],
      };
    await submit(operation);
  }
  const options =
    edit.type === "mapping"
      ? FSLIS
      : edit.type === "risk"
        ? ["low", "moderate", "high", "significant"]
        : edit.type === "benchmark"
          ? ["Revenue", "Total assets", "Equity", "Pre-tax income"]
          : edit.type === "disposition"
            ? [
                "client_correction_obtained",
                "additional_evidence_obtained",
                "unadjusted_exception",
              ]
            : null;
  return (
    <Modal title={"Correct " + label(edit.type)} close={close}>
      <form onSubmit={save}>
        {edit.data.number && (
          <p>
            Account {edit.data.number}: {edit.data.name}
          </p>
        )}
        {options && (
          <label>
            Value
            <select
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
            >
              <option value="" disabled>
                Select…
              </option>
              {options.map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          </label>
        )}
        {edit.type === "benchmark" && (
          <label>
            Percentage (leave blank for policy guideline)
            <input
              type="number"
              min="0.001"
              max="100"
              step="any"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
            />
          </label>
        )}
        {edit.type === "profile" && (
          <>
            <label>
              Profile field
              <select
                value={field}
                onChange={(e) => {
                  setField(e.target.value);
                  setValue("");
                }}
              >
                {[
                  "service",
                  "framework",
                  "issuer",
                  "first_year",
                  "stage",
                  "industries",
                  "related_parties",
                  "prior_benchmark",
                ].map((s) => (
                  <option key={s} value={s}>
                    {label(s)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Value
              {["issuer", "first_year"].includes(field) ? (
                <select
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  required
                >
                  <option value="" disabled>
                    Select…
                  </option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              ) : (
                <input
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  required
                  placeholder={
                    ["issuer", "first_year"].includes(field)
                      ? "true or false"
                      : field === "industries"
                        ? "food_beverage, wholesale, cannabis, other"
                        : field === "stage"
                          ? "growth or mature"
                          : ""
                  }
                />
              )}
            </label>
          </>
        )}
        {["invoice_link", "disposition"].includes(edit.type) && (
          <label>
            Supporting document
            <select
              value={doc}
              onChange={(e) => setDoc(e.target.value)}
              required={edit.type === "invoice_link"}
            >
              <option value="">Select evidence…</option>
              {workspace.documents
                .filter(
                  (d) =>
                    d.status !== "superseded" &&
                    (edit.type !== "invoice_link" || d.kind === "invoice"),
                )
                .map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename}
                  </option>
                ))}
            </select>
          </label>
        )}
        {edit.type === "disposition" && (
          <label>
            Client follow-up and conclusion
            <textarea
              value={followUp}
              onChange={(e) => setFollowUp(e.target.value)}
              required
              minLength={8}
            />
          </label>
        )}
        <label>
          Reason for this correction
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            minLength={8}
            rows={3}
          />
        </label>
        <p className="muted">
          This creates a draft correction and invalidates affected approvals.
          Original evidence and earlier workpapers stay in the history.
        </p>
        <button className="primary" disabled={busy}>
          {busy ? <Spinner /> : "Save correction"}
        </button>
      </form>
    </Modal>
  );
}

function ClientPortal({ token }: { token: string }) {
  const [data, setData] = useState<Payload | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  useEffect(() => {
    request<Payload>("/api/portal", { headers: { "X-Portal-Token": token } })
      .then(setData)
      .catch((e) => setError(e.message));
  }, [token]);
  async function upload(files: FileList | null) {
    if (!files) return;
    setBusy(true);
    setError("");
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        await request("/api/portal/documents", {
          method: "POST",
          headers: { "X-Portal-Token": token },
          body: form,
        });
      }
      setNotice(
        "Files received. Your auditor will review them and follow up on any questions.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="portal">
      <div className="brand">
        <ShieldCheck size={26} /> AI AUDITOR
      </div>
      <main>
        <span className="eyebrow">CLIENT DOCUMENT UPLOAD</span>
        <h1>{data?.name || "Private upload portal"}</h1>
        {error && (
          <div className="banner error" role="alert">
            {error}
          </div>
        )}
        {notice && <div className="banner success">{notice}</div>}
        {data && (
          <>
            <p>
              Year ended {data.period_end}. Upload one document type per file.
              Your auditor reviews every submission.
            </p>
            <label className="upload-zone">
              <Upload size={24} />
              <strong>{busy ? "Uploading…" : "Select files to upload"}</strong>
              <span>
                PDF, XLSX, CSV, PNG, JPG · up to {data.max_upload_mb} MB each
              </span>
              <input
                type="file"
                multiple
                accept=".pdf,.xlsx,.csv,.png,.jpg,.jpeg"
                disabled={busy}
                onChange={(e) => void upload(e.target.files)}
              />
            </label>
            <DataTable
              headers={["Requested evidence", "Status"]}
              rows={data.requests.map((r: Payload) => [
                r.title,
                <Status value={r.status} />,
              ])}
            />
          </>
        )}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
