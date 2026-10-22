import { useEffect, useState } from "react";
import Layout from "../components/Layout";
import Modal from "../components/Modal";
import { api, ApiError } from "../api/client";

const CURRENCIES = ["USD", "PKR", "EUR", "GBP", "AED", "SAR"];

function uuidLike() {
  // Simple client-generated idempotency key so retried clicks / double
  // network requests never double-process the same operation.
  return "web-" + crypto.randomUUID();
}

export default function Dashboard() {
  const [wallets, setWallets] = useState(null);
  const [error, setError] = useState("");
  const [modal, setModal] = useState(null); // { type: 'create'|'deposit'|'withdraw'|'transfer', wallet }

  const loadWallets = async () => {
    try {
      const data = await api.listWallets();
      setWallets(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load wallets.");
    }
  };

  useEffect(() => {
    loadWallets();
  }, []);

  const totalsByCurrency = (wallets || []).reduce((acc, w) => {
    acc[w.currency] = (acc[w.currency] || 0) + parseFloat(w.balance);
    return acc;
  }, {});

  return (
    <Layout>
      <div className="page-header">
        <div className="eyebrow">Overview</div>
        <h1>Your wallets</h1>
        <p>Balances, deposits, withdrawals, and transfers — all in one place.</p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {Object.keys(totalsByCurrency).length > 0 && (
        <div className="stats-row">
          {Object.entries(totalsByCurrency).map(([cur, total]) => (
            <div className="stat-box" key={cur}>
              <div className="label">{cur} total</div>
              <div className="value">{total.toFixed(2)}</div>
            </div>
          ))}
        </div>
      )}

      {wallets === null ? (
        <div className="loading-screen" style={{ minHeight: 200 }}>
          LOADING…
        </div>
      ) : wallets.length === 0 ? (
        <div className="card empty-state">
          <div className="icon">◇</div>
          <p>You don't have any wallets yet.</p>
          <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={() => setModal({ type: "create" })}>
            Create your first wallet
          </button>
        </div>
      ) : (
        <>
          <div className="wallets-grid">
            {wallets.map((w) => (
              <div key={w.id} className={"wallet-card" + (w.status === "FROZEN" ? " frozen" : "")}>
                <span className={"status-badge " + w.status.toLowerCase()}>{w.status}</span>
                <div className="currency-tag">{w.currency} WALLET</div>
                <div className="balance">{parseFloat(w.balance).toFixed(2)}</div>
                <div
                  className="mono hint"
                  style={{ marginTop: 8, wordBreak: "break-all", cursor: "pointer" }}
                  title="Click to copy wallet ID"
                  onClick={() => navigator.clipboard?.writeText(w.id)}
                >
                  ID: {w.id}
                </div>
                <div className="wallet-actions">
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={w.status !== "ACTIVE"}
                    onClick={() => setModal({ type: "deposit", wallet: w })}
                  >
                    Deposit
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={w.status !== "ACTIVE"}
                    onClick={() => setModal({ type: "withdraw", wallet: w })}
                  >
                    Withdraw
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={w.status !== "ACTIVE"}
                    onClick={() => setModal({ type: "transfer", wallet: w })}
                  >
                    Transfer
                  </button>
                </div>
              </div>
            ))}
          </div>
          <button className="btn btn-secondary" style={{ marginTop: 20 }} onClick={() => setModal({ type: "create" })}>
            + Add another wallet
          </button>
        </>
      )}

      {modal?.type === "create" && (
        <CreateWalletModal
          existingCurrencies={(wallets || []).map((w) => w.currency)}
          onClose={() => setModal(null)}
          onDone={() => {
            setModal(null);
            loadWallets();
          }}
        />
      )}
      {modal?.type === "deposit" && (
        <DepositModal wallet={modal.wallet} onClose={() => setModal(null)} onDone={() => { setModal(null); loadWallets(); }} />
      )}
      {modal?.type === "withdraw" && (
        <WithdrawModal wallet={modal.wallet} onClose={() => setModal(null)} onDone={() => { setModal(null); loadWallets(); }} />
      )}
      {modal?.type === "transfer" && (
        <TransferModal wallet={modal.wallet} wallets={wallets} onClose={() => setModal(null)} onDone={() => { setModal(null); loadWallets(); }} />
      )}
    </Layout>
  );
}

function CreateWalletModal({ existingCurrencies, onClose, onDone }) {
  const [currency, setCurrency] = useState(CURRENCIES.find((c) => !existingCurrencies.includes(c)) || "USD");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api.createWallet(currency);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create wallet.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="New wallet" onClose={onClose}>
      {error && <div className="alert alert-error">{error}</div>}
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="currency">Currency</label>
          <select id="currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {CURRENCIES.map((c) => (
              <option key={c} value={c} disabled={existingCurrencies.includes(c)}>
                {c} {existingCurrencies.includes(c) ? "(already have one)" : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary btn-block" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? <span className="spinner" /> : "Create"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function DepositModal({ wallet, onClose, onDone }) {
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [key] = useState(uuidLike());

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api.deposit(wallet.id, Number(amount), key);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Deposit failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={`Deposit to ${wallet.currency} wallet`} onClose={onClose}>
      {error && <div className="alert alert-error">{error}</div>}
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="amount">Amount ({wallet.currency})</label>
          <input
            id="amount"
            type="number"
            step="0.01"
            min="0.01"
            required
            autoFocus
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
          />
        </div>
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary btn-block" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? <span className="spinner" /> : "Deposit"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function WithdrawModal({ wallet, onClose, onDone }) {
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [key] = useState(uuidLike());

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api.withdraw(wallet.id, Number(amount), key);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Withdrawal failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={`Withdraw from ${wallet.currency} wallet`} onClose={onClose}>
      {error && <div className="alert alert-error">{error}</div>}
      <p className="hint" style={{ marginBottom: 16 }}>
        Available balance: <span className="mono">{parseFloat(wallet.balance).toFixed(2)}</span>
      </p>
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="wamount">Amount ({wallet.currency})</label>
          <input
            id="wamount"
            type="number"
            step="0.01"
            min="0.01"
            required
            autoFocus
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
          />
        </div>
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary btn-block" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? <span className="spinner" /> : "Withdraw"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function TransferModal({ wallet, wallets, onClose, onDone }) {
  const [recipientWalletId, setRecipientWalletId] = useState("");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [key] = useState(uuidLike());

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api.transfer(wallet.id, recipientWalletId, Number(amount), description || undefined, key);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Transfer failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={`Transfer from ${wallet.currency} wallet`} onClose={onClose}>
      {error && <div className="alert alert-error">{error}</div>}
      <p className="hint" style={{ marginBottom: 16 }}>
        Available balance: <span className="mono">{parseFloat(wallet.balance).toFixed(2)}</span>
      </p>
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="recipient">Recipient wallet ID</label>
          <input
            id="recipient"
            type="text"
            required
            value={recipientWalletId}
            onChange={(e) => setRecipientWalletId(e.target.value)}
            placeholder="Paste the recipient's wallet ID"
          />
          <div className="hint">Ask the recipient for their {wallet.currency} wallet ID from their dashboard.</div>
        </div>
        <div className="field">
          <label htmlFor="tamount">Amount ({wallet.currency})</label>
          <input
            id="tamount"
            type="number"
            step="0.01"
            min="0.01"
            required
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
          />
        </div>
        <div className="field">
          <label htmlFor="description">Note (optional)</label>
          <input
            id="description"
            type="text"
            maxLength={500}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Payment for services"
          />
        </div>
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary btn-block" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? <span className="spinner" /> : "Send transfer"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
