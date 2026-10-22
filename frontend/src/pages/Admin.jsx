import { useEffect, useState } from "react";
import Layout from "../components/Layout";
import Modal from "../components/Modal";
import { api, ApiError } from "../api/client";

export default function Admin() {
  const [tab, setTab] = useState("wallets");
  const [wallets, setWallets] = useState(null);
  const [users, setUsers] = useState(null);
  const [error, setError] = useState("");
  const [modal, setModal] = useState(null);

  const loadWallets = async () => {
    try {
      setWallets(await api.adminListWallets());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load wallets.");
    }
  };
  const loadUsers = async () => {
    try {
      setUsers(await api.adminListUsers());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load users.");
    }
  };

  useEffect(() => {
    loadWallets();
    loadUsers();
  }, []);

  return (
    <Layout>
      <div className="page-header">
        <div className="eyebrow">Administration</div>
        <h1>Admin console</h1>
        <p>Manage users and wallets. Every action here is written to the audit log.</p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="nav-links" style={{ flexDirection: "row", marginBottom: 20, gap: 8 }}>
        <button
          className={"btn btn-sm " + (tab === "wallets" ? "btn-primary" : "btn-secondary")}
          onClick={() => setTab("wallets")}
        >
          Wallets
        </button>
        <button
          className={"btn btn-sm " + (tab === "users" ? "btn-primary" : "btn-secondary")}
          onClick={() => setTab("users")}
        >
          Users
        </button>
      </div>

      {tab === "wallets" && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {wallets === null ? (
            <div className="loading-screen" style={{ minHeight: 200 }}>
              LOADING…
            </div>
          ) : (
            <table className="ledger">
              <thead>
                <tr>
                  <th>Wallet ID</th>
                  <th>Currency</th>
                  <th>Status</th>
                  <th style={{ textAlign: "right" }}>Balance</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {wallets.map((w) => (
                  <tr key={w.id}>
                    <td className="ref">{w.id}</td>
                    <td>{w.currency}</td>
                    <td>
                      <span className={"status-pill " + (w.status === "ACTIVE" ? "completed" : "failed")}>
                        {w.status}
                      </span>
                    </td>
                    <td className="amount">{parseFloat(w.balance).toFixed(2)}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {w.status === "FROZEN" ? (
                        <button className="btn btn-secondary btn-sm" onClick={() => setModal({ type: "unfreeze", wallet: w })}>
                          Unfreeze
                        </button>
                      ) : (
                        <button className="btn btn-danger btn-sm" onClick={() => setModal({ type: "freeze", wallet: w })}>
                          Freeze
                        </button>
                      )}{" "}
                      <button className="btn btn-secondary btn-sm" onClick={() => setModal({ type: "adjust", wallet: w })}>
                        Adjust
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "users" && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {users === null ? (
            <div className="loading-screen" style={{ minHeight: 200 }}>
              LOADING…
            </div>
          ) : (
            <table className="ledger">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.name}</td>
                    <td style={{ color: "var(--text-muted)" }}>{u.email}</td>
                    <td>{u.role}</td>
                    <td>
                      <span className={"status-pill " + (u.status === "ACTIVE" ? "completed" : "failed")}>
                        {u.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {modal?.type === "freeze" && (
        <ReasonModal
          title={`Freeze wallet ${modal.wallet.currency}`}
          confirmLabel="Freeze wallet"
          confirmClass="btn-danger"
          onClose={() => setModal(null)}
          onSubmit={(reason) => api.adminFreezeWallet(modal.wallet.id, reason)}
          onDone={() => { setModal(null); loadWallets(); }}
        />
      )}
      {modal?.type === "unfreeze" && (
        <ReasonModal
          title={`Unfreeze wallet ${modal.wallet.currency}`}
          confirmLabel="Unfreeze wallet"
          confirmClass="btn-primary"
          onClose={() => setModal(null)}
          onSubmit={(reason) => api.adminUnfreezeWallet(modal.wallet.id, reason)}
          onDone={() => { setModal(null); loadWallets(); }}
        />
      )}
      {modal?.type === "adjust" && (
        <AdjustModal wallet={modal.wallet} onClose={() => setModal(null)} onDone={() => { setModal(null); loadWallets(); }} />
      )}
    </Layout>
  );
}

function ReasonModal({ title, confirmLabel, confirmClass, onClose, onSubmit, onDone }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await onSubmit(reason);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={title} onClose={onClose}>
      {error && <div className="alert alert-error">{error}</div>}
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="reason">Reason</label>
          <input
            id="reason"
            type="text"
            required
            minLength={5}
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Describe why, for the audit log"
          />
        </div>
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary btn-block" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className={"btn btn-block " + confirmClass} disabled={submitting}>
            {submitting ? <span className="spinner" /> : confirmLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function AdjustModal({ wallet, onClose, onDone }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api.adminAdjustBalance(wallet.id, Number(amount), reason);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Adjustment failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={`Adjust balance — ${wallet.currency} wallet`} onClose={onClose}>
      {error && <div className="alert alert-error">{error}</div>}
      <p className="hint" style={{ marginBottom: 16 }}>
        Current balance: <span className="mono">{parseFloat(wallet.balance).toFixed(2)}</span>
      </p>
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="amount">Amount (positive to credit, negative to debit)</label>
          <input
            id="amount"
            type="number"
            step="0.01"
            required
            autoFocus
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="e.g. 500 or -200"
          />
        </div>
        <div className="field">
          <label htmlFor="reason">Reason</label>
          <input
            id="reason"
            type="text"
            required
            minLength={10}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Manual correction after payment investigation"
          />
        </div>
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary btn-block" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? <span className="spinner" /> : "Apply adjustment"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
