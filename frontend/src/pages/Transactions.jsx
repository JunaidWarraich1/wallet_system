import { useEffect, useState } from "react";
import Layout from "../components/Layout";
import { api, ApiError } from "../api/client";

const TYPES = ["", "DEPOSIT", "WITHDRAWAL", "TRANSFER", "ADJUSTMENT"];
const STATUSES = ["", "PENDING", "COMPLETED", "FAILED", "CANCELLED"];

export default function Transactions() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ type: "", status: "", reference: "", page: 1 });

  const load = async () => {
    try {
      const result = await api.listTransactions({ ...filters, page_size: 20 });
      setData(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load transactions.");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <Layout>
      <div className="page-header">
        <div className="eyebrow">History</div>
        <h1>Transactions</h1>
        <p>Every deposit, withdrawal, and transfer on your wallets.</p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="filters-bar">
        <select
          value={filters.type}
          onChange={(e) => setFilters((f) => ({ ...f, type: e.target.value, page: 1 }))}
        >
          {TYPES.map((t) => (
            <option key={t} value={t}>
              {t || "All types"}
            </option>
          ))}
        </select>
        <select
          value={filters.status}
          onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value, page: 1 }))}
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s || "All statuses"}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Search reference…"
          value={filters.reference}
          onChange={(e) => setFilters((f) => ({ ...f, reference: e.target.value, page: 1 }))}
        />
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {data === null ? (
          <div className="loading-screen" style={{ minHeight: 200 }}>
            LOADING…
          </div>
        ) : data.items.length === 0 ? (
          <div className="empty-state">
            <div className="icon">—</div>
            <p>No transactions match these filters.</p>
          </div>
        ) : (
          <table className="ledger">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Type</th>
                <th>Status</th>
                <th>Description</th>
                <th>Date</th>
                <th style={{ textAlign: "right" }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((tx) => (
                <tr key={tx.id}>
                  <td className="ref">{tx.reference}</td>
                  <td>
                    <span className={"type-stamp " + tx.type.toLowerCase()}>{tx.type}</span>
                  </td>
                  <td>
                    <span className={"status-pill " + tx.status.toLowerCase()}>{tx.status}</span>
                  </td>
                  <td style={{ color: "var(--text-muted)" }}>{tx.description || "—"}</td>
                  <td style={{ color: "var(--text-muted)" }}>{new Date(tx.created_at).toLocaleString()}</td>
                  <td className={"amount " + (tx.type === "DEPOSIT" ? "positive" : "")}>
                    {tx.type === "WITHDRAWAL" || (tx.type === "TRANSFER" && tx.source_wallet_id) ? "−" : "+"}
                    {parseFloat(tx.amount).toFixed(2)} {tx.currency}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {data && totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 20 }}>
          <button
            className="btn btn-secondary btn-sm"
            disabled={filters.page <= 1}
            onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}
          >
            Previous
          </button>
          <span style={{ alignSelf: "center", fontSize: 13, color: "var(--text-muted)" }}>
            Page {filters.page} of {totalPages}
          </span>
          <button
            className="btn btn-secondary btn-sm"
            disabled={filters.page >= totalPages}
            onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}
          >
            Next
          </button>
        </div>
      )}
    </Layout>
  );
}
