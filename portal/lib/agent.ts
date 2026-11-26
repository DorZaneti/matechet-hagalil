import "server-only";

// Address of the agent service on Render, e.g. https://matechet-agent.onrender.com
// (AGENT_WEBHOOK_URL is still supported for backwards compatibility: the /portal address directly.)
function agentBase(): string | null {
  if (process.env.AGENT_URL) return process.env.AGENT_URL.replace(/\/$/, "");
  if (process.env.AGENT_WEBHOOK_URL) return process.env.AGENT_WEBHOOK_URL.replace(/\/portal\/?$/, "");
  return null;
}

const headers = () => ({
  "Content-Type": "application/json",
  "x-portal-secret": process.env.AGENT_SHARED_SECRET ?? "",
});

export type AgentHandoff = {
  orderItemId: string;
  clientId: string;
  clientName: string;
  text: string;
  fileName: string | null;
  source: "portal";
};

/**
 * Hands a new order to the agent in part D. Best effort: the draft is already saved in monday,
 * so a failure on the agent's side doesn't fail the customer, and the agent can also collect open drafts itself.
 * The AI key lives with the agent, not in the portal.
 */
export async function forwardToAgent(payload: AgentHandoff): Promise<"sent" | "skipped" | "failed"> {
  const base = agentBase();
  if (!base) return "skipped";
  try {
    const res = await fetch(`${base}/portal`, {
      method: "POST", headers: headers(), body: JSON.stringify(payload),
      // the agent answers right away and processes in the background. On Render free, waking up can take a while
      signal: AbortSignal.timeout(15000),
    });
    return res.ok ? "sent" : "failed";
  } catch (e) {
    console.error("agent handoff failed", e);
    return "failed";
  }
}

/** Bonus: "איפה ההזמנה שלי?". The client is the one from the link only. The question doesn't affect it. */
export async function askAgent(clientId: string, clientName: string, question: string):
  Promise<{ answer: string; needsHuman: boolean } | null> {
  const base = agentBase();
  if (!base) return null;
  try {
    const res = await fetch(`${base}/ask`, {
      method: "POST", headers: headers(),
      body: JSON.stringify({ clientId, clientName, question }),
      signal: AbortSignal.timeout(55000),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    console.error("ask failed", e);
    return null;
  }
}
